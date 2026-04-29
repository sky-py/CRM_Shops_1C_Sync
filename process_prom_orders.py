import asyncio
import platform
import random
from datetime import datetime, timedelta
from pathlib import Path
import constants
from api.prom_api_async import PromClient
from db.db_init_async import AsyncSession, Session_async, create_tables
from db.models import PromCPARefundOutbox, PromDeliveryCommissionOutbox, PromOrderDB
from loguru import logger
from parse.parse_constants import PromStatus
from parse.parse_prom_order import OrderProm
from retry import retry
from sqlalchemy.future import select
from telegram.bot import close_bot_session
from telegram.sender import send_notification
from telegram.sender_sync import send_service_tg_message
from telegram.types import Notification
from tools.rich_log import RichLogMulti


bad_orders = []
reload_file = Path(__file__).with_suffix('.reload')


def init_logger() -> None:
    logger.remove()
    logger.add(lambda msg: rich_log.print_log(msg.split('=>')[0]), level='INFO', colorize=False)
    logger.add(
        sink=f'log/{Path(__file__).stem}.log',
        format='{time:YYYY-MM-DD at HH:mm:ss.SSS} | {level} | {message}',
        level='INFO',
        backtrace=True,
        diagnose=True,
    )

    logger.add(
        sink=lambda msg: send_service_tg_message(msg),
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='ERROR',
        filter=lambda record: record.update(exception=None) or True,
    )


async def send_message(order):
    message_text = generate_message_text(order)
    await send_notification(
        Notification(
            source='prom',
            order_id=order.order_id,
            shop_name=order.shop,
            text=message_text,
            button=True,  # order.status in [PromStatus.NEW, PromStatus.PAID],
        )
    )


def generate_message_text(order: OrderProm):
    match order.status:
        case PromStatus.NEW:
            state = 'НОВЫЙ'
        case PromStatus.PAID:
            state = 'НОВЫЙ ОПЛАЧЕННЫЙ'
        case _:
            state = 'НОВЫЙ'  # 'Принят'

    send_text = (
        f'{state} заказ {order.order_id} на {order.shop}\n'
        f'Сумма: {order.total_price} грн.\n'
        f'Клиент: {order.buyer.full_name} \n'
        f'Телефон: {order.buyer.phone}'
    )
    return send_text


async def add_order_to_db(order: OrderProm, session: AsyncSession):
    order_db = PromOrderDB(
        order_id=order.order_id,
        status=order.status,
        shop=order.shop,
        is_accepted=False if order.status == PromStatus.NEW or order.status == PromStatus.PAID else True,
        cpa_commission=order.cpa_commission,
        ordered_at=order.date_created,
    )
    session.add(order_db)
    await session.flush()
    logger.info(f'Added {order.shop}:{order.order_id} to db')
    return order_db


async def add_order_to_cpa_commission_outbox(order: OrderProm, session: AsyncSession):
    session.add(PromCPARefundOutbox(order_id=order.order_id, shop=order.shop, cpa_commission=order.cpa_commission))


async def add_order_to_delivery_commission_outbox(order: OrderProm, session: AsyncSession):
    session.add(
        PromDeliveryCommissionOutbox(
            order_id=order.order_id, shop=order.shop, delivery_commission=order.delivery_commision
        )
    )


def order_date_is_valid(date: str) -> bool:
    return datetime.fromisoformat(date).replace(tzinfo=None) > (
        datetime.now() - timedelta(days=constants.PROM_CONSIDER_ORDER_FINISHED_DAYS)
    )


@retry(stop_after_delay=constants.PROM_STOP_TRIES_AFTER_DELAY_SEC)
async def get_orders(shop_client: PromClient) -> list:
    last_modified_from = None
    # comment next line for getting ALL orders
    last_modified_from = datetime.now() - timedelta(minutes=constants.PROM_TIME_INTERVAL_TO_CHECK_MIN)
    if last_modified_from is not None:
        orders = await shop_client.get_orders(last_modified_from=last_modified_from, limit=1000)
        return [order for order in orders if order_date_is_valid(order['date_created'])]
    else:  # for getting ALL orders from date
        orders = await shop_client.get_orders(
            created_from=datetime(year=2025, month=7, day=1), created_to=datetime.now(), limit=1000
        )
        return orders


