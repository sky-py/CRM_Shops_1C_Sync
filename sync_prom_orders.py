import asyncio
import httpx
import random
import platform
import colorama
from datetime import datetime, timedelta
import constants
from api.prom_api_async import PromClient
from db.db_init import Session
from db.models import PromOrderDB, PromCPARefundQueueDB
from parse.parse_constants import PromStatus
from parse.parse_prom_order import OrderProm
from loguru import logger
from messengers import send_tg_message, send_service_tg_message


colorama.init()
logger.add(sink='prom_orders.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", level='INFO',
           backtrace=True, diagnose=True)
logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}", level='ERROR',
           backtrace=True, diagnose=True)


def generate_message_text(order: OrderProm):
    match order.status:
        case PromStatus.NEW:
            state = 'НОВЫЙ'
        case PromStatus.PAID:
            state = 'НОВЫЙ ОПЛАЧЕННЫЙ'
        case _:
            state = 'Принят'

    send_text = (f'{state} заказ {order.order_id} на {order.shop}\n'   
                 f'Сумма: {order.total_price} грн.\n'
                 f'Клиент: {order.buyer.full_name} \n'
                 f'Телефон: {order.buyer.phone}')
    return send_text


def add_order_to_db(order: OrderProm, session: Session):
    session.add(PromOrderDB(
        order_id=order.order_id,
        status=order.status,
        shop=order.shop,
        is_accepted=False if order.status == PromStatus.NEW or order.status == PromStatus.PAID else True,
        cpa_commission=order.cpa_commission,
        cpa_is_refunded=order.cpa_is_refunded,
        ordered_at=order.date_created
    ))


def add_order_to_cpa_queue(order: OrderProm, session: Session):
    session.add(PromCPARefundQueueDB(
        order_id=order.order_id,
        shop=order.shop,
        cpa_commission=order.cpa_commission,
    ))


def get_color(shop: dict) -> str:
    i = constants.prom_shops.index(shop)
    return f'\033[{31+i%6}m'


def get_timestamp(minutes_ago: int):
    past_time = datetime.now() - timedelta(minutes=minutes_ago)
    return past_time.strftime("%Y-%m-%dT%H:%M:%S")


async def get_orders_persist(shop_client: PromClient, shop_name: str, color: str) -> list | None:
    for i in range(1, constants.prom_tries_per_request):
        from_date = get_timestamp(minutes_ago=constants.PROM_TIME_INTERVAL_TO_CHECK)
        # r = await shop_client.get_orders(last_modified_from=from_date)
        r = await shop_client.get_orders(date_from='2024-05-01T00:00:00', limit=1000)
        if r.status_code == 200:
            return r.json()['orders']
        else:
            print(color + f"{shop_name} - try #{i}: got ERROR: {r.status_code}. "
                          f"Waiting for {constants.prom_pause_between_tries} seconds")
            await asyncio.sleep(constants.prom_pause_between_tries)

    logger.error(color + f"{shop_name} - Cant get reply. ERROR TEXT:\n{r.text}")


# @logger.catch()
async def worker(shop: dict, client: httpx.AsyncClient):
    shop_client = PromClient(shop['token'], client)
    color = get_color(shop)
    shop_name = shop['name']
    print(color + f"START PROM {shop_name} ")
    await asyncio.sleep(random.randint(0, constants.prom_sleep_time))
    while True:
        orders = await get_orders_persist(shop_client, shop_name, color)
        await process_orders(orders, shop_name, color)
        print(color + f"PROM {shop_name} - OK. Sleeping for {constants.prom_sleep_time} seconds")
        await asyncio.sleep(constants.prom_sleep_time)


async def process_orders(orders: list, shop_name: str, color: str):
    with Session() as session:
        for order_dict in orders:
            order = OrderProm(**order_dict)
            order.shop = shop_name
            with session.begin():
                await process_one_order(order, session, color)


async def process_one_order(order: OrderProm, session: Session, color: str):
    order_db = session.query(PromOrderDB).filter_by(order_id=order.order_id).first()
    if order_db is None:
        await process_new_order(order, session)
    else:
        if not order_db.is_accepted and order.status not in [PromStatus.NEW, PromStatus.PAID]:
            order_db.is_accepted = True
            send_tg_message(generate_message_text(order), *constants.managers_plus)
            logger.info(color + f"{order.shop} - принят заказ {order.order_id}")

        if order.status != order_db.status:
            order_db.status = order.status

        if order.cpa_is_refunded and not order_db.cpa_is_refunded:
            order_db.cpa_is_refunded = True
            add_order_to_cpa_queue(order, session)


async def process_new_order(order: OrderProm, session: Session):
    add_order_to_db(order, session)
    if order.cpa_is_refunded:
        add_order_to_cpa_queue(order, session)
    send_tg_message(generate_message_text(order), *constants.managers_plus)
    logger.info(f"{order.shop} - НОВЫЙ заказ {order.order_id}")


async def main():
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[worker(shop, client) for shop in constants.prom_shops])


if __name__ == '__main__':
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())





