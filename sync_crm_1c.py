import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import constants
from api.key_crm_api import KeyCRM
from db.db_init import Session
from db.models import Order1CDB, PromCPARefundQueueDB, PromOrderDB
from db.sql_init import add_ttn_to_db
from loguru import logger
from messengers import send_service_tg_message
from parse.ai import ai_reorder_names
from parse.parse_key_crm_order import (
    Order1CBuyer,
    Order1CPostupleniye,
    Order1CReturnTovarov,
    Order1CSupplier,
    Order1CSupplierPromCommissionOrder,
    Order1CSupplierUpdate,
    ProductBuyer,
    ProductCommissionProSale,
    ProductCommissionProSaleFreeDelivery
)
from retry import retry
from send_sms import send_ttn_sms

crm = KeyCRM(constants.KEY_CRM_API_KEY)
bad_orders = []
reload_file = Path(__file__).with_suffix('.reload')
Path(constants.json_orders_for_1c_path).mkdir(parents=True, exist_ok=True)
Path(constants.json_archive_1C_path).mkdir(parents=True, exist_ok=True)

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


def find_childs_products(crm_order: dict, all_orders: list[dict]) -> list[ProductBuyer]:
    children_products = []
    skus = [product['sku'] for product in crm_order['products']]
    for curr_order in all_orders:
        if curr_order['parent_id'] == crm_order['id']:  # found child of the order
            for product in curr_order['products']:
                if product['sku'] not in skus:
                    children_products.append(ProductBuyer(**product))
                    skus.append(product['sku'])
    return children_products


def normalize_fio(fio: str) -> str:
    try:
        new_fio = ai_reorder_names(fio)
    except Exception as e:
        logger.error(f'AI failed to reorder names in {fio} | {str(e)}')
        return fio
    else:
        if not new_fio:
            logger.info(f'AI did not recognized proper names in {fio}')
            return fio
        elif new_fio != fio:
            logger.info(f'AI changed {fio} to {new_fio}')
            return ' '.join([word.capitalize() for word in new_fio.split(' ')])
        else:
            logger.info('AI left name the same')
            return fio


def create_json_file(
    order: Order1CBuyer | Order1CSupplierPromCommissionOrder | Order1CPostupleniye, include_keys=None, exclude_keys=None
):
    if type(order) is Order1CBuyer and constants.IS_PRODUCTION_SERVER:
        order.buyer.full_name = normalize_fio(order.buyer.full_name)
    order_dict = order.model_dump(mode='json', include=include_keys, exclude=exclude_keys)
    # order_dict = transform_order_dict_for_1c(order_dict)
    text = json.dumps(order_dict, ensure_ascii=False, indent=4)
    json_file = f'{order.key_crm_id}_{order.action}_{datetime.now().timestamp()}.json'
    (Path(constants.json_orders_for_1c_path) / json_file).write_text(data=text, encoding='utf-8')
    (Path(constants.json_archive_1C_path) / json_file).write_text(data=text, encoding='utf-8')
    if type(order) is not Order1CSupplierUpdate:
        logger.info(f'Created JSON file for {order}')
    else:
        add_text = f'TTN to {order.tracking_code}' if order.tracking_code else f'Supplier_id to {order.supplier_id}'
        logger.info(f'Created JSON file for order {order} and Updated {add_text} for Supplier order')


def add_to_track_and_sms(order: Order1CSupplier, old_ttn_number: Optional[str] = None):
    phone = order.buyer.phone if order.shipping.recipient_phone is None else order.shipping.recipient_phone
    fio = order.buyer.full_name if order.shipping.recipient_full_name is None else order.shipping.recipient_full_name
    if add_ttn_to_db(ttn_number=order.tracking_code,
                     shop_sql_id=order.shop_sql_id,
                     fio=fio,
                     phone=phone,
                     manager=order.manager,
                     old_ttn_number=old_ttn_number
                     ):
        send_ttn_sms(phone=phone, tracking_code=order.tracking_code, shop_sql_id=order.shop_sql_id)


