from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from app.database import Base

IST = ZoneInfo("Asia/Kolkata")

def ist_now():
    return datetime.now(IST)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    total_shipments = Column(Integer, default=0)

    first_visit = Column(DateTime, default=ist_now)
    last_visit = Column(DateTime, default=ist_now)

    shipments = relationship(
        "Shipment",
        back_populates="customer",
        cascade="all, delete-orphan"
    )


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    tracking_id = Column(String, index=True)
    destination_city = Column(String)
    rate = Column(Float)

    created_at = Column(DateTime, default=ist_now)

    status = Column(String, default="BOOKED")
    customer_id = Column(Integer, ForeignKey("customers.id"))
    customer = relationship("Customer", back_populates="shipments")
