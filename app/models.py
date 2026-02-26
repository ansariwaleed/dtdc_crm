from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    total_shipments = Column(Integer, default=0)
    first_visit = Column(DateTime, default=datetime.utcnow)
    last_visit = Column(DateTime, default=datetime.utcnow)

    shipments = relationship("Shipment", back_populates="customer", cascade="all, delete-orphan")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    tracking_id = Column(String, index=True)
    destination_city = Column(String)
    rate = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    status = Column(String, default="BOOKED") # BOOKED, DELIVERED
    customer_id = Column(Integer, ForeignKey("customers.id"))
    customer = relationship("Customer", back_populates="shipments")