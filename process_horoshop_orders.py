import asyncio
import platform
import random
from datetime import datetime, timedelta
from pathlib import Path
import constants
from api.horoshop_api_async import HoroshopClient
from config.logging import logger_init
from db.db_init_async import AsyncSession, Session_async, create_tables
from db.models import PromOrderDB
from loguru import logger
from parse.horoshop_models import OrderHoroshop
from parse.parse_constants import PromStatus
from retry import retry
from sqlalchemy.future import select
from telegram.bot import close_bot_session
from telegram.sender import send_notification
from telegram.types import Notification
from tools.rich_log import RichLogMulti


bad_orders = []
reload_file = Path(__file__).with_suffix('.reload')


async def send_message(order) -> None:
    message_text = generate_message_text(order)
    await send_notification(
        Notification(
            source='prom',
            order_id=order.order_id,
            shop_name=order.shop,
            text=message_text,
            button=True,  # order.status == PromStatus.NEW,
        )
    )
    logger.info(message_text.replace('\n', ' '))


def generate_message_text(order: OrderHoroshop):
    match order.status:
        case PromStatus.NEW:
            state = 'НОВЫЙ'
        case _:
            state = 'НОВЫЙ'  # 'Принят'

    send_text = (
        f'{state} заказ {order.order_id} на {order.shop}\n'
        f'Сумма: {order.total_price} грн.\n'
        f'Клиент: {order.buyer.full_name} \n'
        f'Телефон: {order.buyer.phone}'
    )
    return send_text


async def add_order_to_db(order: OrderHoroshop, session: AsyncSession):
    session.add(
        PromOrderDB(
            order_id=order.order_id,
            status=order.status,
            shop=order.shop,
            is_accepted=False if order.status == PromStatus.NEW else True,
            ordered_at=order.date_created,
        )
    )


def get_timestamp(minutes_ago: int):
    past_time = datetime.now() - timedelta(minutes=minutes_ago)
    return past_time.strftime('%Y-%m-%d %H:%M:%S')


@retry(stop_after_delay=constants.HOROSHOP_STOP_TRIES_AFTER_DELAY)
async def get_orders(shop_client: HoroshopClient) -> list:
    from_date = get_timestamp(minutes_ago=constants.HOROSHOP_TIME_INTERVAL_TO_CHECK)
    return await shop_client.get_orders(date_from=from_date, limit=1000)


async def worker(shop: dict):
    shop_client = HoroshopClient(shop_url=shop['url'], login=shop['login'], password=shop['password'])
    shop_name = shop['name']
    logger.info(f'START HOROSHOP {shop_name} ')
    await asyncio.sleep(random.randint(0, constants.PROM_SLEEP_TIME))
    while True:
        orders = await get_orders(shop_client)
        rich_log.print_to_request_area(shop_name, f'{len(orders)} orders were received')
        await process_orders(orders, shop_name)
        # logger.info(f'HOROSHOP {shop_name} - OK. Sleeping for {constants.PROM_SLEEP_TIME} seconds')
        if reload_file.exists():
            logger.info(f'Found reload file {__file__}, STOPPING {shop_name} thread')
            return
        await asyncio.to_thread(rich_log.sleep, shop_name, constants.PROM_SLEEP_TIME)


async def process_orders(orders: list, shop_name: str):
    notifications = []
    async with Session_async() as session:
        async with session.begin():
            for order_dict in orders:
                try:
                    order = OrderHoroshop(**order_dict)
                    order.shop = shop_name
                    notifications.extend(await process_one_order(order, session))
                except Exception as e:
                    if order_dict['order_id'] not in bad_orders:
                        logger.error(f'Problem with {shop_name} - order: {order_dict["id"]} {e}')
                        bad_orders.append(order_dict['order_id'])
                    else:
                        pass
    for order in notifications:
        await send_message(order)


async def process_one_order(order: OrderHoroshop, session: AsyncSession):
    notifications = []
    result = await session.execute(select(PromOrderDB).filter_by(order_id=order.order_id))
    order_db = result.scalars().first()
    if order_db is None:  # order is new
        logger.info(f'Got new order {order.shop}:{order.order_id} => {order}')
        await add_order_to_db(order, session)
        notifications.append(order)
    else:
        if not order_db.is_accepted and order.status not in [PromStatus.NEW]:
            order_db.is_accepted = True
            # notifications.append(order)

        if order.status != order_db.status:
            order_db.status = order.status
    return notifications


async def main() -> None:
    try:
        await create_tables()
        await asyncio.gather(*[worker(shop) for shop in constants.horoshop_shops])
    finally:
        await close_bot_session()


if __name__ == '__main__':
    rich_log = RichLogMulti(
        header=f'Синхронизация Horoshop с CRM       {__file__}',
        shop_names=[shop['name'] for shop in constants.horoshop_shops],
        header_style='bold white on green',
    )
    logger_init(rich_log=rich_log, rich_log_colorize=False)
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
