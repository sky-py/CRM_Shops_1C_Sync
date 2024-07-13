import asyncio
import platform
import random
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from retry import retry
from sqlalchemy.future import select
import colorama

import constants
from api.horoshop_api_async import HoroshopClient
from db.db_init_async import Session_async, create_tables
from db.models import PromOrderDB
from messengers import send_service_tg_message, send_tg_message
from parse.parse_constants import PromStatus
from parse.horoshop_models import OrderHoroshop


colorama.init()
bad_orders = []
reload_file = Path(__file__).with_suffix('.reload')
logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='INFO', backtrace=True, diagnose=True)
logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='ERROR')


def send_message(order):
    message_text = generate_message_text(order)
    send_tg_message(message_text, *constants.managers_plus)
    logger.info(message_text.replace('\n', ' '))


def generate_message_text(order: OrderHoroshop):
    match order.status:
        case PromStatus.NEW:
            state = 'НОВЫЙ'
        case _:
            state = 'Принят'

    send_text = (f'{state} заказ {order.order_id} на {order.shop}\n'   
                 f'Сумма: {order.total_price} грн.\n'
                 f'Клиент: {order.buyer.full_name} \n'
                 f'Телефон: {order.buyer.phone}')
    return send_text


async def add_order_to_db(order: OrderHoroshop, session: Session_async):
    session.add(PromOrderDB(
        order_id=order.order_id,
        status=order.status,
        shop=order.shop,
        is_accepted=False if order.status == PromStatus.NEW else True,
        ordered_at=order.date_created
    ))


def get_color(shop: dict) -> str:
    i = constants.horoshop_shops.index(shop)
    return f'\033[{31+i%6}m'


def get_timestamp(minutes_ago: int):
    past_time = datetime.now() - timedelta(minutes=minutes_ago)
    return past_time.strftime("%Y-%m-%d %H:%M:%S")


@retry(stop_after_delay=constants.horoshop_stop_tries_after_delay)
async def get_orders(shop_client: HoroshopClient) -> list | None:
    from_date = get_timestamp(minutes_ago=constants.HOROSHOP_TIME_INTERVAL_TO_CHECK)
    return await shop_client.get_orders(date_from=from_date, limit=1000)


@logger.catch
async def worker(shop: dict):
    shop_client = HoroshopClient(shop['login'], shop['password'])
    shop_name = shop['name']
    color = get_color(shop)
    print(color + f"START HOROSHOP {shop_name} ")
    await asyncio.sleep(random.randint(0, constants.prom_sleep_time))
    while True:
        orders = await get_orders(shop_client)
        await process_orders(orders, shop_name, color)
        print(color + f'HOROSHOP {shop_name} - OK. Sleeping for {constants.prom_sleep_time} seconds')
        if reload_file.exists():
            logger.info(f'STOPPING {shop_name} thread')
            return
        await asyncio.sleep(constants.prom_sleep_time)


async def process_orders(orders: list, shop_name: str, color: str):
    async with Session_async() as session:
        async with session.begin():
            for order_dict in orders:
                try:
                    order = OrderHoroshop(**order_dict)
                    order.shop = shop_name
                    await process_one_order(order, session, color)
                except:
                    if order_dict['order_id'] not in bad_orders:
                        logger.error(f'Problem with {shop_name} - order: {order_dict['id']}')
                        bad_orders.append(order_dict['order_id'])
                    else:
                        pass


async def process_one_order(order: OrderHoroshop, session: Session_async, color: str):
    result = await session.execute(select(PromOrderDB).filter_by(order_id=order.order_id))
    order_db = result.scalars().first()
    if order_db is None:  # order is new
        await add_order_to_db(order, session)
        send_message(order)
    else:
        if not order_db.is_accepted and order.status not in [PromStatus.NEW]:
            order_db.is_accepted = True
            send_message(order)

        if order.status != order_db.status:
            order_db.status = order.status


async def main():
    logger.info(f'STARTING {__file__}')
    await create_tables()
    await asyncio.gather(*[worker(shop) for shop in constants.horoshop_shops])
    reload_file.unlink(missing_ok=True)
    logger.info(f'SHUTTING DOWN {__file__}')


if __name__ == '__main__':
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())





