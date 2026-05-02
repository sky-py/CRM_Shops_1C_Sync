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


def get_env_bool(var: str) -> bool:
    value = get_env(var).lower()
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError(f'Environment variable {var} must be boolean, got {value!r}')


# ================================================= DEV =============================================
IS_PRODUCTION_SERVER = get_env_bool('IS_PRODUCTION_SERVER')
CALLBACK_CRM_PORT = int(get_env('CALLBACK_CRM_PORT'))
LOG_DIR = Path(__file__).resolve().parent / 'log'
# ================================================= KEY_CRM =============================================
CRM_API_KEY = get_env('KEY_CRM_API_KEY')
CRM_GET_LAST_ORDERS = 200
CRM_MAX_PROCESSING_ORDERS = 500
CRM_MINUTES_INTERVAL_TO_CHECK = 120
CRM_ORDER_COMPLETED_STAGE_ID = 12
CRM_ORDER_CANCELLED_STAGE_GROUP_ID = 6

TIME_TO_SLEEP_CRM_1C = 40  # sec
JSONS_OUT_PATH = Path('C:/Obmen/CRM/IN')
JSONS_ARCHIVE_PATH = Path(get_env('backup_root_path')) / 'Backup_Json'
# ================================================= DB =============================================
POSTGRES_USER = get_env('POSTGRES_user')
POSTGRES_PASSWORD = get_env('POSTGRES_password')
SALON_DB = get_env('SALON_db')
POSTGRES_HOST = 'localhost'
# ================================================= TELEGRAM =============================================
DO_SEND_TO_BOT = True if get_env('DO_SEND_TO_BOT') == 'True' else False
TG_MAX_MESSAGE_LENGTH = 4096
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
olexandra_tg = int(get_env('olexandra_tg'))
rop_tg = int(get_env('rop_tg'))

# ================================================= MANAGERS =============================================
managers: dict[int, str] = {
    ukrstil_tg: 'Вика',
    beauty_tg: 'Наталья',
    krasunia_tg: 'Елена',
    lida_tg: 'Лида',
    olexandra_tg: 'Олександра',
    # ukrsalon_tg: 'УкрСалон',
    # klimazon_tg: 'Климазон',
}

additional_receivers = {rop_tg: 'Галина', admin_tg: 'Админ'}
# ================================================== UKRSALON =============================================
UKRSALON_URL = get_env('UKRSALON_URL')
TIME_TO_SLEEP_INSALES_CRM = 10  # sec
# ================================================= PROM =============================================
PROM_SLEEP_TIME = 5  # sec
PROM_STOP_TRIES_AFTER_DELAY_SEC = 2500  # sec
PROM_TIME_INTERVAL_TO_CHECK_MIN = 1320  # minutes (twenty-four hours)
PROM_CONSIDER_ORDER_FINISHED_DAYS = 60  # days

prom_shops = [
    {
        'name': Shops.UKRSTIL.value,
        'token': get_env('prom_ukrstil_orders_r'),
        'managers': managers | additional_receivers,
    },
    {
        'name': Shops.BEAUTY_MARKET.value,
        'token': get_env('prom_beauty_orders_r'),
        'managers': managers | additional_receivers,
    },
    {
        'name': Shops.KRASUNIA.value,
        'token': get_env('prom_krasunia_orders_r'),
        'managers': managers | additional_receivers,
    },
]
# ================================================= HOROSHOP =============================================
HOROSHOP_TIME_INTERVAL_TO_CHECK = 20000  # 1440  # minutes (twenty-four hours)
HOROSHOP_SLEEP_TIME = 5  # sec
HOROSHOP_STOP_TRIES_AFTER_DELAY = 200  # sec
horoshop_shops = [
    {
        'name': Shops.KLIMAZON.value,
        'url': 'https://klimazon.com',
        'login': get_env('HOROSHOP_LOGIN'),
        'password': get_env('HOROSHOP_PASSWORD'),
        'managers': managers | additional_receivers,
    }
]
# ================================================= AI =============================================
OPENAI_UKRSALON_API_KEY = get_env('OPENAI_UKRSALON_API_KEY')
