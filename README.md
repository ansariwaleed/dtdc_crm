# DTDC CRM System

A premium CRM designed for DTDC franchises. Features include shipment booking, WhatsApp integration, customer LTV (Life Time Value) tracking, and data insights.

## Features
- **Modern Dashboard**: View daily & monthly revenue and shipment counts.
- **Glassmorphic UI**: Premium aesthetics using Blur-effects and Tailwind CSS.
- **Booking & WhatsApp**: Instant WhatsApp message generation with tracking links.
- **Client Insights**: Identify repeat customers and dominant delivery lanes.
- **Security**: PIN-protected access.

---

## 🛠 Local Setup

1. **Clone the repository.**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Set Environment Variables** (Optional, creates `.env`):
   ```env
   APP_PIN=1234
   SECRET_KEY=yoursecretkey
   ```
4. **Run the app**:
   ```bash
   uvicorn app.main:app --reload
   ```

---

## 🚀 Free Deployment Guide (Render)

### 1. Database (Persistent Storage)
Since Render's Free tier has ephemeral storage, you should use a **free PostgreSQL provider** for persistence:
- **Neon.tech** (Highly Recommended - Always Free PostgreSQL tier)
- **Supabase**

**Steps**:
1. Create a free project on [Neon.tech](https://neon.tech).
2. Get the `DATABASE_URL` (should look like `postgresql://user:pass@host/dbname?sslmode=require`).

### 2. Deploy to Render
1. Create a [Render](https://render.com) account.
2. Link your GitHub repository.
3. Render will auto-detect `render.yaml`.
4. **Environment Variables on Render**:
   - `DATABASE_URL`: Your Neon/Supabase DB URL.
   - `APP_PIN`: Set your desired 4-digit PIN.
   - `SECRET_KEY`: Set a random secure string.

5. Click **Deploy**.

---

## 📁 Technical Info
- **Framework**: FastAPI
- **Database**: SQLAlchemy (Supports SQLite & PostgreSQL)
- **Styling**: Tailwind CSS + Inter Font + Lucide Icons
- **Server**: Gunicorn + Uvicorn Workers
