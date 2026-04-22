from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import constants
from db.models import Base

engine = create_engine(
    f'postgresql+psycopg2://{constants.POSTGRES_USER}:{constants.POSTGRES_PASSWORD}@{constants.POSTGRES_HOST}/{constants.SALON_DB}',
    echo=False,
)
Base.metadata.create_all(bind=engine)
Session_Sync = sessionmaker(bind=engine)
