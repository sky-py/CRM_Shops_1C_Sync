import sys
from pathlib import Path

import constants
import uvicorn
from api.insales_api import Insales
from db.db_init_async import Session_async
from db.models import UkrsalonOrderDB
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from parse.parse_constants import *
from parse.parse_key_crm_order import OrderKeyCrmShort
from retry import retry
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from sync_ukrsalon_crm import process_order, send_message
from telegram.sender_sync import send_service_tg_message


app = FastAPI()
salon = Insales(constants.UKRSALON_URL)
reload_file = Path(__file__).with_suffix('.reload')


def init_logger() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
               level='DEBUG', backtrace=True, diagnose=True)
    logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
               level='ERROR')


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, e: StarletteHTTPException):
    logger.error(f'[HTTP ERROR] {e}')
    return JSONResponse(status_code=e.status_code, content={'status': 'error', 'message': str(e.detail)})


@app.exception_handler(Exception)
async def handle_exception(request: Request, e: Exception):
    logger.exception(f'[GLOBAL ERROR] {e}')
    return JSONResponse(status_code=500, content={'status': 'error', 'message': 'Internal Server Error'})


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


async def send_order_backoffice(order_id: int, data: dict):
    logger.info(f'START updating Insales order {order_id}')
    await salon.write_order(order_id, data)
    logger.info(f'SUCCESS updating Insales order {order_id}')


@app.post('/key_crm')
async def process_request(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        send_service_tg_message(f"ERROR: not json data in key_crm webhook {__file__}\n{str(e)}")
        raise
    else:
        logger.debug(f'Got CRM webhook data: {data}')

    try:
        key_order = OrderKeyCrmShort(**data)
    except Exception as e:
        send_service_tg_message(f"ERROR parsing key_crm webhook data {__file__}\n{str(e)}")
        raise
    else:
        logger.info(f'Got webhook for order: {key_order.key_crm_id}')

    async with Session_async.begin() as session:
        db_order = (
            await session.execute(select(UkrsalonOrderDB).filter_by(key_crm_id=key_order.key_crm_id))
        ).scalars().first()
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
            await send_order_backoffice(db_order.insales_id, order_dict)

        else:
            logger.info(f'not found in DB order {key_order.key_crm_id}')

    return {'message': 'ok'}


@app.post('/ukrsalon_orders')
async def process_ukrsalon_orders(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        send_service_tg_message(f"ERROR: not json data in ukrsalon_orders webhook {__file__}\n{str(e)}")
        raise
    else:
        logger.debug(f'Got Ukrsalon order {data['number']}')

    async with Session_async.begin() as session:
        notification = await process_order(data, session)

    if notification is not None and notification[0].status_id != Status.CANCELLED.value:
        await send_message(*notification)

    return {'message': 'ok'}


if __name__ == '__main__':
    init_logger()
    logger.info('Starting server for RECEIVING CRM Webhooks')
    try:
        uvicorn.run(app, host='0.0.0.0', port=constants.CALLBACK_CRM_PORT, reload=not constants.IS_PRODUCTION_SERVER)
    except Exception as e:
        logger.exception(f'Unexpected error in {__file__}: {e}')
    finally:
        reload_file.unlink(missing_ok=True)
        logger.info(f'SHUTTING DOWN {__file__}')
