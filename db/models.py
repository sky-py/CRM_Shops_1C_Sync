from sqlalchemy import Column, String, Integer, func, Boolean, DateTime, Float, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from parse.parse_constants import PromStatus, Document1C

Base = declarative_base()


class UkrsalonOrderDB(Base):
    __tablename__ = 'ukrsalon_orders'
    id = Column(Integer, primary_key=True)
    source_uuid = Column(Integer)
    key_crm_id = Column(Integer)
    ordered_at = Column(DateTime, default=func.now())
    total_price = Column(Float)
    manager_id = Column(Integer)
    # manager = Column(sqlalchemy.Enum(Manager))
    status_id = Column(Integer)
    is_paid = Column(Boolean, default=False)
    is_accepted = Column(Boolean, default=False)
    insales_id = Column(Integer)
    json = Column(JSONB)

    def __repr__(self):
        return f'{self.id} Insales:{self.source_uuid} KeyCRM:{self.key_crm_id} Manager:{self.manager} ' \
               f'Date:{self.ordered_at} Status:{self.status_id} Paid:{self.is_paid}'


class Order1CDB(Base):
    __tablename__ = 'orders_1c'
    id = Column(Integer, primary_key=True)
    document_type = Column(Enum(Document1C))
    key_crm_id = Column(Integer, default=None)
    parent_id = Column(Integer, default=None)   # None for Buyer order, not None for Supplier order
    tracking_code = Column(String, default=None)
    supplier_id = Column(String, default=None)

    def __repr__(self):
        return f'{self.id} KeyCRM:{self.key_crm_id} by:{self.by} TTN:{self.tracking_code}'


class PromOrderDB(Base):
    __tablename__ = 'prom_orders'
    order_id = Column(Integer, primary_key=True)
    status = Column(Enum(PromStatus), nullable=False)
    shop = Column(String)
    is_accepted = Column(Boolean, default=False)
    cpa_commission = Column(Float, default=0.0)
    cpa_is_refunded = Column(Boolean, default=False)
    ordered_at = Column(DateTime(timezone=True), default=func.now())

    def __repr__(self):
        return f'Order {self.order_id} Shop:{self.shop} is_accepted:{self.is_accepted} CPA:{self.CPA_comission}'


class PromCPARefundQueueDB(Base):
    __tablename__ = 'prom_cpa_queue'
    order_id = Column(Integer, primary_key=True)
    shop = Column(String)
    cpa_commission = Column(Float, default=0.0)
