"""
Read-only report: which Prom commissions are missing or wrong in 1C for one shop.

It changes nothing: no DB writes, no JSON files for 1C, no messages. It simulates two steps:
1. Refresh our DB (prom_orders) from Prom API for all orders of the period: status, CPA commission
   and its refund, order commission, free delivery fee.
2. With the refreshed data, decide what the sync scripts would create in 1C (commission, fake order for a
   cancelled order, CPA return, free delivery) and what can only be fixed manually.

Usage (from the project folder):
    python report_prom_commissions.py "Красуня" [2026-01-01] [output.html]
"""

import asyncio
import html
import json
import os
import platform
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import constants
from api.key_crm_api import KeyCRM
from api.prom_api_async import PromClient
from db.db_init import Session_Sync
from db.models import Order1CDB, PromOrderDB
from parse.parse_constants import Document1C, PromStatus
from parse.parse_prom_order import OrderProm

ARCHIVE_DIRS = (Path(constants.JSONS_ARCHIVE_PATH), Path(constants.JSONS_ARCHIVE_PATH) / 'Archive')
PROM_ORDER_URL = 'https://my.prom.ua/cms/order/edit/{}'
CRM_ORDER_URL = 'https://ukrsalon.keycrm.app/app/orders/view/{}'
CRM_STATUS_GROUPS = {1: 'новый', 2: 'принят', 3: 'в производстве', 4: 'отправлен', 5: 'выполнен', 6: 'отменён'}
PROM_STATUS_NAMES = {
    PromStatus.NEW: 'новый',
    PromStatus.ACCEPTED: 'принят',
    PromStatus.SUCCESS: 'выполнен',
    PromStatus.CANCELLED: 'отменён',
    PromStatus.PAID: 'оплачен',
    PromStatus.DRAFT: 'черновик',
    PromStatus.DISPATCHED: 'отправлен',
    PromStatus.OTHER: 'другой',
}

# what the sync scripts would do
AUTO = 'auto'  # the scripts would create it after the DB refresh
MANUAL = 'manual'  # must be fixed by hand
CHECK = 'check'  # needs attention, no 1C document by itself


@dataclass
class Item:
    prom_order_id: int
    kind: str  # AUTO / MANUAL / CHECK
    title: str
    amount: float  # effect on our prepayment in 1C: negative = expense to add, positive = return
    details: str = ''
    crm_order_id: Optional[int] = None


@dataclass
class DbChange:
    prom_order_id: int
    changes: list[str] = field(default_factory=list)


def money(value: float) -> str:
    return f'{value:,.2f}'.replace(',', ' ').replace('.', ',')


def load_archive_index() -> dict[str, list[Path]]:
    """key_crm_id -> archive JSON files of postupleniye documents (to read amounts already booked in 1C)."""
    index = defaultdict(list)
    for folder in ARCHIVE_DIRS:
        if not folder.exists():
            continue
        for name in os.listdir(folder):
            if '_create_postupleniye_tovarov_' in name:
                index[name.split('_create_postupleniye_tovarov_')[0]].append(folder / name)
    return index


def booked_amount(index: dict[str, list[Path]], key: str) -> Optional[float]:
    files = index.get(key)
    if not files:
        return None
    data = json.loads(files[0].read_text(encoding='utf-8'))
    return round(sum(p['price'] * p['quantity'] for p in data['products']), 2)


async def fetch_prom_orders(token: str, since: datetime) -> list[dict]:
    client = PromClient(token)
    return await client.get_orders(created_from=since, created_to=datetime.now())


