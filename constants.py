import constants_dev
import os
from dotenv import load_dotenv
from parse.parse_constants import Shops

load_dotenv('c:/Scripts/env/tg.env')
load_dotenv('c:/Scripts/env/crm.env')

IS_PRODUCTION = constants_dev.IS_PRODUCTION  # type of web server used

KEY_CRM_API_KEY = os.getenv('KEY_CRM_API_KEY')
KEY_GET_LAST_ACTIVE_ORDERS = 200
KEY_MAX_PROCESSING_ORDERS = 1000
KEY_TIME_INTERVAL_TO_CHECK = 120  # minutes
KEY_TIME_SHIFT = 180  # time difference between CRM time and local in minutes
KEY_ACTIVE_STAGES = [1, 2, 3, 6, 20, 21, 23, 30, 32, 33]  # for speed, but better get these stages from API
order_completed_stage_id = 12
# KEY_GET_LAST_ORDERS = 400

UKRSALON_URL = os.getenv('UKRSALON_URL')

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
ilona_tg = os.getenv('ilona_tg')

managers = [ukrsalon_tg, ukrstil_tg, beauty_tg, klimazon_tg, krasunia_tg, lida_tg, ilona_tg]
managers_plus = [*managers, director_tg, rop_tg]

time_to_sleep_insales_crm = 5   # sec
time_to_sleep_crm_1c = 40   # sec

json_orders_for_1c_path = 'C:/Obmen/CRM/IN'
json_archive_path = constants_dev.json_archive_path

# ================================================= PROM =============================================

prom_shops = [
    {'name': Shops.UKRSTIL.value, 'token': os.getenv('prom_ukrstil_orders_r'), 'managers': managers_plus},
    {'name': Shops.BEAUTY_MARKET.value, 'token': os.getenv('prom_beauty_orders_r'), 'managers': managers_plus},
    {'name': Shops.KLIMAZON.value, 'token': os.getenv('prom_klimazon_orders_r'), 'managers': managers_plus},
    {'name': Shops.KRASUNIA.value, 'token': os.getenv('prom_krasunia_orders_r'), 'managers': managers_plus},
]

prom_sleep_time = 5  # sec
prom_stop_tries_after_delay = 200  # sec
PROM_TIME_INTERVAL_TO_CHECK = 1320  # minutes (twenty-four hours)

