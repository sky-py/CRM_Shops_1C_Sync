from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.ext.automap import automap_base
from datetime import date
from common_funcs import international_phone
import os
from dotenv import load_dotenv

load_dotenv('/etc/env/db.env')

user = os.getenv('SQL_user')
password = os.getenv('SQL_password')
db = os.getenv('SQL_db_TTN')
host = 'localhost'

engine = create_engine(f'mssql+pyodbc://{user}:{password}@{host}/{db}?driver=SQL+Server+Native+Client+11.0')

base = automap_base()
base.prepare(autoload_with=engine)
TTN = base.classes.ttn     # ttn is name of the table
session = Session(engine)


def write_record_to_db(new_ttn: TTN):
    session.add(new_ttn)
    session.commit()


def ttn_number_exist(ttn_number):
    q = session.query(TTN).filter_by(ttn_number=ttn_number).first()
    if q:
        return True


def add_ttn_to_db(tracking_code: str, shop_sql_id: int, fio: str, phone: str, manager: str) -> bool:
    if ttn_number_exist(tracking_code):
        return False
    phone = international_phone(phone).removeprefix('+38') if phone else phone
    write_record_to_db(TTN(ttn_number=tracking_code,
                           shop=shop_sql_id,
                           fio=fio,
                           phone=phone,
                           delivery_date=date(year=2002, month=2, day=2),
                           manager=manager))
    return True



