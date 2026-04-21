from contextlib import redirect_stdout
import constants
from api.insales_api import Insales
from api.key_crm_api import KeyCRM
from db.db_init import Session_Sync
from db.models import UkrsalonOrderDB
from parse.parse_insales_order import OrderInsales
from parse.parse_constants import Status, ukrsalon_crm_id, insta_ukrsalon_crm_id
from telegram.sender_sync import send_service_tg_message
from loguru import logger
from pathlib import Path
from telegram.sender import send_notification
from telegram.types import Notification
from tools.rich_log import RichLog

ukrsalon = Insales(constants.UKRSALON_URL)
crm = KeyCRM(constants.CRM_API_KEY)
rich_log = RichLog(header=f'Синхронизация Укрсалона с CRM       {__file__}')

reload_file = Path(__file__).with_suffix('.reload')


def init_logger() -> None:
    logger.remove()
    logger.add(lambda msg: rich_log.print_log(msg.split('=>')[0]), level='INFO', colorize=True)
    logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
               level='INFO', backtrace=True, diagnose=True)
    logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
               level='ERROR')


def send_message(order: OrderInsales, key_crm_id: int):
    message_text = generate_message_text(order, key_crm_id)
    send_notification(
        Notification(
            source='ukrsalon',
            order_id=order.source_uuid,
            shop_name='УкрСалон',
            text=message_text,
            button=True  # order.status_id == Status.NEW.value,
        )
    )
    logger.info(message_text)


def generate_message_text(order: OrderInsales, key_crm_id: int) -> str:
    match order.status_id:
        case Status.NEW.value:
            state = 'НОВЫЙ'
        case _:
            state = 'НОВЫЙ'  # 'Принят'

    send_text = (f'{state} заказ {order.source_uuid} на Укрсалоне =>\n'
                 f'Сумма: {round(order.total_price)} грн.\n'
                 f'Клиент: {order.buyer.full_name}\n'
                 f'Телефон: {order.buyer.phone}\n')
    if order.status_id == Status.NEW.value:
        send_text += f'Админка: https://ukrsalon.com.ua/admin2/orders/{order.insales_id}\n'
                      # f'CRM: https://ukrsalon.keycrm.app/app/orders/view/{key_crm_id}')
    return send_text


def update_order_backoffice(order: OrderInsales):
    ukrsalon.write_order(order.insales_id,
                         {'order': {
                             'shipping_address_attributes': {
                                 'phone': order.buyer.phone,
                                 'name': order.buyer.name,
                                 'surname': order.buyer.surname,
                                 'middlename': order.buyer.middlename,
                             },
                         }
                         })


def update_client_backoffice(order: OrderInsales):
    ukrsalon.write_client(order.buyer.id,
                          {'client': {
                              'phone': order.buyer.phone,
                              'name': order.buyer.name,
                              'surname': order.buyer.surname,
                              'middlename': order.buyer.middlename,
                          }
                          })


def set_order_shop(order: OrderInsales) -> None:
    """if order from instagram => CRMshop=Insta shop"""
    if 'instagram' in order.marketing.utm_source.lower():
        order.source_id = insta_ukrsalon_crm_id
    else:
        order.source_id = ukrsalon_crm_id


# @retry(stop_after_delay=300, max_delay=20)
def get_orders() -> list[dict]:
    r = ukrsalon.get_orders()
    r.raise_for_status()
    orders = r.json()
    rich_log.print_request(f'{len(orders)} last orders were received')
    return orders


def process_order(order_dict: dict, session: Session_Sync) -> tuple[OrderInsales, int] | None:
    q = session.query(UkrsalonOrderDB).filter_by(source_uuid=order_dict['number']).first()
    if q is None:  # order not found in db
        try:
            order = OrderInsales(**order_dict)
            logger.info(f'Got new order {order.source_uuid} => {order}')
        except Exception as e:
            logger.error(f'Error parsing order {order_dict["number"]}: {e}')
            return None
        set_order_shop(order)
        crm_reply = crm.new_order(order.model_dump())
        errors = crm_reply.get('errors', {})
        if errors:
            if errors.get('source_uuid', [''])[0] == 'The source uuid has already been taken.':
                logger.info(f'Error inserting order {order.source_uuid} to CRM: The source uuid has already been taken. Trying to get order from CRM...')
                try:
                    crm_reply = crm.get_orders(filter={"source_uuid": order_dict['number']})[0]
                    logger.info(f'Successfully got id {order.source_uuid} from CRM')
                except:
                    logger.error(f'Error getting id {order.source_uuid} from CRM => {crm_reply}')
                    return None
            else:
                logger.error(f'Got unknown error from CRM for order {order_dict['number']} {errors}')
                return None
        session.add(UkrsalonOrderDB(source_uuid=order.source_uuid,
                                    insales_id=order.insales_id,
                                    key_crm_id=crm_reply['id'],
                                    ordered_at=order.ordered_at,
                                    total_price=order.total_price,
                                    manager_id=order.manager_DB,
                                    status_id=order.status_id,
                                    is_paid=order.is_paid,
                                    is_accepted=False if order.status_id == Status.NEW.value else True,
                                    json=order_dict
                                    ))
        update_order_backoffice(order)
        update_client_backoffice(order)
        return order, crm_reply['id']

    if not q.is_accepted:
        order = OrderInsales(**order_dict)
        if order.status_id != Status.NEW.value:
            # notifications.append((order, q.key_crm_id))
            q.is_accepted = True
    return None


def main() -> None:
    notifications = []
    with Session_Sync.begin() as session:
        with redirect_stdout(rich_log.console_to_rich_log_redirector):
            orders = get_orders()
        for order_dict in orders:
            notification = process_order(order_dict, session)
            if notification is not None:
                notifications.append(notification)
    for pair_data in notifications:
        if pair_data[0].status_id != Status.CANCELLED.value:
            send_message(*pair_data)


if __name__ == '__main__':
    init_logger()
    logger.info(f'STARTING {__file__}')
    try:
        while True:
            main()
            if reload_file.exists():
                reload_file.unlink(missing_ok=True)
                logger.info(f'SHUTTING DOWN {__file__}')
                exit(0)
            rich_log.sleep(constants.time_to_sleep_insales_crm)
    except Exception as e:
        logger.exception(f'Error in {__file__}: {e}')
    finally:
        rich_log.stop()