def main(shop_name: str, since: datetime, out_file: Path) -> None:
    shop = next(s for s in constants.prom_shops if s['name'] == shop_name)
    crm = KeyCRM(constants.CRM_API_KEY)

    print(f'Reading Prom orders of {shop_name} created since {since:%d.%m.%Y}...')
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raw_orders = asyncio.run(fetch_prom_orders(shop['token'], since))
    prom_orders: dict[int, OrderProm] = {}
    parse_errors = []
    for order_dict in raw_orders:
        try:
            order = OrderProm(**order_dict)
        except Exception as e:
            parse_errors.append(f'{order_dict.get("id")}: {e}')
            continue
        prom_orders[order.order_id] = order
    print(f'Prom orders: {len(prom_orders)}, parse errors: {len(parse_errors)}')

    archive = load_archive_index()

    with Session_Sync() as session:
        db_orders = {o.order_id: o for o in session.query(PromOrderDB).filter(PromOrderDB.shop == shop_name).all()}
        keys = [key for oid in prom_orders for key in (str(oid), f'{oid}_oc', f'{oid}_fd')]
        docs = defaultdict(set)  # key_crm_id -> document types in 1C
        for key, doc_type in session.query(Order1CDB.key_crm_id, Order1CDB.document_type).filter(
            Order1CDB.key_crm_id.in_(keys)
        ):
            docs[key].add(doc_type)
        session.rollback()  # read-only

        db_changes: list[DbChange] = []
        items: list[Item] = []
        not_in_db = []
        need_crm: list[tuple[OrderProm, float, float]] = []  # order, CPA to book, order commission to book

        for oid, order in sorted(prom_orders.items()):
            db = db_orders.get(oid)
            if db is None:
                not_in_db.append(order)
                continue

            # ---------- step 1: what refreshing the DB would change ----------
            change = DbChange(oid)
            if order.status != db.status:
                change.changes.append(f'статус: {PROM_STATUS_NAMES[db.status]} → {PROM_STATUS_NAMES[order.status]}')
            if order.cpa_commission > 0 and order.cpa_commission != db.cpa_commission:
                change.changes.append(f'комиссия ProSale: {money(db.cpa_commission)} → {money(order.cpa_commission)}')
            if order.cpa_is_refunded and not db.cpa_is_refunded:
                change.changes.append('комиссия ProSale возвращена Prom')
            if order.order_commission != db.order_commission:
                change.changes.append(
                    f'оплата за заказ: {money(db.order_commission)} → {money(order.order_commission)}'
                )
            fd_changed = order.status == PromStatus.SUCCESS and order.delivery_commision != db.delivery_commission
            if fd_changed:
                change.changes.append(
                    f'доставка: {money(db.delivery_commission)} → {money(order.delivery_commision)}'
                )
            if change.changes:
                db_changes.append(change)

            cpa = order.cpa_commission if order.cpa_commission > 0 else db.cpa_commission
            cpa_key, oc_key, fd_key = str(oid), f'{oid}_oc', f'{oid}_fd'
            cpa_booked = cpa_key in docs
            oc_booked = oc_key in docs or cpa_key in docs  # fake order books order commission under plain key

            # ---------- step 2: what is missing in 1C ----------
            # CPA return: Prom refunded a commission that is booked in 1C
            if order.cpa_is_refunded and cpa > 0 and cpa_booked:
                if Document1C.RETURN_TOVAROV not in docs[cpa_key]:
                    items.append(
                        Item(
                            oid,
                            AUTO if not db.cpa_is_refunded else MANUAL,
                            'Возврат комиссии ProSale',
                            cpa,
                            'Prom вернул комиссию, в 1С есть поступление, но нет возврата',
                        )
                    )

            cpa_to_book = cpa if cpa > 0 and not order.cpa_is_refunded and not cpa_booked else 0
            oc_to_book = order.order_commission if order.order_commission > 0 and not oc_booked else 0
            if cpa_to_book or oc_to_book:
                need_crm.append((order, cpa_to_book, oc_to_book))

            # free delivery fee: a missing document is expected only for delivered orders, but an already booked
            # amount is compared for any status (an order may be cancelled after delivery, Prom still charges)
            fee = order.delivery_commision
            if fee > 0 and (order.status == PromStatus.SUCCESS or fd_key in docs):
                booked = booked_amount(archive, fd_key) if fd_key in docs else None
                if fd_key not in docs:
                    items.append(
                        Item(
                            oid,
                            AUTO if fd_changed else MANUAL,
                            'Доставка: нет документа',
                            -fee,
                            f'Prom: {money(fee)} по условиям акции',
                        )
                    )
                elif booked is not None and abs(booked - fee) > 0.009:
                    items.append(
                        Item(
                            oid,
                            MANUAL,
                            'Доставка: сумма в 1С отличается',
                            booked - fee,
                            f'в 1С {money(booked)}, по условиям акции {money(fee)}',
                        )
                    )

        print(f'Orders with commission missing in 1C: {len(need_crm)}, checking them in CRM...')
        for order, cpa_to_book, oc_to_book in need_crm:
            oid = order.order_id
            amount = cpa_to_book + oc_to_book
            what = ' + '.join(
                part
                for part, value in (('ProSale', cpa_to_book), ('оплата за заказ', oc_to_book))
                if value
            )
            try:
                crm_orders = crm.get_orders(filter={'source_uuid': str(oid)})
            except Exception as e:
                items.append(Item(oid, CHECK, 'Ошибка запроса CRM', -amount, str(e)))
                continue
            if not crm_orders:
                kind = MANUAL if order.status in (PromStatus.SUCCESS, PromStatus.CANCELLED) else CHECK
                items.append(Item(oid, kind, f'Комиссия ({what}): заказа нет в CRM', -amount))
                continue
            crm_order = crm_orders[0]
            crm_id = crm_order['id']
            group = crm_order['status_group_id']
            crm_status = CRM_STATUS_GROUPS.get(group, str(group))
            buyer_in_1c = (
                session.query(Order1CDB)
                .filter_by(key_crm_id=str(crm_id), parent_id=None, document_type=Document1C.CLIENT_ORDER)
                .first()
                is not None
            )
            session.rollback()
            if buyer_in_1c:
                items.append(
                    Item(oid, AUTO, f'Комиссия ({what}) к заказу в 1С', -amount, f'CRM: {crm_status}', crm_id)
                )
            elif group == constants.CRM_ORDER_CANCELLED_STAGE_GROUP_ID and order.status == PromStatus.CANCELLED:
                items.append(
                    Item(
                        oid,
                        AUTO if not crm_order['parent_id'] else MANUAL,
                        f'Фиктивный заказ + комиссия ({what})',
                        -amount,
                        'отменён в CRM и на Prom, Prom комиссию не вернул',
                        crm_id,
                    )
                )
            elif group == constants.CRM_ORDER_CANCELLED_STAGE_GROUP_ID:
                items.append(
                    Item(
                        oid,
                        CHECK,
                        f'Комиссия ({what}): отменён в CRM, на Prom «{PROM_STATUS_NAMES[order.status]}»',
                        -amount,
                        'нужно отменить заказ на Prom, тогда комиссия будет возвращена или проведена',
                        crm_id,
                    )
                )
            elif order.status == PromStatus.CANCELLED:
                items.append(
                    Item(
                        oid,
                        MANUAL,
                        f'Комиссия ({what}): отменён на Prom, в CRM «{crm_status}»',
                        -amount,
                        'отменить заказ в CRM, тогда скрипт создаст фиктивный заказ',
                        crm_id,
                    )
                )
            elif group == constants.CRM_ORDER_COMPLETED_STAGE_GROUP_ID:
                items.append(
                    Item(
                        oid,
                        MANUAL,
                        f'Комиссия ({what}): заказ выполнен, но не в 1С',
                        -amount,
                        'поставить в CRM отметку «Заказ 1С»',
                        crm_id,
                    )
                )
            else:
                items.append(
                    Item(oid, CHECK, f'Комиссия ({what}): заказ в работе', -amount, f'CRM: {crm_status}', crm_id)
                )

    write_html(out_file, shop_name, since, prom_orders, db_changes, items, not_in_db, parse_errors)
    print_summary(items, db_changes, not_in_db)
    print(f'Report: {out_file}')


