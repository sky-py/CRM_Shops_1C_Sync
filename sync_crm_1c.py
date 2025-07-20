import json
import time
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Literal
import constants
from api.key_crm_api import KeyCRM
from constants import IS_PRODUCTION_SERVER
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
    ProductCommissionProSaleFreeDelivery,
    FakeProduct
)
from parse.parse_constants import TTN_SENT_BY_CAR, FAKE_SUPPLIER, PromStatus
from retry import retry
from send_sms import send_ttn_sms

crm = KeyCRM(constants.CRM_API_KEY)
parse_errors_orders_ids = []
reload_file = Path(__file__).with_suffix('.reload')
Path(constants.json_orders_for_1c_path).mkdir(parents=True, exist_ok=True)
Path(constants.json_archive_1C_path).mkdir(parents=True, exist_ok=True)

logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='INFO', backtrace=True, diagnose=True)
logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='ERROR')


def find_all_tree_orders_any_level(order_dict: dict, crm_orders: list[dict]) -> list[dict]:
    orders_map = {order['id']: order for order in crm_orders}
    children_map = {}
    for order in crm_orders:
        children_map.setdefault(order['parent_id'], []).append(order['id'])

    result = []
    stack = [order_dict['id']]

    while stack:
        curr_node_id = stack.pop()
        result.append(orders_map[curr_node_id])

        if curr_node_id in children_map:
            stack.extend(children_map[curr_node_id])

    return result


def find_unique_tree_products(tree_orders: list[dict]) -> list[dict]:
    unique_products = []
    skus = []
    for order in tree_orders:
        for product in order['products']:
            if product['sku'] not in skus:
                unique_products.append(product)
                skus.append(product['sku'])
    return unique_products
    

def find_root_order_id(order_dict: dict, crm_orders: list[dict]) -> int:
    orders_map = {order['id']: order for order in crm_orders}
    curr_order_id = order_dict['id']
    while True:
        if curr_order := orders_map.get(curr_order_id):
            if curr_order['parent_id'] is None:
                return curr_order['id']
            else:
                curr_order_id = curr_order['parent_id']
        else:
            return find_root_order_id_via_api(curr_order_id)
    
    
    
def find_root_order_id_via_api(order_id: int) -> int:
    order = crm.get_order(order_id)
    while True:
        if order['parent_id'] is None:
            return order['id']
        else:
            order = crm.get_order(order['parent_id'])
    


def normalize_fio(fio: str) -> str:
    if not IS_PRODUCTION_SERVER:
        return fio

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


def create_json_file(order: Order1CBuyer | Order1CSupplierPromCommissionOrder | Order1CPostupleniye,
                     include_keys=None, exclude_keys=None):
    if type(order) is Order1CBuyer:
        order.buyer.full_name = normalize_fio(order.buyer.full_name)
    text = json.dumps(order.model_dump(mode='json', include=include_keys, exclude=exclude_keys),
                      ensure_ascii=False, indent=4)
    json_file = f'{order.key_crm_id}_{order.action}_{datetime.now().timestamp()}.json'
    (Path(constants.json_orders_for_1c_path) / json_file).write_text(data=text, encoding='utf-8')
    shutil.copyfile((Path(constants.json_orders_for_1c_path) / json_file), (Path(constants.json_archive_1C_path) / json_file))
    if order.action != 'update_supplier_order':
        logger.info(f'Created JSON file for {order.document_type.value}, key_crm_id = {order.key_crm_id}')
    else:
        logger.info(f'Created JSON Update file for Supplier order key_crm_id = {order.key_crm_id}')


def add_to_track_and_sms(order: Order1CSupplier, old_ttn_number: Optional[str] = None):
    if not order.send_sms:
        logger.info(f'SMS skipped for order {order.key_crm_id}')
        return
    # try:
    #     if int(order.key_crm_id) < 79000:
    #         logger.info(f'SMS skipped for order {order.key_crm_id}')
    #         return
    # except:
    #     pass
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


