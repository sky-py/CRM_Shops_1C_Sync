from enum import Enum, StrEnum

ukrsalon_crm_id = 10  # Ідентифікатор джерела Укрсалон
insta_ukrsalon_crm_id = 5  # Ідентифікатор джерела Инстаграм Укрсалон
sku_to_name_xml_file = 'c:/Quad Solutions/files/1_ main/ukrstil_ua.xml'
TTN_SENT_BY_CAR = '00000000000000'
FAKE_SUPPLIER = 'Фиктивный поставщик'


class Status(Enum):
    NEW = 2
    ACCEPTED = 3
    SUCCESS = 1
    CANCELLED = 0
    PRODUCTION = 4   # Оформлен
    DISPATCHED = 5
    PAID = 6
    OTHER = 10


class PromStatus(Enum):
    NEW = 'New'
    ACCEPTED = 'Accepted'
    SUCCESS = 'Success'
    CANCELLED = 'Cancelled'
    PAID = 'Paid'
    DRAFT = 'Draft'
    OTHER = 'Other'
    DISPATCHED = 'Dispatched'
    
    
class PaymentStatus(StrEnum):
    PAID = 'paid'
    NOT_PAID = 'not_paid'


class Shops(Enum):
    UKRSALON = 'УкрСалон'
    UKRSTIL = 'УкрСтиль'
    BEAUTY_MARKET = 'Бьюти Маркет'
    KLIMAZON = 'Климазон'
    KRASUNIA = 'Красуня'


class Document1C(Enum):
    CLIENT_ORDER = 'Заказ Клиента'
    SUPPLIER_ORDER = 'Заказ поставщику'
    POSTUPLENIYE_TOVAROV = 'Поступление товаров и услуг'
    RETURN_TOVAROV = 'Возврат товаров поставщику'


status_prom_to_db = {
    'pending': PromStatus.NEW,
    'received': PromStatus.ACCEPTED,
    'delivered': PromStatus.SUCCESS,
    'canceled': PromStatus.CANCELLED,
    'paid': PromStatus.PAID,
    'draft': PromStatus.DRAFT,
}

status_horoshop_to_db = {
    1: PromStatus.NEW,
    2: PromStatus.ACCEPTED,
    3: PromStatus.SUCCESS,
    4: PromStatus.CANCELLED,
    6: PromStatus.DISPATCHED,
}

manager_insales_to_db = {   # TODO 1
    798545: 9,   # Ilona
    192279: 2,   # Vika
    1245660: 3,  # Natasha
    1252475: 4,  # Lida
    156590: 6,  # Olena
    # 4760402: 9,  # Lilya Tovaroved
}

manager_key_to_db = {    # TODO 2
    4: 1,   # Ira
    5: 2,   # Vika
    6: 3,  # Natasha
    7: 4,    # Lida
    11: 5,    # Yulia
    12: 6,    # Olena
    17: 7,    # Lilia
    18: 8,    # Galina
    22: 9,    # Ilona
    28: 10,    # Olga
    26: 11,    # Oksana
    27: 12,    # Alexandra
    24: 13,    # Svetlana
    2: 14,    # Sergey
}


manager_key_to_1c = {
    4: 'Мен. № 2 - Ирина Т.',
    5: 'Мен. № 3 -Вика',
    6: 'Мен. № 8 - Наталья',
    7: 'Мен. № 10 - Лида',
    11: 'Мен. № 12 - Юлия',
    12: 'Мен. № 11 - Елена',
    17: 'Мен. № 14 - Лилия',
    18: 'Мен. № 15 - Галина',
    22: 'Мен. № 16 - Илона',
    28: 'Мен. № 17 - Ольга',
    26: 'Мен. № 18 - Оксана',
    27: 'Мен. № 19 - Александра',
    24: 'Светлана',
    2: 'Сергей',
}


status_key_group_to_db = {
    # via group status number
    6: Status.CANCELLED,
    5: Status.SUCCESS,
    1: Status.NEW,
    2: Status.ACCEPTED,
    3: Status.PRODUCTION,  # У вировництві -> Оформлен
    4: Status.DISPATCHED   # Отправлен -> Оформлен
}

