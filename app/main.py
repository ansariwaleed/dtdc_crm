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

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

def parse_dates(start_date_str: str, end_date_str: str):
    """Helper to parse date strings from frontend into datetime objects."""
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



# -------------------- DASHBOARD --------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    start_dt, end_dt = parse_dates(start_date, end_date)

    # Defaults if no specific date range is selected
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)

    s_today_q = db.query(Shipment).filter(Shipment.created_at >= today_start)
    r_today_q = db.query(func.sum(Shipment.rate)).filter(Shipment.created_at >= today_start)
    s_month_q = db.query(Shipment).filter(Shipment.created_at >= month_start)
    r_month_q = db.query(func.sum(Shipment.rate)).filter(Shipment.created_at >= month_start)

    # If dates are provided, override the generic queries to use the specific date range
    if start_dt or end_dt:
        base_q = db.query(Shipment)
        rev_q = db.query(func.sum(Shipment.rate))
        if start_dt:
            base_q = base_q.filter(Shipment.created_at >= start_dt)
            rev_q = rev_q.filter(Shipment.created_at >= start_dt)
        if end_dt:
            base_q = base_q.filter(Shipment.created_at <= end_dt)
            rev_q = rev_q.filter(Shipment.created_at <= end_dt)

        shipments_today = base_q.count()
        revenue_today = rev_q.scalar() or 0
        shipments_month = shipments_today  # Sync values for display
        revenue_month = revenue_today
    else:
        shipments_today = s_today_q.count()
        revenue_today = r_today_q.scalar() or 0
        shipments_month = s_month_q.count()
        revenue_month = r_month_q.scalar() or 0

    total_customers = db.query(Customer).count()
    repeat_customers = db.query(Customer).filter(Customer.total_shipments > 1).count()
    repeat_percent = (round((repeat_customers / total_customers) * 100, 1) if total_customers > 0 else 0)

    # --- Chart Data (Last 14 Days) ---
    chart_days = 14
    chart_start = (now - timedelta(days=chart_days-1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Query daily revenue
    # Using cast(..., Date) is standard SQL and works on both SQLite and PostgreSQL
    daily_revenue_data = db.query(
        cast(Shipment.created_at, Date).label("date"),
        func.sum(Shipment.rate).label("revenue")
    ).filter(
        Shipment.created_at >= chart_start
    ).group_by(
        cast(Shipment.created_at, Date)
    ).all()

    revenue_dict = {}
    for r in daily_revenue_data:
        # SQLite returns strings, PostgreSQL returns date objects
        d_str = r.date if isinstance(r.date, str) else r.date.strftime("%Y-%m-%d")
        revenue_dict[d_str] = r.revenue

    revenue_chart_labels = []
    revenue_chart_data = []
    for i in range(chart_days):
        day = chart_start + timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        revenue_chart_labels.append(day.strftime("%b %d"))
        revenue_chart_data.append(revenue_dict.get(day_str, 0))

    # --- Top Performers ---
    top_customers = db.query(
        Customer.phone,
        func.sum(Shipment.rate).label("revenue")
    ).join(Shipment).filter(
        Shipment.created_at >= month_start
    ).group_by(
        Customer.id
    ).order_by(
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
        "start_date": start_date or "",
        "end_date": end_date or "",
        "chart_labels": revenue_chart_labels,
        "chart_data": revenue_chart_data,
        "top_customers": top_customers
    })


# -------------------- PIN --------------------

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


# -------------------- ADD SHIPMENT --------------------

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

    phone = "".join(filter(str.isdigit, phone))
    if not phone.startswith("91") and len(phone) == 10:
        phone = "91" + phone
    elif len(phone) > 10 and phone.startswith("0"):
        phone = "91" + phone[1:]


    customer = db.query(Customer).filter(Customer.phone == phone).first()

    if not customer:
        customer = Customer(
            phone=phone,
            total_shipments=1,
            first_visit=datetime.utcnow(),
            last_visit=datetime.utcnow()
        )
        db.add(customer)
        db.flush() # Ensure we have the ID but don't commit yet
    else:
        customer.total_shipments += 1
        customer.last_visit = datetime.utcnow()

    shipment = Shipment(
        tracking_id=tracking_id,
        destination_city=destination_city.strip().upper(),
        rate=rate,
        customer_id=customer.id
    )
    db.add(shipment)
    db.commit()

    tracking_link = f"https://www.dtdc.com/track-your-shipment/?awb={tracking_id}"
    franchise_name = "DTDC Deokali Tiraha – Faizabad"
    franchise_phone = "9519291041"
    gmap_link = "https://maps.app.goo.gl/8w3MpRrRhrvDemB79?g_st=aw"

    formatted_rate = int(rate) if rate.is_integer() else rate

    message = f"""Dear Customer,

Your shipment has been successfully booked at {franchise_name}.

Tracking Details:
• Tracking ID: {tracking_id}
• Destination: {destination_city.upper()}
• Charges: ₹{formatted_rate}

Visit Our Office: {gmap_link}

Track your shipment: {tracking_link}

For assistance, feel free to contact us.

— {franchise_name}
Phone: {franchise_phone}
"""

    whatsapp_url = f"https://wa.me/{phone}?text={quote(message)}"
    return RedirectResponse(whatsapp_url, status_code=302)


# -------------------- SHIPMENTS LIST --------------------

@app.get("/shipments", response_class=HTMLResponse)
def shipments_page(request: Request, q: str = None, status: str = "BOOKED", msg: str = None, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    query = db.query(Shipment).join(Customer).order_by(Shipment.created_at.desc())

    if q:
        query = query.filter(
            (Shipment.tracking_id.ilike(f"%{q}%")) |
            (Shipment.destination_city.ilike(f"%{q}%")) |
            (Customer.phone.ilike(f"%{q}%"))
        )

    if status and status != 'ALL':
        query = query.filter(Shipment.status == status)

    start_dt, end_dt = parse_dates(start_date, end_date)
    if start_dt:
        query = query.filter(Shipment.created_at >= start_dt)
    if end_dt:
        query = query.filter(Shipment.created_at <= end_dt)

    shipments = query.limit(200).all()

    return templates.TemplateResponse("shipments.html", {
        "request": request,
        "shipments": shipments,
        "q": q or "",
        "status": status,
        "msg": msg,
        "start_date": start_date or "",
        "end_date": end_date or ""
    })
@app.get("/export-shipments")
def export_shipments(request: Request, q: str = None, status: str = "BOOKED", start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    query = db.query(Shipment).join(Customer).order_by(Shipment.created_at.desc())

    if q:
        query = query.filter(
            (Shipment.tracking_id.ilike(f"%{q}%")) |
            (Shipment.destination_city.ilike(f"%{q}%")) |
            (Customer.phone.ilike(f"%{q}%"))
        )

    if status and status != 'ALL':
        query = query.filter(Shipment.status == status)

    start_dt, end_dt = parse_dates(start_date, end_date)
    if start_dt:
        query = query.filter(Shipment.created_at >= start_dt)
    if end_dt:
        query = query.filter(Shipment.created_at <= end_dt)

    shipments = query.all()

    # Create Excel workbook in memory
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Shipments"

    # Write headers
    headers = ['Tracking ID', 'Customer Phone', 'Destination City', 'Rate', 'Status', 'Date']
    ws.append(headers)

    # Write data
    for s in shipments:
        ws.append([
            s.tracking_id,
            s.customer.phone if s.customer else 'N/A',
            s.destination_city,
            s.rate,
            s.status,
            s.created_at.strftime("%Y-%m-%d %H:%M")
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    # Generate filename
    filename = "shipments"
    if start_date and end_date:
        filename += f"_{start_date}_to_{end_date}"
    else:
        filename += f"_export_{datetime.utcnow().strftime('%Y%m%d')}"

    response = StreamingResponse(iter([stream.getvalue()]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}.xlsx"

    return response
@app.post("/deliver-shipment/{shipment_id}")
def deliver_shipment(request: Request, shipment_id: int, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment:
        shipment.status = "DELIVERED"
        db.commit()
        return JSONResponse({"ok": True, "msg": "Marked as Delivered"})
    return JSONResponse({"ok": False, "msg": "Shipment not found"}, status_code=404)


@app.post("/delete-shipment/{shipment_id}")
def delete_shipment(request: Request, shipment_id: int, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment:
        customer = shipment.customer
        if customer:
            customer.total_shipments = max(0, customer.total_shipments - 1)
        db.delete(shipment)
        db.commit()
        return JSONResponse({"ok": True, "msg": "Shipment Deleted"})
    return JSONResponse({"ok": False, "msg": "Shipment not found"}, status_code=404)



# -------------------- CUSTOMERS --------------------

@app.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, q: str = None, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    # Default to last 30 days if no date is provided
    now = datetime.utcnow()
    start_dt, end_dt = parse_dates(start_date, end_date)

    # We query all customers but if date range is applied we only show customers 
    # who had a visit within that date range.
    query = db.query(
        Customer.id,
        Customer.phone,
        Customer.total_shipments,
        Customer.last_visit,
        func.sum(Shipment.rate).label("total_revenue")
    ).outerjoin(Shipment).group_by(Customer.id).order_by(
        Customer.last_visit.desc()
    )

    if start_dt:
        query = query.filter(Customer.last_visit >= start_dt)
    if end_dt:
        query = query.filter(Customer.last_visit <= end_dt)

    if q:
        query = query.filter(Customer.phone.ilike(f"%{q}%"))

    customers = query.all()

    return templates.TemplateResponse("customers.html", {
        "request": request,
        "customers": customers,
        "q": q or "",
        "start_date": start_date or "",
        "end_date": end_date or ""
    })


@app.post("/delete-customer/{customer_id}")
def delete_customer(request: Request, customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer:
        db.delete(customer)
        db.commit()
        return JSONResponse({"ok": True, "msg": "Customer Deleted"})
    return JSONResponse({"ok": False, "msg": "Customer not found"}, status_code=404)


# -------------------- INSIGHTS --------------------

@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request, start_date: str = None, end_date: str = None, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/pin")

    start_dt, end_dt = parse_dates(start_date, end_date)

    inactive_threshold = datetime.utcnow() - timedelta(days=45)

    inactive_customers = db.query(Customer).filter(
        Customer.last_visit < inactive_threshold
    ).count()

    query = db.query(
        Shipment.destination_city,
        func.count(Shipment.id).label("count")
    )

    if start_dt:
        query = query.filter(Shipment.created_at >= start_dt)
    if end_dt:
        query = query.filter(Shipment.created_at <= end_dt)

    top_cities = query.group_by(Shipment.destination_city).order_by(
        func.count(Shipment.id).desc()
    ).limit(5).all()

    return templates.TemplateResponse("insights.html", {
        "request": request,
        "inactive_customers": inactive_customers,
        "top_cities": top_cities,
        "start_date": start_date or "",
        "end_date": end_date or ""
    })