def format_date_time(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def make_time_interval(minutes: int) -> str:
    return f'{format_date_time(datetime.now() - timedelta(minutes=minutes))}, {format_date_time(datetime.now())}'


@retry(stop_after_delay=120)
def get_active_orders() -> list:
    orders = []
    r = crm.get_stages()['data']
    active_stages = [stage_dict['id'] for stage_dict in r if not stage_dict['is_closing_order']]
    # for stage in constants.KEY_ACTIVE_STAGES:
    for stage in active_stages:
        stage_orders = crm.get_orders(last_orders_amount=0, filter={'status_id': stage})
        print(f'{len(stage_orders)} orders for stage {stage}\n')
        orders += stage_orders
    return orders


@retry(stop_after_delay=120)
def get_completed_orders() -> list:
    orders = crm.get_orders(
        last_orders_amount=constants.KEY_GET_LAST_ACTIVE_ORDERS,
        filter={'status_id': constants.order_completed_stage_id},
    )
    print(f'{len(orders)} orders for Completed stage {constants.order_completed_stage_id}\n')
    return orders


@retry(stop_after_delay=120)
def get_last_created_orders(minutes: int) -> list:
    my_filter = {'created_between': make_time_interval(minutes + constants.KEY_TIME_SHIFT)}
    # my_filter = {'created_between': '2024-05-01 00:00:00, 2025-04-25 23:59:59'} #  for getting all orders from date
    orders = crm.get_orders(last_orders_amount=0, filter=my_filter)
    print(
        f'{len(orders)} orders were CREATED during last {minutes} minutes (time shift = {constants.KEY_TIME_SHIFT})\n'
    )
    return orders


@retry(stop_after_delay=120)
def get_last_modified_orders(minutes: int) -> list:
    my_filter = {'updated_between': make_time_interval(minutes + constants.KEY_TIME_SHIFT)}
    orders = crm.get_orders(last_orders_amount=0, filter=my_filter)
    print(
        f'{len(orders)} orders were MODIFIED during last {minutes} minutes (time shift = {constants.KEY_TIME_SHIFT})\n'
    )
    return orders


def is_order_valid(order: Order1CBuyer) -> bool:
    """Checks if a client order is valid for processing."""
    return order.push_to_1C and order.manager and order.buyer and order.buyer.phone and not order.buyer.has_duplicates


def add_order_to_db(order: Order1CBuyer | Order1CSupplier | Order1CSupplierPromCommissionOrder) -> bool:
    """
    Adds the order to the database if it doesn't exist yet.
    :param order: The order to add to the database.
    :return: True if the order was added, False if it already existed.
    """
    with Session.begin() as session:
        if session.query(Order1CDB).filter_by(key_crm_id=order.key_crm_id, document_type=order.document_type).first():
            logger.info(f'DOESN\'t add order to db (already exists) key_crm_id: {order.key_crm_id}, '
                        f'type: {order.document_type.value}')
            return False
        if type(order) is Order1CBuyer:
            session.add(Order1CDB(key_crm_id=order.key_crm_id, document_type=order.document_type))
        else:
            session.add(
                Order1CDB(
                    key_crm_id=order.key_crm_id,
                    parent_id=order.parent_id,
                    document_type=order.document_type,
                    tracking_code=order.tracking_code,
                    supplier_id=order.supplier_id,
                )
            )
        logger.info(f'Added Order {order} to db')
        return True
        


def process_new_buyer_order(order: Order1CBuyer):
    if add_order_to_db(order):
        create_json_file(order)


def process_new_supplier_order(order: Order1CSupplier | Order1CSupplierPromCommissionOrder):
    if order.parent_id is None:
        order.parent_id = order.key_crm_id
    if add_order_to_db(order):
        create_json_file(order, exclude_keys={'buyer', 'shipping', 'payment'})

    if order.tracking_code:
        add_to_track_and_sms(order=order)


def process_existing_supplier_order(order: Order1CSupplierUpdate, db_order: Order1CDB):
    if order.tracking_code and order.tracking_code != db_order.tracking_code:  # order tracking code is new or changed
        add_to_track_and_sms(order=order, old_ttn_number=db_order.tracking_code)
        order.supplier_id = None
        db_order.tracking_code = order.tracking_code
        create_json_file(order, include_keys={'action', 'key_crm_id', 'tracking_code', 'supplier_id'})
    elif order.supplier_id and not db_order.supplier_id:  # but valid supplier number is not in db
        order.tracking_code = None
        db_order.supplier_id = order.supplier_id
        create_json_file(order, include_keys={'action', 'key_crm_id', 'tracking_code', 'supplier_id'})


def make_supplier_comission_orders(buyer_order: Order1CBuyer):
    with Session.begin() as session:
        prom_order = session.query(PromOrderDB).filter_by(order_id=buyer_order.source_uuid).first()
        if prom_order is not None:  # if order at Prom orders
            if prom_order.cpa_commission > 0:  # if order has CPA commission
                commission_order = Order1CSupplierPromCommissionOrder(
                    key_crm_id=f'{prom_order.order_id}',
                    parent_id=buyer_order.key_crm_id,
                    supplier=f'Просейл {prom_order.shop}',
                    products=[ProductCommissionProSale(price=prom_order.cpa_commission)],
                    shop=prom_order.shop,
                )
                process_new_supplier_order(commission_order)
                make_postupleniye_for_commission_order(commission_order)

            if prom_order.delivery_commission > 0:  # if order has delivery commission
                commission_order = Order1CSupplierPromCommissionOrder(
                    key_crm_id=f'{prom_order.order_id}_fd',  # free delivery
                    parent_id=buyer_order.key_crm_id,
                    supplier=f'Просейл {prom_order.shop}',
                    products=[ProductCommissionProSaleFreeDelivery(price=prom_order.delivery_commission)],
                    shop=prom_order.shop,
                )
                process_new_supplier_order(commission_order)
                make_postupleniye_for_commission_order(commission_order)


def make_postupleniye_for_commission_order(commission_order: Order1CSupplierPromCommissionOrder):
    postupleniye = Order1CPostupleniye(
        key_crm_id=commission_order.key_crm_id,
        parent_id=commission_order.key_crm_id,
        supplier=commission_order.supplier,
        products=commission_order.products,
    )
    if add_order_to_db(postupleniye):
        create_json_file(postupleniye)


def make_vozvrat_tovarov_for_commission_posupleniye(prom_cpa_refund: PromCPARefundQueueDB):
    return_tovarov = Order1CReturnTovarov(
        key_crm_id=str(prom_cpa_refund.order_id),
        parent_id=str(prom_cpa_refund.order_id),
        supplier=f'Просейл {prom_cpa_refund.shop}',
        products=[ProductCommissionProSale(price=prom_cpa_refund.cpa_commission)],
    )
    if add_order_to_db(return_tovarov):
        create_json_file(return_tovarov)


@logger.catch
def main():
    crm_orders = get_last_modified_orders(constants.KEY_TIME_INTERVAL_TO_CHECK)
    # crm_orders = get_last_created_orders(constants.KEY_TIME_INTERVAL_TO_CHECK)
    # crm_orders = crm.get_orders(last_orders_amount=constants.KEY_MAX_PROCESSING_ORDERS)
    # crm_orders = get_active_orders() + get_completed_orders()
    print(f'Got {len(crm_orders)} orders')
    if len(crm_orders) > constants.KEY_MAX_PROCESSING_ORDERS:
        logger.error('Too many orders (more than {constants.KEY_MAX_PROCESSING_ORDERS}) to process in CRM')
    process_orders(crm_orders)
    process_cpa_refunds()


def process_orders(crm_orders: list[dict]):
    with Session.begin() as session:
        for order_dict in crm_orders:
            try:
                order = Order1CBuyer(**order_dict)
            except Exception as e:
                if order_dict['id'] not in bad_orders:
                    logger.error(f'Error {e} parsing order: {order_dict["id"]}')
                    bad_orders.append(order_dict['id'])
                continue

            if not is_order_valid(order):
                continue  # skip some not properly filled orders

            if not order.parent_id:  # it is Buyer order and POSSIBLY Supplier order
                db_order = session.query(Order1CDB).filter_by(key_crm_id=order.key_crm_id, parent_id=None).first()
                if db_order is None:  # if order doesn't exist in db
                    for product in find_childs_products(order_dict, crm_orders):
                        order.products.append(product)  # adding child products to order
                    process_new_buyer_order(order)
                    make_supplier_comission_orders(order)   # untab this line for testing purposes

            if order.supplier:   # Supplier present, this is a Supplier order or also a Supplier order
                order = Order1CSupplier(**order_dict)
                db_order = session.query(Order1CDB).filter(Order1CDB.key_crm_id == order.key_crm_id,
                                                           Order1CDB.parent_id.isnot(None)).first()
                if db_order is None:  # if order doesn't exist in db
                    process_new_supplier_order(order=order)
                else:  # if order exists in db
                    order = Order1CSupplierUpdate(**order_dict)
                    process_existing_supplier_order(order=order, db_order=db_order)


def process_cpa_refunds():
    with Session.begin() as session:
        all_cpa_refunds = session.query(PromCPARefundQueueDB).all()
        for cpa_refund in all_cpa_refunds:
            q = session.query(Order1CDB).filter_by(key_crm_id=str(cpa_refund.order_id)).first()
            if q is not None:
                make_vozvrat_tovarov_for_commission_posupleniye(cpa_refund)
                session.delete(cpa_refund)


if __name__ == '__main__':
    logger.info(f'STARTING {__file__}')
    while True:
        print('Getting CRM orders for 1C...')
        main()
        if reload_file.exists():
            reload_file.unlink(missing_ok=True)
            logger.info(f'SHUTTING DOWN {__file__}')
            exit(0)
        print(f'Sleeping {constants.time_to_sleep_crm_1c} sec\n')
        time.sleep(constants.time_to_sleep_crm_1c)
        # time.sleep(3600)  # for testing purposes, remove in production