@retry(stop_after_delay=120)
def get_active_orders() -> list:
    """
    Returns list of all active orders from CRM.
    Active orders are orders that are not in closing stages.
    """
    orders = []
    r = crm.get_stages()['data']
    active_stages = [stage_dict['id'] for stage_dict in r if not stage_dict['is_closing_order']]
    for stage in active_stages:
        stage_orders = crm.get_orders(last_orders_amount=0, filter={'status_id': stage})
        print(f'{len(stage_orders)} orders for stage {stage}\n')
        orders += stage_orders
    return orders


@retry(stop_after_delay=120)
def get_orders_by_stage(stage_id: int = constants.CRM_ORDER_COMPLETED_STAGE_ID) -> list:
    """
    Returns list of all completed orders from CRM.
    Completed orders are orders that have reached the completed stage.
    """
    orders = crm.get_orders(
        last_orders_amount=constants.CRM_GET_LAST_ORDERS,
        filter={'status_id': stage_id},
    )
    return orders


@retry(stop_after_delay=120)
def get_interval_orders(*, start: datetime,
                        end: Optional[datetime] = None, 
                        filter_on: Literal['created', 'updated'] = 'updated') -> list:
    end = end or datetime.now(timezone.utc)
    time_window = f'{format_date_time(start)}, {format_date_time(end)}'
    filter_kwargs = {f'{filter_on}_between': time_window}
    orders = crm.get_orders(last_orders_amount=0, filter=filter_kwargs)
    print(f'{len(orders)} orders were {filter_kwargs} UTC')
    return orders


def is_order_proper_filled(order: Order1CBuyer) -> bool:
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
        order_copy = order.model_copy(deep=True)
        order_copy.tracking_code = None
        order_copy.supplier_id = None
        create_json_file(order_copy, exclude_keys={'buyer', 'shipping', 'payment'})

    if order.tracking_code or order.supplier_id:
        order_update = order.model_copy(deep=True)
        order_update.action = 'update_supplier_order'
        create_json_file(order_update, include_keys={'action', 'key_crm_id', 'tracking_code', 'supplier_id'})
        if order.tracking_code:
            add_to_track_and_sms(order=order)


def process_existing_supplier_order(order: Order1CSupplierUpdate, db_order: Order1CDB):
    updated = False
    if order.tracking_code and order.tracking_code != db_order.tracking_code:  # order tracking code is new or changed
        add_to_track_and_sms(order=order, old_ttn_number=db_order.tracking_code)
        db_order.tracking_code = order.tracking_code
        updated = True
    if order.supplier_id != db_order.supplier_id:
        db_order.supplier_id = order.supplier_id
        updated = True
    if updated:
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


def update_crm_order(order: Order1CBuyer):
    if not IS_PRODUCTION_SERVER:
        return
    data = {'products': [product.model_dump(include={'sku', 'price'}) for product in order.products],
            'discount_amount': 0}
    try:
        crm.update_order(order_id=order.key_crm_id, data=data)
    except:
        logger.error(f'Error updating crm order {order.key_crm_id}')


def is_order_cancelled(order: Order1CBuyer) -> bool:
    return order.stage_group_id == constants.CRM_ORDER_CANCELLED_STAGE_GROUP_ID


def is_prom_order_has_unreturned_CPA_commission(prom_order: PromOrderDB) -> bool:
    return prom_order.status == PromStatus.CANCELLED and prom_order.cpa_commission > 0 and not prom_order.cpa_is_refunded