def print_summary(items: list[Item], db_changes: list[DbChange], not_in_db: list) -> None:
    print(f'DB changes: {len(db_changes)} orders, Prom orders missing in DB: {len(not_in_db)}')
    for kind, label in ((AUTO, 'auto'), (MANUAL, 'manual'), (CHECK, 'check')):
        selected = [i for i in items if i.kind == kind]
        print(f'{label}: {len(selected)} items, effect on 1C prepayment {round(sum(i.amount for i in selected), 2)}')


def link(url: str, text) -> str:
    return f'<a href="{html.escape(url)}" target="_blank">{html.escape(str(text))}</a>'


def write_html(out_file, shop_name, since, prom_orders, db_changes, items, not_in_db, parse_errors) -> None:
    def item_rows(kind: str) -> str:
        selected = sorted((i for i in items if i.kind == kind), key=lambda i: (i.title, i.prom_order_id))
        if not selected:
            return '<p class="muted">Нет.</p>'
        rows = []
        for i in selected:
            crm = link(CRM_ORDER_URL.format(i.crm_order_id), i.crm_order_id) if i.crm_order_id else '—'
            cls = 'minus' if i.amount < 0 else 'plus'
            rows.append(
                f'<tr><td>{link(PROM_ORDER_URL.format(i.prom_order_id), i.prom_order_id)}</td><td>{crm}</td>'
                f'<td>{html.escape(i.title)}</td><td>{html.escape(i.details)}</td>'
                f'<td class="n {cls}">{money(i.amount)}</td></tr>'
            )
        total = sum(i.amount for i in selected)
        return (
            '<div class="tbl"><table><tr><th>Заказ Prom</th><th>Заказ CRM</th><th>Что</th><th>Подробности</th>'
            '<th class="n">Влияние на сальдо 1С</th></tr>' + ''.join(rows)
            + f'<tr class="total"><td colspan="4">Итого ({len(selected)})</td><td class="n">{money(total)}</td></tr>'
            '</table></div>'
        )

    changes_rows = ''.join(
        f'<tr><td>{link(PROM_ORDER_URL.format(c.prom_order_id), c.prom_order_id)}</td>'
        f'<td>{html.escape("; ".join(c.changes))}</td></tr>'
        for c in db_changes
    )
    missing_rows = ''.join(
        f'<tr><td>{link(PROM_ORDER_URL.format(o.order_id), o.order_id)}</td><td>{o.date_created:%d.%m.%Y}</td>'
        f'<td>{PROM_STATUS_NAMES[o.status]}</td><td class="n">{money(o.cpa_commission)}</td></tr>'
        for o in not_in_db
    )
    totals = {k: sum(i.amount for i in items if i.kind == k) for k in (AUTO, MANUAL, CHECK)}
    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Комиссии Prom: {html.escape(shop_name)}</title>
