from flask import Flask, request
from waitress import serve
from parse.parse_key_crm_order import OrderKeyCrmShort
from db.db_init import Session
from db.models import UkrsalonOrderDB
from api.insales_api import Insales
import constants
from parse.parse_constants import *
from messengers import send_service_tg_message
from loguru import logger
from pathlib import Path

from retry import retry

app = Flask(__name__)
salon = Insales(constants.UKRSALON_URL)

logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='INFO', backtrace=True, diagnose=True)
logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='ERROR')


def make_dict_for_request(key_order: OrderKeyCrmShort) -> dict:
    # responsible_user_id = get_key_by_value(manager_insales_to_db, key_order.manager_id)
    if key_order.status == Status.DISPATCHED:
        key_order.status = Status.PRODUCTION
    fulfillment_status = get_key_by_value(status_insales_to_db, key_order.status)
    order_dict = {'order':
                  {
                      # "responsible_user_id": responsible_user_id,
                      "fulfillment_status": fulfillment_status
                   }}
    if key_order.status == Status.SUCCESS:
        order_dict['order']['financial_status'] = get_key_by_value(financial_status_to_db, True)
    elif key_order.status == Status.CANCELLED:
        order_dict['order']['financial_status'] = get_key_by_value(financial_status_to_db, False)
    return order_dict


@retry(stop_after_delay=300)
def send_order_backoffice(order_id: int, data: dict):
    try:
        salon.write_order(order_id, data)
    except Exception as e:
        logger.error(f'ERROR updating Insales order {order_id} | {str(e)}')
    else:
        logger.info(f'SUCCESS updating Insales order {order_id}')


@logger.catch
@app.route('/key_crm', methods=['GET', 'POST'])
def process_request():
    try:
        key_order = OrderKeyCrmShort(**request.json)
    except Exception as e:
        send_service_tg_message(f"Ошибка в программе {__file__}\n{str(e)}")
    else:
        logger.info(f'Got webhook for order: {key_order.key_crm_id}')
        with Session.begin() as session:
            db_order = session.query(UkrsalonOrderDB).filter_by(key_crm_id=key_order.key_crm_id).first()
            if db_order is not None:
                logger.info(f'FOUND in DB order {key_order.key_crm_id}')
                db_order.status_id = key_order.status.value
                db_order.manager_id = key_order.manager_id
                if key_order.status == Status.SUCCESS:
                    db_order.is_paid = True
                elif key_order.status == Status.CANCELLED:
                    db_order.is_paid = False

                order_dict = make_dict_for_request(key_order=key_order)
                logger.info(f'Updating Insales order {db_order.insales_id} with {order_dict} ...')
                send_order_backoffice(db_order.insales_id, order_dict)

            else:
                logger.info(f'not found in DB order {key_order.key_crm_id}')

        return {'message': 'ok'}, 200


# @app.route('/insales_new_order', methods=['POST'])
# def process_new_order():
#     try:
#         print(request.data)
#         print('\n\n\n')
#         print(request.json)
#     except Exception as e:
#         print(f"Ошибка в программе {__file__}\n{str(e)}")
#     return {'message': 'ok'}, 200


if __name__ == '__main__':
    print('Starting in_server for RECEIVING CRM Webhooks')
    if constants.IS_PRODUCTION_SERVER:
        serve(app, host='0.0.0.0', port=55055, threads=4)
    else:
        app.run(host='0.0.0.0', port=55055, debug=True)


