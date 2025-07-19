import os
from dotenv import load_dotenv
from parse.parse_constants import Shops


load_dotenv('/etc/env/tg.env')
load_dotenv('/etc/env/crm.env')
load_dotenv('/etc/env/dev.env')
load_dotenv('/etc/env/ai.env')

IS_PRODUCTION_SERVER = True if os.getenv('IS_PRODUCTION_SERVER') == 'True' else False

CRM_API_KEY = os.getenv('KEY_CRM_API_KEY')
CRM_GET_LAST_ORDERS = 200
CRM_MAX_PROCESSING_ORDERS = 500
CRM_MINUTES_INTERVAL_TO_CHECK = 120
CRM_ORDER_COMPLETED_STAGE_ID = 12
CRM_ORDER_CANCELLED_STAGE_GROUP_ID = 6

UKRSALON_URL = os.getenv('UKRSALON_URL')

# ================================================= TELEGRAM =============================================
tg_token = os.getenv('tg_token_salon')
tg_token_tools = os.getenv('tg_token_tools')

admin_tg = os.getenv('admin_tg')
director_tg = os.getenv('director_tg')
ukrsalon_tg = os.getenv('ukrsalon_tg')
ukrstil_tg = os.getenv('ukrstil_tg')
beauty_tg = os.getenv('beauty_tg')
klimazon_tg = os.getenv('klimazon_tg')
krasunia_tg = os.getenv('krasunia_tg')
lida_tg = os.getenv('lida_tg')
rop_tg = os.getenv('rop_tg')

managers = [ukrsalon_tg, ukrstil_tg, beauty_tg, klimazon_tg, krasunia_tg, lida_tg]
managers_plus = [*managers, director_tg, rop_tg]

time_to_sleep_insales_crm = 5   # sec
time_to_sleep_crm_1c = 40   # sec

json_orders_for_1c_path = 'C:/Obmen/CRM/IN'
json_archive_1C_path = os.getenv('json_archive_1C_path')

# ================================================= PROM =============================================

prom_shops = [
    {'name': Shops.UKRSTIL.value, 'token': os.getenv('prom_ukrstil_orders_r'), 'managers': managers_plus},
    {'name': Shops.BEAUTY_MARKET.value, 'token': os.getenv('prom_beauty_orders_r'), 'managers': managers_plus},
    {'name': Shops.KRASUNIA.value, 'token': os.getenv('prom_krasunia_orders_r'), 'managers': managers_plus},
]

prom_sleep_time = 5  # sec
prom_stop_tries_after_delay = 200  # sec
PROM_TIME_INTERVAL_TO_CHECK = 1320  # minutes (twenty-four hours)
PROM_DAYS_TO_CONSIDER_ORDER_FINISHED = 60  # days


# ================================================= HOROSHOP =============================================
horoshop_shops = [
    {'name': Shops.KLIMAZON.value,
     'url': 'https://klimazon.com',
     'login': os.getenv('HOROSHOP_LOGIN'),
     'password': os.getenv('HOROSHOP_PASSWORD'),
     'managers': managers_plus},
]

HOROSHOP_TIME_INTERVAL_TO_CHECK = 20000  # 1320  # minutes (twenty-four hours)
horoshop_sleep_time = 5  # sec
horoshop_stop_tries_after_delay = 200  # sec

# ================================================= AI =============================================
OPENAI_UKRSALON_API_KEY = os.getenv('OPENAI_UKRSALON_API_KEY')

