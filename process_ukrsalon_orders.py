import asyncio
import platform
from contextlib import redirect_stdout
from pathlib import Path
import constants
import httpx
from api.insales_api import Insales
from api.key_crm_api import KeyCRM
from config.logging import logger_init
from db.db_init_async import AsyncSession, Session_async, create_tables
from db.models import UkrsalonOrderDB
from exceptions import response_details_from_exception
from loguru import logger
from parse.parse_constants import Status, insta_ukrsalon_crm_id, ukrsalon_crm_id
from parse.parse_insales_order import OrderInsales
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telegram.bot import close_bot_session
from telegram.sender import send_notification
from telegram.types import Notification
from tools.rich_log import RichLog


ukrsalon = Insales(constants.UKRSALON_URL)
crm = KeyCRM(constants.CRM_API_KEY)

reload_file = Path(__file__).with_suffix('.reload')
PRODUCT_MIN_PRICE = 0.01
SOURCE_UUID_TAKEN_ERROR = 'The source uuid has already been taken.'


async def send_message(order: OrderInsales, key_crm_id: int):
    message_text = generate_message_text(order, key_crm_id)
    await send_notification(
        Notification(
            source='ukrsalon',
            order_id=order.insales_id,
            source_uuid=order.source_uuid,
            shop_name='УкрСалон',
            text=message_text,
            button=True,  # order.status_id == Status.NEW.value,
        )
    )


def generate_message_text(order: OrderInsales, key_crm_id: int) -> str:
    match order.status_id:
        case Status.NEW.value:
            state = 'НОВЫЙ'
        case _:
            state = 'НОВЫЙ'  # 'Принят'

    send_text = (
        f'{state} заказ {order.source_uuid} на Укрсалоне =>\n'
        f'Сумма: {round(order.total_price)} грн.\n'
        f'Клиент: {order.buyer.full_name}\n'
        f'Телефон: {order.buyer.phone}\n'
    )
    # if order.status_id == Status.NEW.value:
    send_text += f'Админка: https://ukrsalon.com.ua/admin2/orders/{order.insales_id}\n'
    # f'CRM: https://ukrsalon.keycrm.app/app/orders/view/{key_crm_id}')
    return send_text


async def update_shipping_address_backoffice(order: OrderInsales):
    await ukrsalon.write_order(
        order.insales_id,
        {
            'order': {
                'shipping_address_attributes': {
                    'phone': order.buyer.phone,
                    'name': order.buyer.name,
                    'surname': order.buyer.surname,
                    'middlename': order.buyer.middlename,
                }
            }
        },
    )


async def update_client_backoffice(order: OrderInsales):
    await ukrsalon.write_client(
        order.buyer.id,
        {
            'client': {
                'phone': order.buyer.phone,
                'name': order.buyer.name,
                'surname': order.buyer.surname,
                'middlename': order.buyer.middlename,
            }
        },
    )


def set_order_shop(order: OrderInsales) -> None:
    """if order from instagram => CRMshop=Insta shop"""
    if 'instagram' in order.marketing.utm_source.lower():
        order.source_id = insta_ukrsalon_crm_id
    else:
        order.source_id = ukrsalon_crm_id


async def get_orders() -> list[dict]:
    r = await ukrsalon.get_orders()
    orders = r.json()
    rich_log.print_request(f'{len(orders)} last orders were received')
    return orders


def replace_zero_price(order: OrderInsales) -> None:
    for product in order.products:
        if product.price == 0:
            product.price = PRODUCT_MIN_PRICE


async def process_crm_errors(errors: dict, order: OrderInsales) -> dict | None:
    source_uuid_errors = errors.get('source_uuid', [])
    if SOURCE_UUID_TAKEN_ERROR not in source_uuid_errors:
        logger.error(f'Got unknown error from CRM for order {order.source_uuid} {errors}')
        return None

    logger.info(f'Error inserting order {order.source_uuid} to CRM: {SOURCE_UUID_TAKEN_ERROR}. Trying to get order from CRM...')
    try:
        crm_orders = await asyncio.to_thread(crm.get_orders, filter={'source_uuid': order.source_uuid})
    except Exception as e:
        logger.error(f'Error getting id {order.source_uuid} from CRM => {e}')
        return None

    if not crm_orders:
        logger.error(f'Error getting id {order.source_uuid} from CRM => empty response')
        return None

    logger.info(f'Successfully got id {order.source_uuid} from CRM')

    return crm_orders[0]