status_insales_to_db = {
    'declined': Status.CANCELLED,
    'dispatched': Status.SUCCESS,
    'new': Status.NEW,
    'accepted': Status.ACCEPTED,
    'approved': Status.PRODUCTION     # Оформлен
}

financial_status_to_db = {
    'pending': False,
    'paid': True
}

shop_key_to_1c = {
    1: Shops.KLIMAZON.value,
    2: Shops.UKRSTIL.value,
    3: Shops.BEAUTY_MARKET.value,
    4: Shops.KRASUNIA.value,
    5: 'Insta ' + Shops.UKRSALON.value,
    6: 'Insta ' + Shops.UKRSTIL.value,
    7: 'Insta ' + Shops.BEAUTY_MARKET.value,
    8: 'Insta ' + Shops.KLIMAZON.value,
    9: 'Insta ' + Shops.KRASUNIA.value,
    10: Shops.UKRSALON.value,
    11: Shops.KLIMAZON.value,
}

shop_crm_id_to_sql_shop_id = {
    1: 4,
    2: 2,
    3: 3,
    4: 5,
    5: 1,
    6: 2,
    7: 3,
    8: 4,
    9: 5,
    10: 1,
}


payment_insales_to_crm_id = {
    'Оплата по счёту': 8,
    'Оплата за рахунком': 8,
    'Выставление счета для юр.лиц в Украине': 8,
    'Виставлення рахунку на юр.осіб в Україні': 8,
    'Рассрочка Плати позже': 9,
    'Розстрочка від сервісу "Плати пізніше"': 9,
    'Наложенным платежом': 6,
    'Накладеним платежем': 6,
    'Банковской картой / Приват24 / LiqPay/ Google Pay/ Apple Pay': 11,
    'Банківською картою / Приват24 / LiqPay/ Google Pay/ Apple Pay': 11,
    'МоноБанк Оплата Частями': 17,
    'Монобанк - "Купівля Частинами"': 17,
    'ПриватБанк  Оплата Частями': 12,
    'ПриватБанк - "Оплата Частинами"': 12,
    'ПриватБанк Мгновенная рассрочка': 14,
    'ПриватБанк - "Миттєва розстрочка"': 14,
    'А-Банк   Оплата Частями': 23,
    'А-Банк - "Оплата Частинами"': 23,
    'Альфа-банк Оплата Частями': 22,
    'Альфа-банк - Оплата Частинами': 22,
    'Укрсиббанк Оплата Частями': 21,
    'Оплата Частинами від Укрсиббанка': 21,

}


payment_crm_id_to_1c = {
    1: 'Оплачено',
    3: 'Выслан счёт',
    8: 'Выслан счёт',
    7: 'Промоплата',
    16: 'Промоплата',
    6: 'НК (наложка на компанию)',
    25: 'НК (наложка на компанию)',
    29: 'НК (наложка на компанию)',
    11: 'Ликпей',
    9: 'ОПЛАТА ЧАСТЯМИ',
    12: 'ОПЛАТА ЧАСТЯМИ',
    13: 'ОПЛАТА ЧАСТЯМИ',
    14: 'ОПЛАТА ЧАСТЯМИ',
    15: 'ОПЛАТА ЧАСТЯМИ',
    17: 'ОПЛАТА ЧАСТЯМИ',
    18: 'ОПЛАТА ЧАСТЯМИ',
    19: 'ОПЛАТА ЧАСТЯМИ',
    20: 'ОПЛАТА ЧАСТЯМИ',
    21: 'ОПЛАТА ЧАСТЯМИ',
    22: 'ОПЛАТА ЧАСТЯМИ',
    23: 'ОПЛАТА ЧАСТЯМИ',
    24: 'ОПЛАТА ЧАСТЯМИ',
    27: 'ОПЛАТА ЧАСТЯМИ',
    28: 'ОПЛАТА ЧАСТЯМИ',
    31: 'ОПЛАТА ЧАСТЯМИ',
    32: 'ОПЛАТА ЧАСТЯМИ',
    34: 'ОПЛАТА ЧАСТЯМИ',
    37: 'ОПЛАТА ЧАСТЯМИ',
    35: 'WayForPay',
    36: 'WayForPay',
}

paid_by_card_methods = ['Промоплата', 'Ликпей', 'WayForPay']


def get_key_by_value(mdict: dict, val):
    for key, value in mdict.items():
        if val == value:
            return key



