from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import os
from dotenv import load_dotenv
from db.models import Base

load_dotenv('/etc/env/db.env')

user = os.getenv('POSTGRES_user')
password = os.getenv('POSTGRES_password')
db = os.getenv('SALON_db')
host = 'localhost'

engine = create_engine(f'postgresql+psycopg2://{user}:{password}@{host}/{db}', echo=False)
Base.metadata.create_all(bind=engine)
Session_Sync = sessionmaker(bind=engine)
