import time
import constants
from api.insales_api import Insales
from api.key_crm_api import KeyCRM
from db.db_init import Session
from db.models import UkrsalonOrderDB
from parse.parse_insales_order import OrderInsales
from parse.parse_constants import Status, ukrsalon_crm_id, insta_ukrsalon_crm_id
from messengers import send_tg_message, send_service_tg_message
from loguru import logger
from pathlib import Path
from retry import retry

ukrsalon = Insales(constants.UKRSALON_URL)
crm = KeyCRM(constants.KEY_CRM_API_KEY)

reload_file = Path(__file__).with_suffix('.reload')
logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='INFO', backtrace=True, diagnose=True)
logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='ERROR')


def send_notification(order: OrderInsales, key_crm_id):
    if order.status_id != Status.CANCELLED.value:
        send_text = (f'{"НОВЫЙ" if order.status_id == Status.NEW.value else "Принят"} заказ {order.source_uuid} на Укрсалоне\n'
                     f'Сумма: {round(order.total_price)} грн.\n'
                     f'Клиент: {order.buyer.full_name}\n'
                     f'Телефон: {order.buyer.phone}\n')
        if order.status_id == Status.NEW.value:
            send_text += f'Админка: https://ukrsalon.com.ua/admin2/orders/{order.insales_id}\n'
                          # f'CRM: https://ukrsalon.keycrm.app/app/orders/view/{key_crm_id}')
        send_tg_message(send_text, *constants.managers_plus)
        logger.info(send_text.replace('\n', ' '))


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


@retry(stop_after_delay=300, max_delay=20)
def get_orders() -> list[dict]:
    r = ukrsalon.get_orders()
    r.raise_for_status()
    return r.json()


@logger.catch
def main():
    with Session.begin() as session:
        for order_dict in get_orders():
            q = session.query(UkrsalonOrderDB).filter_by(source_uuid=order_dict['number']).first()
            if q is None:  # order not found in db
                print('inserting order: ', order_dict['number'])
                order = OrderInsales(**order_dict)
                set_order_shop(order)
                crm_reply = crm.new_order(order.model_dump())
                try:
                    if crm_reply.get('errors').get('source_uuid')[0] == 'The source uuid has already been taken.':
                        print('source_uuid: The source uuid has already been taken')
                        crm_reply = crm.get_orders(filter={"source_uuid": order_dict['number']})[0]
                        # crm_reply = crm.get_order_by_source_uuid(source_uuid=order_dict['number'])
                except:
                    pass
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
                send_notification(order, crm_reply['id'])
                update_order_backoffice(order)
                update_client_backoffice(order)
            else:
                if not q.is_accepted:
                    order = OrderInsales(**order_dict)
                    if order.status_id != Status.NEW.value:
                        send_notification(order, q.key_crm_id)
                        q.is_accepted = True


if __name__ == '__main__':
    logger.info(f'STARTING {__file__}')
    while True:
        main()
        if reload_file.exists():
            reload_file.unlink(missing_ok=True)
            logger.info(f'SHUTTING DOWN {__file__}')
            exit(0)
        print(f'Insales orders - sleeping {constants.time_to_sleep_insales_crm}')
        time.sleep(constants.time_to_sleep_insales_crm)




