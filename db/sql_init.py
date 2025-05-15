import os
from datetime import date
from typing import Optional
from common_funcs import international_phone
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from parse.parse_constants import TTN_SENT_BY_CAR

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


def get_record_by_ttn(ttn_number):
    q = session.query(TTN).filter_by(ttn_number=ttn_number).first()
    return q


def stop_track_ttn(ttn_number: Optional[str]) -> None:
    if ttn_number is not None:
        q = get_record_by_ttn(ttn_number)
        if q is not None:
            q.finished = 8  # ttn is changed 
            session.commit()


def add_ttn_to_db(ttn_number: str, shop_sql_id: int, fio: str, phone: str, manager: str, old_ttn_number: Optional[str] = None) -> bool:
    stop_track_ttn(old_ttn_number)
    if ttn_number == TTN_SENT_BY_CAR:
        return True
    if get_record_by_ttn(ttn_number) is not None:
        print(f'TTN {ttn_number} already exists in the database')
        return False
    phone = international_phone(phone).removeprefix('+38') if phone else phone
    write_record_to_db(TTN(ttn_number=ttn_number,
                           shop=shop_sql_id,
                           fio=fio,
                           phone=phone,
                           delivery_date=date(year=2002, month=2, day=2),
                           manager=manager))
    return True
