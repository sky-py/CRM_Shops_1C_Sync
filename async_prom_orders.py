import asyncio
import platform
import random
from datetime import datetime, timedelta
from pathlib import Path
import colorama
import constants
from api.prom_api_async import PromClient
from db.db_init_async import Session_async, create_tables
from db.models import PromCPARefundQueueDB, PromOrderDB
from loguru import logger
from messengers import send_service_tg_message, send_tg_message
from parse.parse_constants import PromStatus
from parse.parse_prom_order import OrderProm
from retry import retry
from sqlalchemy.future import select

colorama.init()
bad_orders = []
reload_file = Path(__file__).with_suffix('.reload')
logger.add(
    sink=f'log/{Path(__file__).stem}.log',
    format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
    level='INFO',
    backtrace=True,
    diagnose=True,
)
logger.add(
    sink=lambda msg: send_service_tg_message(msg),
    format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
    level='ERROR',
)


def send_message(order):
    message_text = generate_message_text(order)
    send_tg_message(message_text, *constants.managers_plus)
    logger.info(message_text.replace('\n', ' '))


def generate_message_text(order: OrderProm):
    match order.status:
        case PromStatus.NEW:
            state = 'НОВЫЙ'
        case PromStatus.PAID:
            state = 'НОВЫЙ ОПЛАЧЕННЫЙ'
        case _:
            state = 'Принят'

    send_text = (
        f'{state} заказ {order.order_id} на {order.shop}\n'
        f'Сумма: {order.total_price} грн.\n'
        f'Клиент: {order.buyer.full_name} \n'
        f'Телефон: {order.buyer.phone}'
    )
    return send_text


async def add_order_to_db(order: OrderProm, session: Session_async):
    session.add(
        PromOrderDB(
            order_id=order.order_id,
            status=order.status,
            shop=order.shop,
            is_accepted=False if order.status == PromStatus.NEW or order.status == PromStatus.PAID else True,
            cpa_commission=order.cpa_commission,
            delivery_commission=order.delivery_commision,
            cpa_is_refunded=order.cpa_is_refunded,
            ordered_at=order.date_created,
        )
    )
    logger.info(f'Added {order.shop}:{order.order_id} to db. Order = {order}')


async def add_order_to_cpa_queue(order: OrderProm, session: Session_async):
    session.add(PromCPARefundQueueDB(order_id=order.order_id, shop=order.shop, cpa_commission=order.cpa_commission))
    logger.info(f'Added {order.shop}:{order.order_id} with CPA commission {order.cpa_commission} to cpa refund queue')


def get_color(shop: dict) -> str:
    i = constants.prom_shops.index(shop)
    return f'\033[{31 + i % 6}m'


def order_date_is_valid(date: str) -> bool:
    return datetime.fromisoformat(date).replace(tzinfo=None) > (datetime.now() -
            timedelta(days=constants.PROM_DAYS_TO_CONSIDER_ORDER_FINISHED))


@retry(stop_after_delay=constants.prom_stop_tries_after_delay)
async def get_orders(shop_client: PromClient) -> list | None:
    from_date = datetime.now() - timedelta(minutes=constants.PROM_TIME_INTERVAL_TO_CHECK)
    orders = await shop_client.get_orders(last_modified_from=from_date, limit=1000)
    return [order for order in orders if order_date_is_valid(order['date_created'])]
    # orders = await shop_client.get_orders(date_from=datetime(year=2024, month=5, day=1), date_to=datetime.now(), limit=1000)  # for getting all orders from date
    # return orders  # for getting all orders from date


@logger.catch  # TODO inform worker does not run
async def worker(shop: dict):
    shop_client = PromClient(shop['token'])
    color = get_color(shop)
    shop_name = shop['name']
    print(color + f'START PROM {shop_name} ')
    await asyncio.sleep(random.randint(0, constants.prom_sleep_time))
    while True:
        orders = await get_orders(shop_client)
        # print(f'{shop_name} got {len(orders)} orders')  # for testing purposes
        await process_orders(orders, shop_name, color)
        print(color + f'PROM {shop_name} - OK. Sleeping for {constants.prom_sleep_time} seconds')
        if reload_file.exists():
            logger.info(f'STOPPING {shop_name} thread')
            return
        await asyncio.sleep(constants.prom_sleep_time)
        # await asyncio.sleep(3600) # for testing purposes, remove in production


async def process_orders(orders: list, shop_name: str, color: str):
    async with Session_async() as session:
        async with session.begin():
            for order_dict in orders:
                try:
                    order = OrderProm(**order_dict)
                    order.shop = shop_name
                    await process_one_order(order, session, color)
                except Exception as e:
                    if order_dict['id'] not in bad_orders:
                        logger.error(f'Problem with {shop_name} - order: {order_dict["id"]}')
                        bad_orders.append(order_dict['id'])


async def process_one_order(order: OrderProm, session: Session_async, color: str):
    result = await session.execute(select(PromOrderDB).filter_by(order_id=order.order_id))
    order_db = result.scalars().first()
    if order_db is None:
        await process_new_order(order, session)
    else:
        if not order_db.is_accepted and order.status not in [PromStatus.NEW, PromStatus.PAID]:
            order_db.is_accepted = True
            send_message(order)

        if order.status != order_db.status:
            order_db.status = order.status

        if order.cpa_is_refunded and not order_db.cpa_is_refunded:
            order_db.cpa_is_refunded = True
            await add_order_to_cpa_queue(order, session)

        if order.delivery_commision != order_db.delivery_commission:
            order_db.delivery_commission = order.delivery_commision
            logger.info(f'Updated delivery commission for {order.shop}:{order.order_id} to {order.delivery_commision}')


async def process_new_order(order: OrderProm, session: Session_async):
    await add_order_to_db(order, session)
    if order.cpa_is_refunded:
        await add_order_to_cpa_queue(order, session)
    send_message(order)


async def main():
    logger.info(f'STARTING {__file__}')
    await create_tables()
    await asyncio.gather(*[worker(shop) for shop in constants.prom_shops])
    reload_file.unlink(missing_ok=True)
    logger.info(f'SHUTTING DOWN {__file__}')


if __name__ == '__main__':
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
