from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import io
import openpyxl
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta
from urllib.parse import quote

from app.database import engine, get_db
from app import models
from app.models import Customer, Shipment
from app.auth import verify_pin, create_session, is_authenticated


# ================= IST TIME FIX =================

IST_OFFSET = timedelta(hours=5, minutes=30)

def get_ist_time():
    return datetime.utcnow() + IST_OFFSET


# =================================================

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


# ---------------- DATE PARSER ----------------

def parse_dates(start_date_str: str, end_date_str: str):
    start_dt = None
    end_dt = None

    if start_date_str:
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            pass

    if end_date_str:
        try:
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    return start_dt, end_dt


# ---------------- DASHBOARD ----------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    start_dt, end_dt = parse_dates(start_date, end_date)

    now = get_ist_time()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    s_today_q = db.query(Shipment).filter(Shipment.created_at >= today_start)
    r_today_q = db.query(func.sum(Shipment.rate)).filter(Shipment.created_at >= today_start)
    s_month_q = db.query(Shipment).filter(Shipment.created_at >= month_start)
    r_month_q = db.query(func.sum(Shipment.rate)).filter(Shipment.created_at >= month_start)

    shipments_today = s_today_q.count()
    revenue_today = r_today_q.scalar() or 0
    shipments_month = s_month_q.count()
    revenue_month = r_month_q.scalar() or 0

    total_customers = db.query(Customer).count()
    repeat_customers = db.query(Customer).filter(Customer.total_shipments > 1).count()
    repeat_percent = round((repeat_customers / total_customers) * 100, 1) if total_customers else 0

    chart_days = 14
    chart_start = (now - timedelta(days=chart_days-1)).replace(hour=0, minute=0, second=0, microsecond=0)

    daily_revenue_data = db.query(
        cast(Shipment.created_at, Date),
        func.sum(Shipment.rate)
    ).filter(
        Shipment.created_at >= chart_start
    ).group_by(
        cast(Shipment.created_at, Date)
    ).all()

    revenue_dict = {
        (r[0] if isinstance(r[0], str) else r[0].strftime("%Y-%m-%d")): r[1]
        for r in daily_revenue_data
    }

    labels, data = [], []
    for i in range(chart_days):
        day = chart_start + timedelta(days=i)
        labels.append(day.strftime("%b %d"))
        data.append(revenue_dict.get(day.strftime("%Y-%m-%d"), 0))

    top_customers = db.query(
        Customer.phone,
        func.sum(Shipment.rate)
    ).join(Shipment).filter(
        Shipment.created_at >= month_start
    ).group_by(Customer.id).order_by(
        func.sum(Shipment.rate).desc()
    ).limit(3).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "shipments_today": shipments_today,
        "revenue_today": int(revenue_today),
        "shipments_month": shipments_month,
        "revenue_month": int(revenue_month),
        "total_customers": total_customers,
        "repeat_percent": repeat_percent,
        "chart_labels": labels,
        "chart_data": data,
        "top_customers": top_customers
    })


# ---------------- PIN ----------------

@app.get("/pin", response_class=HTMLResponse)
def pin_page(request: Request):
    return templates.TemplateResponse("pin.html", {"request": request})


@app.post("/pin")
def submit_pin(pin: str = Form(...)):
    if verify_pin(pin):
        response = RedirectResponse("/", status_code=302)
        create_session(response)
        return response
    return RedirectResponse("/pin", status_code=302)


# ---------------- ADD PAGE (FIXED) ----------------

@app.get("/add", response_class=HTMLResponse)
def add_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/pin")
    return templates.TemplateResponse("add.html", {"request": request})


@app.post("/add")
def add_shipment(
    request: Request,
    phone: str = Form(...),
    tracking_id: str = Form(...),
    destination_city: str = Form(...),
    rate: float = Form(...),
    db: Session = Depends(get_db)
):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    now = get_ist_time()

    customer = db.query(Customer).filter(Customer.phone == phone).first()

    if not customer:
        customer = Customer(
            phone=phone,
            total_shipments=1,
            first_visit=now,
            last_visit=now
        )
        db.add(customer)
        db.flush()
    else:
        customer.total_shipments += 1
        customer.last_visit = now

    shipment = Shipment(
        tracking_id=tracking_id,
        destination_city=destination_city.upper(),
        rate=rate,
        customer_id=customer.id
    )

    db.add(shipment)
    db.commit()

    return RedirectResponse("/", status_code=302)


# ---------------- CUSTOMERS ----------------

@app.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    customers = db.query(Customer).order_by(Customer.last_visit.desc()).all()

    return templates.TemplateResponse("customers.html", {
        "request": request,
        "customers": customers
    })


# ---------------- INSIGHTS ----------------

@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    inactive_threshold = get_ist_time() - timedelta(days=45)

    inactive_customers = db.query(Customer).filter(
        Customer.last_visit < inactive_threshold
    ).count()

    top_cities = db.query(
        Shipment.destination_city,
        func.count(Shipment.id)
    ).group_by(
        Shipment.destination_city
    ).order_by(
        func.count(Shipment.id).desc()
    ).limit(5).all()

    return templates.TemplateResponse("insights.html", {
        "request": request,
        "inactive_customers": inactive_customers,
        "top_cities": top_cities
    })
