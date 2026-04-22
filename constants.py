import os
from pathlib import Path
from dotenv import load_dotenv
from parse.parse_constants import Shops

load_dotenv('/etc/env/tg.env')
load_dotenv('/etc/env/crm.env')
load_dotenv('/etc/env/dev.env')
load_dotenv('/etc/env/ai.env')
load_dotenv('/etc/env/db.env')


def get_env(var: str) -> str:
    v = os.getenv(var)
    if v is None:
        raise ValueError(f'Environment variable {var} is not set')
    return v


IS_PRODUCTION_SERVER = True if get_env('IS_PRODUCTION_SERVER') == 'True' else False
DO_SEND_TO_BOT = True if get_env('DO_SEND_TO_BOT') == 'True' else False
TG_MAX_MESSAGE_LENGTH = 4096

CRM_API_KEY = get_env('KEY_CRM_API_KEY')
CRM_GET_LAST_ORDERS = 200
CRM_MAX_PROCESSING_ORDERS = 500
CRM_MINUTES_INTERVAL_TO_CHECK = 120
CRM_ORDER_COMPLETED_STAGE_ID = 12
CRM_ORDER_CANCELLED_STAGE_GROUP_ID = 6

UKRSALON_URL = get_env('UKRSALON_URL')
CALLBACK_CRM_PORT = int(get_env('CALLBACK_CRM_PORT'))
POSTGRES_USER = get_env('POSTGRES_user')
POSTGRES_PASSWORD = get_env('POSTGRES_password')
SALON_DB = get_env('SALON_db')
POSTGRES_HOST = 'localhost'

# ================================================= TELEGRAM =============================================
tg_token_salon = get_env('tg_token_salon')
tg_token_orders = get_env('tg_token_orders')
tg_token_tools = get_env('tg_token_tools')

admin_tg = int(get_env('admin_tg'))
director_tg = int(get_env('director_tg'))
ukrsalon_tg = int(get_env('ukrsalon_tg'))
ukrstil_tg = int(get_env('ukrstil_tg'))
beauty_tg = int(get_env('beauty_tg'))
klimazon_tg = int(get_env('klimazon_tg'))
krasunia_tg = int(get_env('krasunia_tg'))
lida_tg = int(get_env('lida_tg'))
rop_tg = int(get_env('rop_tg'))

managers: dict[int, str] = {
    ukrsalon_tg: 'УкрСалон',  # TODO: NAME
    ukrstil_tg: 'Вика',
    beauty_tg: 'Наталья',
    klimazon_tg: 'Климазон',
    krasunia_tg: 'Елена',
    lida_tg: 'Лида',
}

additional_receivers = {director_tg: 'Маша', rop_tg: 'Галина'}

time_to_sleep_insales_crm = 5  # sec
time_to_sleep_crm_1c = 40  # sec

jsons_out_path = Path('C:/Obmen/CRM/IN')
jsons_archive_path = Path(get_env('backup_root_path')) / 'Backup_Json'

# ================================================= PROM =============================================

prom_shops = [
    {'name': Shops.UKRSTIL.value, 'token': get_env('prom_ukrstil_orders_r'), 'managers': managers | additional_receivers},
    {'name': Shops.BEAUTY_MARKET.value, 'token': get_env('prom_beauty_orders_r'), 'managers': managers | additional_receivers},
    {'name': Shops.KRASUNIA.value, 'token': get_env('prom_krasunia_orders_r'), 'managers': managers | additional_receivers},
]

PROM_SLEEP_TIME = 5  # sec
PROM_STOP_TRIES_AFTER_DELAY_SEC = 2500  # sec
PROM_TIME_INTERVAL_TO_CHECK_MIN = 1320  # minutes (twenty-four hours)
PROM_CONSIDER_ORDER_FINISHED_DAYS = 60  # days


# ================================================= HOROSHOP =============================================
horoshop_shops = [
    {
        'name': Shops.KLIMAZON.value,
        'url': 'https://klimazon.com',
        'login': get_env('HOROSHOP_LOGIN'),
        'password': get_env('HOROSHOP_PASSWORD'),
        'managers': managers | additional_receivers,
    }
]

HOROSHOP_TIME_INTERVAL_TO_CHECK = 20000  # 1320  # minutes (twenty-four hours)
horoshop_sleep_time = 5  # sec
horoshop_stop_tries_after_delay = 200  # sec

# ================================================= AI =============================================
OPENAI_UKRSALON_API_KEY = get_env('OPENAI_UKRSALON_API_KEY')
