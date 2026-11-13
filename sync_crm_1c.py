import json
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional
import constants
from api.key_crm_api import KeyCRM
from config.logging import logger_init
from constants import IS_PRODUCTION_SERVER
from db.db_init import Session, Session_Sync
from db.models import (
    CancelledAfter1CNoticeDB,
    Order1CDB,
    PromCPARefundOutbox,
    PromDeliveryCommissionOutbox,
    PromOrderDB,
)
from db.sql_init import add_ttn_to_db
from loguru import logger
from parse.ai import ai_reorder_names
from parse.parse_constants import FAKE_SUPPLIER, TTN_SENT_BY_CAR, Document1C, PromStatus
from parse.parse_key_crm_order import (
    FakeProductBuyer,
    FakeProductSupplier,
    Order1CBuyer,
    Order1CPostupleniye,
    Order1CReturnTovarov,
    Order1CSupplier,
    Order1CSupplierPromCommissionOrder,
    Order1CSupplierUpdate,
    ProductBuyer,
    ProductCommissionProSale,
    ProductCommissionProSaleForOrder,
    ProductCommissionProSaleFreeDelivery,
)
from retry import retry
from send_sms import send_ttn_sms
from sqlalchemy import or_
from telegram.sender_sync import send_service_tg_message, send_tg_message
from tools.rich_log import RichLog


crm = KeyCRM(constants.CRM_API_KEY)
parse_errors_orders_ids = []
last_commission_backfill_date = None
reload_file = Path(__file__).with_suffix('.reload')
last_sync_file = Path(__file__).with_suffix('.last_sync')  # UTC time of the last fully processed CRM window
constants.JSONS_OUT_PATH.mkdir(parents=True, exist_ok=True)
constants.JSONS_ARCHIVE_PATH.mkdir(parents=True, exist_ok=True)


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