<style>
:root{{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#6b6b66;--line:#e3e2dd;--accent:#2f5d8a;--plus:#1f7a45;
--minus:#b3261e;--head:#f0efeb}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#161615;--card:#1f1f1d;--text:#ecebe6;
--muted:#a3a29b;--line:#33332f;--accent:#8db8e3;--plus:#6fcf97;--minus:#f28b82;--head:#262624}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:19px;margin:32px 0 8px;padding-top:8px;border-top:1px solid var(--line)}}
a{{color:var(--accent)}}.muted{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.card .lbl{{color:var(--muted);font-size:13px}}.card .val{{font-size:22px;font-weight:600}}
.tbl{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{background:var(--head);font-size:13px;white-space:nowrap}}tr:last-child td{{border-bottom:0}}
td.n,th.n{{text-align:right;white-space:nowrap}}tr.total td{{font-weight:700;background:var(--head)}}
.plus{{color:var(--plus)}}.minus{{color:var(--minus)}}
</style></head><body><main>
<h1>Комиссии Prom без документов в 1С: {html.escape(shop_name)}</h1>
<div class="muted">Заказы Prom, созданные с {since:%d.%m.%Y}. Отчёт сформирован {datetime.now():%d.%m.%Y %H:%M}.
Только чтение: база, 1С и CRM не изменялись.</div>
<div class="cards">
<div class="card"><div class="lbl">Заказов на Prom</div><div class="val">{len(prom_orders)}</div></div>
<div class="card"><div class="lbl">Создаст скрипт</div><div class="val">{money(totals[AUTO])}</div></div>
<div class="card"><div class="lbl">Исправить вручную</div><div class="val">{money(totals[MANUAL])}</div></div>
<div class="card"><div class="lbl">Проверить</div><div class="val">{money(totals[CHECK])}</div></div>
</div>
<p class="muted">«Влияние на сальдо 1С»: минус — в 1С нужно добавить расход (наша предоплата уменьшится),
плюс — возврат или лишний расход (предоплата увеличится).</p>

<h2>1. Документы, которые создаст скрипт</h2>
<p class="muted">После обновления базы с Prom и прогона дозагрузки за период. Документы получат дату запуска.</p>
{item_rows(AUTO)}

<h2>2. Исправить вручную</h2>
<p class="muted">Скрипт этого не сделает: нет отметки «Заказ 1С», статусы в CRM и на Prom не совпадают,
или нужно изменить уже проведённую сумму.</p>
{item_rows(MANUAL)}

<h2>3. Проверить</h2>
<p class="muted">Заказы ещё в работе или статусы требуют внимания. Документ в 1С пока не нужен.</p>
{item_rows(CHECK)}

<h2>4. Что изменится в базе после обновления с Prom ({len(db_changes)})</h2>
{'<div class="tbl"><table><tr><th>Заказ Prom</th><th>Изменения</th></tr>' + changes_rows + '</table></div>' if db_changes else '<p class="muted">Нет.</p>'}

<h2>5. Заказы Prom, которых нет в нашей базе ({len(not_in_db)})</h2>
{'<div class="tbl"><table><tr><th>Заказ Prom</th><th>Создан</th><th>Статус</th><th class="n">ProSale</th></tr>' + missing_rows + '</table></div>' if not_in_db else '<p class="muted">Нет.</p>'}
{('<h2>Ошибки разбора заказов Prom</h2><p class="muted">' + html.escape('; '.join(parse_errors)) + '</p>') if parse_errors else ''}
</main></body></html>"""
    out_file.write_text(page, encoding='utf-8')


if __name__ == '__main__':
    shop_arg = sys.argv[1] if len(sys.argv) > 1 else 'Красуня'
    since_arg = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime(datetime.now().year, 1, 1)
    out_arg = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(f'prom_commissions_{shop_arg}.html')
    main(shop_arg, since_arg, out_arg)