async def worker(shop: dict):
    shop_client = PromClient(shop['token'])
    shop_name = shop['name']
    logger.info(f'START PROM {shop_name} ')
    await asyncio.sleep(random.randint(0, 2))
    while True:
        try:
            orders = await get_orders(shop_client)
        except Exception as e:
            logger.error(f'Problem with {shop_name} - {e}')
            continue
        rich_log.print_to_request_area(shop_name, f'{len(orders)} orders were received')
        await process_orders(orders, shop_name)
        # logger.info(f'PROM {shop_name} - OK. Sleeping for {constants.PROM_SLEEP_TIME} seconds')
        if reload_file.exists():
            logger.info(f'Found reload file {__file__}, STOPPING {shop_name} thread')
            return
        await asyncio.to_thread(rich_log.sleep, shop_name, constants.PROM_SLEEP_TIME)
        # await asyncio.sleep(3600) # for testing purposes, remove in production


async def process_orders(orders: list, shop_name: str):
    notifications = []
    async with Session_async() as session:
        async with session.begin():
            for order_dict in orders:
                try:
                    order = OrderProm(**order_dict)
                    order.shop = shop_name
                except Exception as e:
                    if order_dict['id'] not in bad_orders:
                        logger.error(f'Problem with {shop_name} - order: {order_dict["id"]} {e}')
                        bad_orders.append(order_dict['id'])
                else:
                    notifications.extend(await process_one_order(order, session))
    for order in notifications:
        await send_message(order)


def order_was_accepted(order, order_db) -> bool:
    if not order_db.is_accepted and order.status not in [PromStatus.NEW, PromStatus.PAID]:
        order_db.is_accepted = True
        return True
    return False


def update_order_status(order, order_db):
    if order.status != order_db.status:
        order_db.status = order.status


async def process_cpa_refund(order, order_db, session):
    if order.cpa_is_refunded and not order_db.cpa_is_refunded:
        order_db.cpa_is_refunded = True
        await add_order_to_cpa_commission_outbox(order, session)
        logger.info(
            f'Updated CPA refund status for {order.shop}:{order.order_id} to {order.cpa_is_refunded} '
            f'and added to CPA refund outbox.'
        )


async def process_delivery_commission(order, order_db, session):
    if order.status == PromStatus.SUCCESS and order.delivery_commision != order_db.delivery_commission:
        order_db.delivery_commission = order.delivery_commision
        await add_order_to_delivery_commission_outbox(order, session)
        logger.info(
            f'Updated delivery commission for {order.shop}:{order.order_id} to {order.delivery_commision} '
            f'and added to delivery commission outbox.'
        )


def process_order_commission(order, order_db):
    if order.order_commission != order_db.order_commission:
        order_db.order_commission = order.order_commission
        logger.info(f'Updated order commission for {order.shop}:{order.order_id} to {order.order_commission}')


async def process_one_order(order: OrderProm, session: AsyncSession):
    notifications = []
    result = await session.execute(select(PromOrderDB).filter_by(order_id=order.order_id))
    order_db = result.scalars().first()
    if order_db is None:
        logger.info(f'Got new order {order.shop}:{order.order_id} => {order}')
        order_db = await add_order_to_db(order, session)
        notifications.append(order)

    # if order_was_accepted(order, order_db):
    #     notifications.append(order)
    update_order_status(order, order_db)
    await process_cpa_refund(order, order_db, session)
    await process_delivery_commission(order, order_db, session)
    process_order_commission(order, order_db)
    return notifications


async def main():
    try:
        await create_tables()
        await asyncio.gather(*[worker(shop) for shop in constants.prom_shops])
    finally:
        await close_bot_session()


if __name__ == '__main__':
    rich_log = RichLogMulti(
        header=f'Синхронизация Prom с CRM       {__file__}',
        shop_names=[shop['name'] for shop in constants.prom_shops],
        header_style='bold white on magenta',
    )
    init_logger()
    logger.info(f'STARTING {__file__}')

    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f'Error in {__file__}: {e}')
    finally:
        reload_file.unlink(missing_ok=True)
        logger.info(f'SHUTTING DOWN {__file__}')
        rich_log.stop()