def get_crm_errors_from_exception(e: Exception) -> dict:
    response = getattr(e, 'response', None)
    if response is None:
        return {}

    try:
        data = response.json()
    except ValueError:
        return {}

    if not isinstance(data, dict):
        return {}

    return data.get('errors', {})


async def create_or_get_crm_order(order: OrderInsales) -> dict | None:
    if not constants.IS_PRODUCTION_SERVER:
        return {'id': 1}

    replace_zero_price(order)  # CRM doesn't allow 0 price

    try:
        crm_reply = await asyncio.to_thread(crm.new_order, order.model_dump())
    except Exception as e:
        errors = get_crm_errors_from_exception(e)
        if errors:
            return await process_crm_errors(errors, order)
        logger.error(f'Error inserting Insales order {order.source_uuid} to CRM => {response_details_from_exception(e)}')
        return None

    errors = crm_reply.get('errors', {})
    if not errors:
        return crm_reply
    return await process_crm_errors(errors, order)
    # {'errors': {'payments.0.amount': ['The payments.0.amount must be at least 0.01.']}, 'message': 'The payments.0.amount must be at least 0.01.'}


async def process_order(order_dict: dict, session: AsyncSession) -> tuple[OrderInsales, int] | None:
    q = (await session.execute(select(UkrsalonOrderDB).filter_by(insales_id=order_dict['id']))).scalars().first()
    if q is None:  # order not found in db
        try:
            order = OrderInsales(**order_dict)
            logger.info(f'Got new order {order.source_uuid} => {order}')
        except Exception as e:
            logger.error(f'Error parsing order {order_dict.get("number")}: {e}')
            return None
        set_order_shop(order)
        crm_reply = await create_or_get_crm_order(order)
        if crm_reply is None:
            return None
        try:
            async with session.begin_nested():
                session.add(
                    UkrsalonOrderDB(
                        source_uuid=order.source_uuid,
                        insales_id=order.insales_id,
                        key_crm_id=crm_reply['id'],
                        ordered_at=order.ordered_at,
                        total_price=order.total_price,
                        manager_id=order.manager_DB,
                        status_id=order.status_id,
                        is_paid=order.is_paid,
                        is_accepted=False if order.status_id == Status.NEW.value else True,
                        json=order_dict,
                    )
                )
                await session.flush()
        except IntegrityError:
            logger.info(f'Order {order.insales_id} already inserted concurrently. Skipping duplicate insert.')
            return None
        if constants.IS_PRODUCTION_SERVER:
            await update_shipping_address_backoffice(order)
            await update_client_backoffice(order)
        return order, crm_reply['id']

    if not q.is_accepted:
        order = OrderInsales(**order_dict)
        if order.status_id != Status.NEW.value:
            # notifications.append((order, q.key_crm_id))
            q.is_accepted = True
    return None


async def worker() -> None:
    while True:
        try:
            with redirect_stdout(rich_log.console_to_rich_log_redirector):
                orders = await get_orders()
        except httpx.HTTPError as e:
            logger.info(f'Ukrsalon orders polling skipped: {type(e).__name__} {e}')
        else:
            notifications = await process_orders(orders)
            for pair_data in notifications:
                if pair_data[0].status_id != Status.CANCELLED.value:
                    await send_message(*pair_data)

        if reload_file.exists():
            logger.info(f'Found reload file {__file__}, STOPPING Ukrsalon orders sync')
            return
        await asyncio.to_thread(rich_log.sleep, constants.TIME_TO_SLEEP_INSALES_CRM)


async def process_orders(orders: list):
    notifications = []
    async with Session_async.begin() as session:
        for order_dict in orders:
            notification = await process_order(order_dict, session)
            if notification is not None:
                notifications.append(notification)
    return notifications


async def main() -> None:
    try:
        await create_tables()
        await worker()
    finally:
        await close_bot_session()


if __name__ == '__main__':
    rich_log = RichLog(header=f'Синхронизация Укрсалона с CRM       {__file__}')
    logger_init(rich_log=rich_log, log_cut_after='=>')
    logger.info(f'STARTING {__file__}')

    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f'Error in {__file__}: {e}')
    finally:
        reload_file.unlink(missing_ok=True)
        rich_log.stop()
        logger.info(f'SHUTTING DOWN {__file__}')