def check_and_process_unreturned_commission(order: Order1CBuyer, order_dict: dict) -> None:
    with Session.begin() as session:
        prom_order = session.query(PromOrderDB).filter_by(order_id=order.source_uuid).first()
        if prom_order is None:  
            return
        if is_prom_order_has_unreturned_CPA_commission(prom_order):    # if order has unreturned CPA commission
            logger.info(f'Start processing unreturned CPA commission for order {order.key_crm_id} ({prom_order.shop}: {order.source_uuid})')
            order.products = [FakeProduct()]
            order.proveden = True
            msg = f'Заказ для учёта комиссии просейл по заказу {prom_order.shop}: {order.source_uuid}'
            order.manager_comment = f'{order.manager_comment}\n{msg}' if order.manager_comment else msg
            process_new_buyer_order(order)
            
            supplier_order = Order1CSupplier(**order_dict)
            supplier_order.products = [FakeProduct()]
            supplier_order.supplier = FAKE_SUPPLIER
            supplier_order.tracking_code = TTN_SENT_BY_CAR
            supplier_order.send_sms = False
            process_new_supplier_order(supplier_order)
            
            commission_order = Order1CSupplierPromCommissionOrder(
                key_crm_id=f'{prom_order.order_id}',
                parent_id=order.key_crm_id,
                supplier=f'Просейл {prom_order.shop}',
                products=[ProductCommissionProSale(price=prom_order.cpa_commission)],
                shop=prom_order.shop,
            )
            process_new_supplier_order(commission_order)
            make_postupleniye_for_commission_order(commission_order)


@logger.catch
def main():
    start_time = datetime.now(timezone.utc) - timedelta(minutes=constants.CRM_MINUTES_INTERVAL_TO_CHECK)
    crm_orders = get_interval_orders(start=start_time)
    # crm_orders = get_interval_orders(start=datetime(year=2024, month=5, day=1, tzinfo=timezone.utc), filter_on='created') 
    # crm_orders = get_active_orders() + get_orders_by_stage()
    if len(crm_orders) > constants.CRM_MAX_PROCESSING_ORDERS:
        logger.error(f'Too many orders (more than {constants.CRM_MAX_PROCESSING_ORDERS}) to process in CRM')
    process_orders(crm_orders)
    process_cpa_refunds()


def process_orders(crm_orders: list[dict]):
    with Session.begin() as session:
        for order_dict in crm_orders:
            
            try:
                order = Order1CBuyer(**order_dict)
            except Exception as e:
                if order_dict['id'] not in parse_errors_orders_ids:
                    logger.error(f'Error {e} parsing order: {order_dict['id']}')
                    parse_errors_orders_ids.append(order_dict['id'])
                continue
            
            if not is_order_proper_filled(order) and not is_order_cancelled(order):
                continue  # skip some not properly filled orders

            if not order.parent_id:  # it is Buyer order and POSSIBLY Supplier order
                db_order = session.query(Order1CDB).filter_by(key_crm_id=order.key_crm_id, parent_id=None).first()
                if db_order is None:  # if order doesn't exist in db
                    if is_order_cancelled(order):
                        check_and_process_unreturned_commission(order, order_dict)
                        continue
                    # if order.prices_rounded: # uncomment when CRM fixes update
                    #     update_crm_order(order)
                    tree_orders = find_all_tree_orders_any_level(order_dict, crm_orders)
                    tree_products = find_unique_tree_products(tree_orders)
                    extended_order = order.model_copy(deep=True)
                    extended_order.products = [ProductBuyer(**product) for product in tree_products]
                    process_new_buyer_order(extended_order)
                    make_supplier_comission_orders(order)   # untab this line for testing purposes

            if order.supplier:   # Supplier present, this is a Supplier order or also a Supplier order
                order = Order1CSupplier(**order_dict)
                db_order = session.query(Order1CDB).filter(Order1CDB.key_crm_id == order.key_crm_id,
                                                           Order1CDB.parent_id.isnot(None)).first()
                if db_order is None:  # if order doesn't exist in db
                    root_id = find_root_order_id(order_dict, crm_orders)
                    order.parent_id = str(root_id)
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
        print('Getting CRM orders...')
        main()
        if not IS_PRODUCTION_SERVER:
            exit(0)
        if reload_file.exists():
            reload_file.unlink(missing_ok=True)
            logger.info(f'SHUTTING DOWN {__file__}')
            exit(0)
        print(f'Sleeping {constants.time_to_sleep_crm_1c} sec\n')
        time.sleep(constants.time_to_sleep_crm_1c)