def create_json_file(
    order: Order1CBuyer | Order1CSupplierPromCommissionOrder | Order1CPostupleniye, include_keys=None, exclude_keys=None
):
    if type(order) is Order1CBuyer:
        order.buyer.full_name = normalize_fio(order.buyer.full_name)
    text = json.dumps(
        order.model_dump(mode='json', include=include_keys, exclude=exclude_keys), ensure_ascii=False, indent=4
    )
    json_file = f'{order.key_crm_id}_{order.action}_{datetime.now().timestamp()}.json'
    (constants.JSONS_ARCHIVE_PATH / json_file).write_text(data=text, encoding='utf-8')
    (constants.JSONS_OUT_PATH / json_file).write_text(data=text, encoding='utf-8')
    logger.info(f'Created JSON file: {json_file} for order: {order.key_crm_id} type: {order.document_type.value}')


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
    if add_ttn_to_db(
        ttn_number=order.tracking_code,
        shop_sql_id=order.shop_sql_id,
        fio=fio,
        phone=phone,
        manager=order.manager,
        old_ttn_number=old_ttn_number,
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
    r = crm.get_order_stages()['data']
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
    orders = crm.get_orders(last_orders_amount=constants.CRM_GET_LAST_ORDERS, filter={'status_id': stage_id})
    return orders


@retry(stop_after_delay=120)
def get_interval_orders(
    *, start: datetime, end: Optional[datetime] = None, filter_on: Literal['created', 'updated'] = 'updated'
) -> list:
    end = end or datetime.now(timezone.utc)
    time_window = f'{format_date_time(start)}, {format_date_time(end)}'
    filter_kwargs = {f'{filter_on}_between': time_window}
    orders = crm.get_orders(last_orders_amount=0, filter=filter_kwargs)
    rich_log.print_request(f'{len(orders)} orders were received: {filter_kwargs} UTC')
    return orders


def is_product_name_excluded(name: str) -> bool:
    name_words = set(re.findall(r'\w+', name.casefold()))
    return any(
        all(word.casefold() in name_words for word in words)
        for words in constants.CRM_1C_EXCLUDED_PRODUCT_NAME_WORD_GROUPS
    )


def is_order_proper_filled(order: Order1CBuyer) -> bool:
    """Checks if a client order is valid for processing."""
    return (
        order.push_to_1C
        and order.manager
        and order.buyer
        and order.buyer.phone
        and not order.buyer.has_duplicates
        and not any(is_product_name_excluded(product.name) for product in order.products)
    )


def add_order_to_db(
    order: Order1CBuyer | Order1CSupplier | Order1CSupplierPromCommissionOrder, session: Session
) -> bool:
    """
    Adds the order to the database if it doesn't exist yet.
    :param order: The order to add to the database.
    :return: True if the order was added, False if it already existed.
    """
    if session.query(Order1CDB).filter_by(key_crm_id=order.key_crm_id, document_type=order.document_type).first():
        logger.info(f'Order {order.key_crm_id} type: {order.document_type.value} already exists. Skipping...')
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
    session.flush()
    logger.info(f'Order: {order.key_crm_id} type: {order.document_type.value} added to db. => {order}')
    return True


def process_new_buyer_order(order: Order1CBuyer, session: Session):
    if add_order_to_db(order, session):
        create_json_file(order)


def process_new_supplier_order(order: Order1CSupplier | Order1CSupplierPromCommissionOrder, session: Session):
    if order.parent_id is None:
        order.parent_id = order.key_crm_id
    if add_order_to_db(order, session):
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


def make_supplier_comission_orders(buyer_order: Order1CBuyer, session: Session):
    prom_order = session.query(PromOrderDB).filter_by(order_id=buyer_order.source_uuid).first()
    if prom_order is not None:  # if order at Prom orders
        make_prom_commission_orders(prom_order, buyer_order.key_crm_id, session)


def make_prom_commission_orders(
    prom_order: PromOrderDB, parent_id: str, session: Session, include_cpa: bool = True, include_oc: bool = True
):
    """Creates supplier order + postupleniye for Prom commissions. Already existing documents are skipped."""
    if include_cpa and prom_order.cpa_commission > 0:  # if order has CPA commission
        commission_order = Order1CSupplierPromCommissionOrder(
            key_crm_id=f'{prom_order.order_id}',
            parent_id=parent_id,
            supplier=f'Просейл {prom_order.shop}',
            products=[ProductCommissionProSale(price=prom_order.cpa_commission)],
            shop=prom_order.shop,
        )
        process_new_supplier_order(commission_order, session)
        make_postupleniye_for_commission_order(commission_order, session)

    if include_oc and prom_order.order_commission > 0:  # if order has order commission
        commission_order = Order1CSupplierPromCommissionOrder(
            key_crm_id=f'{prom_order.order_id}_oc',  # oc = order commission
            parent_id=parent_id,
            supplier=f'Просейл {prom_order.shop}',
            products=[ProductCommissionProSaleForOrder(price=prom_order.order_commission)],
            shop=prom_order.shop,
        )
        process_new_supplier_order(commission_order, session)
        make_postupleniye_for_commission_order(commission_order, session)


def find_crm_order_by_prom_id(prom_order_id: int) -> Optional[dict]:
    crm_orders = crm.get_orders(filter={'source_uuid': str(prom_order_id)})
    return crm_orders[0] if crm_orders else None


def backfill_cancelled_order_commission(crm_order_dict: dict, order_title: str, session: Session, dry_run: bool) -> bool:
    """
    The fake buyer order for a cancelled order with unreturned Prom commission is normally created when
    process_orders sees the cancelled CRM order. That happens only within CRM_MINUTES_INTERVAL_TO_CHECK after
    the CRM change, and only if Prom status in DB is already CANCELLED. When Prom cancels later, the order
    is never re-read, so retry it here. Returns True if the fake order flow applies to the order.
    """
    if crm_order_dict['parent_id'] or crm_order_dict['status_group_id'] != constants.CRM_ORDER_CANCELLED_STAGE_GROUP_ID:
        return False
    prom_order = session.query(PromOrderDB).filter_by(order_id=int(crm_order_dict['source_uuid'])).first()
    if prom_order is None or not (
        is_prom_order_cancelled_and_has_unreturned_CPA_commission(prom_order)
        or is_prom_order_cancelled_and_has_order_commission(prom_order)
    ):
        return False
    logger.info(f'Commission backfill: cancelled CRM order {crm_order_dict["id"]} for {order_title} => fake order')
    if dry_run:
        return True
    try:
        order = Order1CBuyer(**crm_order_dict)
    except Exception as e:
        logger.error(f'Commission backfill: error parsing CRM order {crm_order_dict["id"]}: {e}')
        return False
    check_and_process_unreturned_commission(order, crm_order_dict, session)
    return True


def backfill_prom_commissions(session: Session, dry_run: bool = False) -> None:
    """
    Prom may assign a commission after the buyer order was already sent to 1C, and then
    make_supplier_comission_orders never sees it. Once a day find recent Prom orders with commission
    but without a commission document in 1C, and create it if the buyer order is already in 1C.
    If the buyer order is not in 1C and the order is cancelled both in CRM and on Prom with commission kept
    by Prom, create the fake buyer order with commission. Other orders are left for the regular flow.
    Documents are created only for orders from the last PROM_COMMISSION_BACKFILL_DAYS. Orders from the last
    PROM_COMMISSION_ALERT_DAYS that are finished but still have no commission in 1C are sent to Telegram.
    """
    now = datetime.now(timezone.utc)
    create_since = now - timedelta(days=constants.PROM_COMMISSION_BACKFILL_DAYS)
    check_since = now - timedelta(days=max(constants.PROM_COMMISSION_ALERT_DAYS, constants.PROM_COMMISSION_BACKFILL_DAYS))
    with session.begin():
        prom_orders = (
            session
            .query(PromOrderDB)
            .filter(
                PromOrderDB.ordered_at >= check_since,
                or_(PromOrderDB.cpa_commission > 0, PromOrderDB.order_commission > 0),
            )
            .all()
        )
        keys = [key for p in prom_orders for key in (str(p.order_id), f'{p.order_id}_oc')]
        existing_keys = {key for (key,) in session.query(Order1CDB.key_crm_id).filter(Order1CDB.key_crm_id.in_(keys))}

        candidates = []  # plain values: ORM objects expire after commit
        for p in prom_orders:
            cpa_key, oc_key = str(p.order_id), f'{p.order_id}_oc'
            # refunded CPA nets to zero on Prom, booking it would only add a commission + return pair
            cpa_missing = p.cpa_commission > 0 and not p.cpa_is_refunded and cpa_key not in existing_keys
            # fake buyer order flow books order commission under the plain key, so check both keys
            oc_missing = p.order_commission > 0 and oc_key not in existing_keys and cpa_key not in existing_keys
            if cpa_missing or oc_missing:
                candidates.append(
                    MissingCommission(
                        prom_order_id=p.order_id,
                        shop=p.shop,
                        prom_status=p.status,
                        can_create=p.ordered_at >= create_since,
                        cpa_missing=cpa_missing,
                        oc_missing=oc_missing,
                        amount=(p.cpa_commission if cpa_missing else 0) + (p.order_commission if oc_missing else 0),
                    )
                )

    created = 0
    alerts = []
    for c in candidates:
        order_title = f'{c.shop}:{c.prom_order_id}'
        try:
            crm_order_dict = find_crm_order_by_prom_id(c.prom_order_id)
        except Exception as e:
            logger.info(f'Commission backfill: failed to find CRM order for {order_title} | {e}')
            continue
        if crm_order_dict is None:
            logger.info(f'Commission backfill: CRM order not found for {order_title}')
            if c.prom_status in (PromStatus.SUCCESS, PromStatus.CANCELLED):
                alerts.append((c, None, 'заказа нет в CRM'))
            continue
        crm_order_id = crm_order_dict['id']

        with session.begin():
            buyer_order_in_1c = (
                session
                .query(Order1CDB)
                .filter_by(key_crm_id=str(crm_order_id), parent_id=None, document_type=Document1C.CLIENT_ORDER)
                .first()
            )
            if buyer_order_in_1c is None:
                if c.can_create and backfill_cancelled_order_commission(crm_order_dict, order_title, session, dry_run):
                    created += 1
                    continue
                logger.info(f'Commission backfill: CRM order {crm_order_id} for {order_title} is not in 1C yet')
                if reason := get_not_in_1c_alert_reason(crm_order_dict, now):
                    alerts.append((c, crm_order_id, reason))
                continue

            if not c.can_create:
                alerts.append((c, crm_order_id, 'заказ клиента в 1С, комиссия не проведена'))
                continue

            what = []
            if c.cpa_missing:
                what.append('CPA')
            if c.oc_missing:
                what.append('order commission')
            logger.info(f'Commission backfill: {order_title} CRM {crm_order_id} => {" + ".join(what)} {c.amount}')
            created += 1
            if dry_run:
                continue
            prom_order = session.get(PromOrderDB, c.prom_order_id)
            make_prom_commission_orders(
                prom_order, str(crm_order_id), session, include_cpa=c.cpa_missing, include_oc=c.oc_missing
            )

    logger.info(f'Commission backfill finished: {created} orders {"would be " if dry_run else ""}processed')
    send_missing_commissions_alert(alerts, dry_run)


@dataclass(slots=True)
class MissingCommission:
    prom_order_id: int
    shop: str
    prom_status: PromStatus
    can_create: bool  # order is recent enough to create 1C documents automatically
    cpa_missing: bool
    oc_missing: bool
    amount: float


def get_not_in_1c_alert_reason(crm_order_dict: dict, now: datetime) -> Optional[str]:
    """
    Orders still in work (e.g. in production for weeks) are not reported. Completed orders are reported at once:
    the manager forgot to send them to 1C. Cancelled ones only after PROM_CANCELLED_ALERT_DELAY_DAYS, when Prom
    won't refund the commission anymore and the fake order should have been created automatically.
    """
    status_group = crm_order_dict['status_group_id']
    if status_group == constants.CRM_ORDER_COMPLETED_STAGE_GROUP_ID:
        return 'заказ выполнен, но не отправлен в 1С (нет отметки «Заказ 1С»)'
    if status_group == constants.CRM_ORDER_CANCELLED_STAGE_GROUP_ID:
        changed_at = crm_order_dict.get('status_changed_at') or crm_order_dict.get('updated_at')
        try:
            cancelled_days = (now - datetime.fromisoformat(changed_at)).days
        except (TypeError, ValueError):
            cancelled_days = constants.PROM_CANCELLED_ALERT_DELAY_DAYS
        if cancelled_days >= constants.PROM_CANCELLED_ALERT_DELAY_DAYS:
            return (
                f'заказ отменён в CRM {cancelled_days} дн. назад, по нашей базе Prom комиссию не вернул, '
                f'фиктивный заказ не создан'
            )
    return None


def send_missing_commissions_alert(alerts: list[tuple[MissingCommission, Optional[int], str]], dry_run: bool) -> None:
    if not alerts:
        return
    total = round(sum(c.amount for c, _, _ in alerts), 2)
    lines = [f'Комиссии Prom без документа в 1С: {len(alerts)} заказ(ов) на {total} грн']
    for c, crm_order_id, reason in sorted(alerts, key=lambda a: (a[0].shop, a[0].prom_order_id)):
        crm_link = f'https://ukrsalon.keycrm.app/app/orders/view/{crm_order_id}' if crm_order_id else 'нет в CRM'
        lines.append(f'\n{c.shop} {c.prom_order_id} — {round(c.amount, 2)} грн\n{reason}\nCRM: {crm_link}')
    text = '\n'.join(lines)
    logger.info(f'Commission backfill: alert => {text}')
    if not dry_run:
        send_service_tg_message(text)


def make_postupleniye_for_commission_order(commission_order: Order1CSupplierPromCommissionOrder, session: Session):
    postupleniye = Order1CPostupleniye(
        key_crm_id=commission_order.key_crm_id,
        parent_id=commission_order.key_crm_id,
        supplier=commission_order.supplier,
        products=commission_order.products,
    )
    if add_order_to_db(postupleniye, session):
        create_json_file(postupleniye)


def make_vozvrat_tovarov_for_commission_posupleniye(prom_cpa_refund: PromCPARefundOutbox, session: Session):
    return_tovarov = Order1CReturnTovarov(
        key_crm_id=str(prom_cpa_refund.order_id),
        parent_id=str(prom_cpa_refund.order_id),
        supplier=f'Просейл {prom_cpa_refund.shop}',
        products=[ProductCommissionProSale(price=prom_cpa_refund.cpa_commission)],
    )
    if add_order_to_db(return_tovarov, session):
        create_json_file(return_tovarov)


def update_crm_order(order: Order1CBuyer):
    if not IS_PRODUCTION_SERVER:
        return
    data = {
        'products': [product.model_dump(include={'sku', 'price'}) for product in order.products],
        'discount_amount': 0,
    }
    try:
        crm.update_order(order_id=order.key_crm_id, data=data)
    except Exception as e:
        logger.error(f'Error updating crm order {order.key_crm_id}: {e}')


def is_order_cancelled(order: Order1CBuyer) -> bool:
    return order.stage_group_id == constants.CRM_ORDER_CANCELLED_STAGE_GROUP_ID


def is_prom_order_cancelled_and_has_unreturned_CPA_commission(prom_order: PromOrderDB) -> bool:
    return (
        prom_order.status == PromStatus.CANCELLED and prom_order.cpa_commission > 0 and not prom_order.cpa_is_refunded
    )


def is_prom_order_cancelled_and_has_order_commission(prom_order: PromOrderDB) -> bool:
    return prom_order.status == PromStatus.CANCELLED and prom_order.order_commission > 0


def check_and_process_unreturned_commission(order: Order1CBuyer, order_dict: dict, session: Session) -> None:
    prom_order = session.query(PromOrderDB).filter_by(order_id=order.source_uuid).first()
    if prom_order is None:
        return

    products = []
    if is_prom_order_cancelled_and_has_unreturned_CPA_commission(prom_order):
        products.append(ProductCommissionProSale(price=prom_order.cpa_commission))
    if is_prom_order_cancelled_and_has_order_commission(prom_order):
        products.append(ProductCommissionProSaleForOrder(price=prom_order.order_commission))

    if products:
        logger.info(
            f'Start processing unreturned CPA commission or order commission for order {order.key_crm_id} ({prom_order.shop}: {order.source_uuid})'
        )
        order.products = [FakeProductBuyer()]
        order.proveden = True
        msg = f'Заказ для учёта комиссии за заказ пром и (возможно) невозвращенной комиссии по просейл по заказу {prom_order.shop}: {order.source_uuid}'
        order.manager_comment = f'{order.manager_comment}\n{msg}' if order.manager_comment else msg
        process_new_buyer_order(order, session)

        supplier_order = Order1CSupplier(**order_dict)
        supplier_order.products = [FakeProductSupplier()]
        supplier_order.supplier = FAKE_SUPPLIER
        supplier_order.tracking_code = TTN_SENT_BY_CAR
        supplier_order.send_sms = False
        process_new_supplier_order(supplier_order, session)

        commission_order = Order1CSupplierPromCommissionOrder(
            key_crm_id=f'{prom_order.order_id}',
            parent_id=order.key_crm_id,
            supplier=f'Просейл {prom_order.shop}',
            products=products,
            shop=prom_order.shop,
        )
        process_new_supplier_order(commission_order, session)
        make_postupleniye_for_commission_order(commission_order, session)
        mark_cancelled_after_1c_handled(order.key_crm_id, prom_order.order_id, session, is_fake_order=True)


PROM_COMMISSION_KINDS = {
    '': ('ProSale', 'cpa_commission'),
    '_oc': ('оплата за заказ', 'order_commission'),
    '_fd': ('доставка', 'delivery_commission'),
}


def mark_cancelled_after_1c_handled(crm_order_id: str, prom_order_id: int, session: Session, is_fake_order: bool):
    if session.get(CancelledAfter1CNoticeDB, str(crm_order_id)) is None:
        session.add(
            CancelledAfter1CNoticeDB(
                crm_order_id=str(crm_order_id), prom_order_id=prom_order_id, is_fake_order=is_fake_order
            )
        )
        session.flush()


def is_status_changed_since(order_dict: dict, since: Optional[datetime]) -> bool:
    changed_at = order_dict.get('status_changed_at')
    if since is None or not changed_at:
        return False
    try:
        return datetime.fromisoformat(changed_at) >= since
    except ValueError:
        return False


def get_prom_commission_keys_in_1c(prom_order_id: int, crm_order_id: str, session: Session) -> list[str]:
    keys = [f'{prom_order_id}{suffix}' for suffix in PROM_COMMISSION_KINDS]
    rows = (
        session
        .query(Order1CDB.key_crm_id)
        .filter(
            Order1CDB.document_type == Document1C.SUPPLIER_ORDER,
            Order1CDB.parent_id == str(crm_order_id),
            Order1CDB.key_crm_id.in_(keys),
        )
        .all()
    )
    return sorted(row.key_crm_id for row in rows)


def format_fake_price(product: FakeProductBuyer) -> str:
    return f'{product.quantity:g} шт × {product.price:g} грн'.replace('.', ',')


def make_cancelled_after_1c_text(crm_order_id: str, prom_order: PromOrderDB, commission_keys: list[str]) -> str:
    lines = [
        '⚠ Заказ отменён после выгрузки в 1С',
        f'Заказ CRM {crm_order_id} (Prom {prom_order.shop} {prom_order.order_id})',
        f'https://ukrsalon.keycrm.app/app/orders/view/{crm_order_id}',
        '',
        f'В 1С к нему есть комиссия Prom, поставщик «Просейл {prom_order.shop}»:',
    ]
    for key in commission_keys:
        name, field = PROM_COMMISSION_KINDS[key.removeprefix(str(prom_order.order_id))]
        amount = f'{getattr(prom_order, field):.2f}'.replace('.', ',')
        lines.append(f'• {key} — {name} {amount} грн')
    lines += [  # the same result as the fake order flow (FakeProductBuyer, FakeProductSupplier, FAKE_SUPPLIER)
        '',
        'Не удаляйте этот заказ в 1С — вместе с ним удалится комиссия. Вместо удаления:',
        f'1. В заказе клиента {crm_order_id} замените все товары на «{FakeProductBuyer().name}» '
        f'({format_fake_price(FakeProductBuyer())}) и проведите.',
        f'2. В заказе поставщику {crm_order_id} поставьте поставщика «{FAKE_SUPPLIER}» и замените товары '
        f'на «{FakeProductSupplier().name}» ({format_fake_price(FakeProductSupplier())}).',
        f'3. Документы «Просейл {prom_order.shop}» не трогайте. Если Prom вернёт комиссию, '
        f'возврат придёт в 1С автоматически.',
    ]
    return '\n'.join(lines)


def notify_cancelled_after_1c(order: Order1CBuyer, order_dict: dict, session: Session, since: Optional[datetime]):
    """
    When an order already sent to 1C is cancelled, the accountant may delete the client order in 1C together with
    its subordinate documents, including the Prom commission which Prom keeps. The script can't see 1C, so the
    accountant is warned once, at the moment of cancellation, not to delete the commission documents.
    """
    if not order.source_uuid or not is_status_changed_since(order_dict, since):
        return
    if session.get(CancelledAfter1CNoticeDB, str(order.key_crm_id)) is not None:
        return  # already notified, or the commission was created by the fake order flow
    commission_keys = get_prom_commission_keys_in_1c(order.source_uuid, order.key_crm_id, session)
    prom_order = session.query(PromOrderDB).filter_by(order_id=order.source_uuid).first()
    if not commission_keys or prom_order is None:
        return
    mark_cancelled_after_1c_handled(order.key_crm_id, prom_order.order_id, session, is_fake_order=False)
    text = make_cancelled_after_1c_text(order.key_crm_id, prom_order, commission_keys)
    logger.info(f'Order {order.key_crm_id} cancelled after it was sent to 1C, accountant notified => {text}')
    send_tg_message(text, [constants.buh_tg])


def read_last_sync_time() -> Optional[datetime]:
    try:
        return datetime.fromisoformat(last_sync_file.read_text(encoding='utf-8').strip())
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error(f'Cannot read last sync time from {last_sync_file}: {e}')
        return None


def save_last_sync_time(sync_time: datetime) -> None:
    last_sync_file.write_text(sync_time.isoformat(), encoding='utf-8')


def get_sync_start_time(now: datetime) -> datetime:
    """
    Normally CRM changes of the last CRM_MINUTES_INTERVAL_TO_CHECK minutes are read. If the previous successful
    sync was earlier (the script was stopped or failing), start from it, so changes made meanwhile are not lost.
    Catch-up is limited to CRM_MAX_CATCHUP_DAYS.
    """
    start = now - timedelta(minutes=constants.CRM_MINUTES_INTERVAL_TO_CHECK)
    last_sync = read_last_sync_time()
    if last_sync is None:
        return start
    catch_up_start = last_sync - timedelta(minutes=constants.CRM_SYNC_OVERLAP_MINUTES)
    if catch_up_start >= start:
        return start
    earliest = now - timedelta(days=constants.CRM_MAX_CATCHUP_DAYS)
    if catch_up_start < earliest:
        logger.error(
            f'Last successful CRM sync was at {last_sync} UTC, more than {constants.CRM_MAX_CATCHUP_DAYS} days ago. '
            f'Syncing only changes since {earliest} UTC, older changes must be checked manually'
        )
        return earliest
    logger.info(f'Last successful CRM sync was at {last_sync} UTC, catching up CRM changes since {catch_up_start} UTC')
    return catch_up_start


def main():
    now = datetime.now(timezone.utc)
    start_time = get_sync_start_time(now)
    with redirect_stdout(rich_log.console_to_rich_log_redirector):
        crm_orders = get_interval_orders(start=start_time, end=now)
    # crm_orders = get_interval_orders(start=datetime(year=2025, month=7, day=1, tzinfo=timezone.utc), filter_on='created')
    # crm_orders = get_active_orders() + get_orders_by_stage()
    if len(crm_orders) > constants.CRM_MAX_PROCESSING_ORDERS:
        logger.error(f'Too many orders (more than {constants.CRM_MAX_PROCESSING_ORDERS}) to process in CRM')
    with Session_Sync() as session:
        process_orders(crm_orders, session, since=start_time)
        process_cpa_refunds(session)
        process_delivery_fees(session)
        run_daily_commission_backfill(session)
    save_last_sync_time(now)  # only after all orders of the window were processed without exceptions


def run_daily_commission_backfill(session: Session) -> None:
    global last_commission_backfill_date
    today = datetime.now().date()
    if last_commission_backfill_date == today:
        return
    last_commission_backfill_date = today
    try:
        with redirect_stdout(rich_log.console_to_rich_log_redirector):
            backfill_prom_commissions(session)
    except Exception as e:
        logger.error(f'Commission backfill failed: {e}')


def process_orders(crm_orders: list[dict], session: Session, since: Optional[datetime] = None):
    """since: start of the CRM window; orders cancelled after it may trigger the cancelled-after-1C notice"""
    for order_dict in crm_orders:
        with session.begin():
            try:
                order = Order1CBuyer(**order_dict)
            except Exception as e:
                if order_dict['id'] not in parse_errors_orders_ids:
                    logger.error(f'Error parsing order {order_dict["id"]}: {e} ')
                    parse_errors_orders_ids.append(order_dict['id'])
                continue

            if not is_order_proper_filled(order) and not is_order_cancelled(order):
                continue  # skip some not properly filled orders

            if not order.parent_id:  # it is Buyer order and POSSIBLY Supplier order
                db_order = session.query(Order1CDB).filter_by(key_crm_id=order.key_crm_id, parent_id=None).first()
                if db_order is None:  # if order doesn't exist in db
                    if is_order_cancelled(order):
                        check_and_process_unreturned_commission(order, order_dict, session)
                        continue
                    # if order.prices_rounded: # uncomment when CRM fixes update
                    #     update_crm_order(order)
                    tree_orders = find_all_tree_orders_any_level(order_dict, crm_orders)
                    tree_products = find_unique_tree_products(tree_orders)
                    extended_order = order.model_copy(deep=True)
                    extended_order.products = [ProductBuyer(**product) for product in tree_products]
                    process_new_buyer_order(extended_order, session)
                    make_supplier_comission_orders(order, session)  # untab this line to process unprocessed commissions
                elif is_order_cancelled(order):
                    notify_cancelled_after_1c(order, order_dict, session, since)

            if order.supplier:  # Supplier present, this is a Supplier order or also a Supplier order
                order = Order1CSupplier(**order_dict)
                db_order = (
                    session
                    .query(Order1CDB)
                    .filter(Order1CDB.key_crm_id == order.key_crm_id, Order1CDB.parent_id.isnot(None))
                    .first()
                )
                if db_order is None:  # if order doesn't exist in db
                    root_id = find_root_order_id(order_dict, crm_orders)
                    order.parent_id = str(root_id)
                    process_new_supplier_order(order=order, session=session)
                else:  # if order exists in db
                    order = Order1CSupplierUpdate(**order_dict)
                    process_existing_supplier_order(order=order, db_order=db_order)


def process_cpa_refunds(session: Session):
    with session.begin():
        all_cpa_refunds = session.query(PromCPARefundOutbox).all()
    for cpa_refund in all_cpa_refunds:
        with session.begin():
            q = session.query(Order1CDB).filter_by(key_crm_id=str(cpa_refund.order_id)).first()
            if q is not None:
                make_vozvrat_tovarov_for_commission_posupleniye(cpa_refund, session)
                session.delete(cpa_refund)


def process_delivery_fees(session: Session):
    with session.begin():
        records = session.query(PromDeliveryCommissionOutbox).all()
    for record in records:
        with session.begin():
            try:
                crm_reply = crm.get_orders(filter={'source_uuid': str(record.order_id)})[0]
                logger.info(f'Successfully got order from CRM for {record.order_id}')
            except Exception as e:
                logger.error(f'Failed to get order from CRM for {record.order_id} | {str(e)}')
                continue
            commission_order = Order1CSupplierPromCommissionOrder(
                key_crm_id=f'{record.order_id}_fd',  # fd = free delivery
                parent_id=str(crm_reply['id']),
                supplier=f'Просейл {record.shop}',
                products=[ProductCommissionProSaleFreeDelivery(price=record.delivery_commission)],
                shop=record.shop,
            )
            process_new_supplier_order(commission_order, session)
            make_postupleniye_for_commission_order(commission_order, session)
            session.delete(record)


if __name__ == '__main__':
    rich_log = RichLog(header=f'Синхронизация CRM с 1С - {__file__}', header_style='bold white on cyan')
    logger_init(rich_log=rich_log, log_cut_after='=>')
    logger.info(f'STARTING {__file__}')
    try:
        while True:
            main()
            if not IS_PRODUCTION_SERVER:
                exit(0)
            if reload_file.exists():
                reload_file.unlink(missing_ok=True)
                logger.info(f'SHUTTING DOWN {__file__}')
                exit(0)
            rich_log.sleep(constants.TIME_TO_SLEEP_CRM_1C)
    except Exception as e:
        logger.error(f'Error in {__file__}: {e}')
    finally:
        rich_log.stop()
