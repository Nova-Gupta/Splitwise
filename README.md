# SplitSmart — Shared Expenses App

> Built for an internship assignment. Tracks shared flat expenses with proper group membership timelines, multi-currency support, and a deliberate CSV importer that catches 27 data anomalies in the provided `expenses_export.csv`.

## Live Demo

- **App (frontend):** https://splitsmart-3pyw.onrender.com
- **API (backend):** https://splitwise-api-urn0.onrender.com
- **GitHub:** https://github.com/Nova-Gupta/Splitwise

---

## Quick Start (Local)

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Backend

```bash
cd backend
pip install flask flask-cors pyjwt werkzeug
python app.py           # runs on http://localhost:5000
```

On first run, `app.py` calls `init_db()` which creates `splitwise.db` from `schema.sql`.

Then seed demo users and the flat group:

```bash
python seed.py
# Creates: aisha, rohan, priya, meera, sam, dev — all password: pass123
# Creates: "Flat Expenses" group with correct membership dates
```

### 2. Frontend

```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:5000 npm start
# Opens http://localhost:3000
```

### 3. Import the CSV

1. Log in as `aisha` (password `pass123`)
2. Click on **Flat Expenses** group
3. Go to **Import** tab
4. Upload `expenses_export.csv`
5. Review the import report — it shows all 27 anomalies detected, 2 rows skipped, 1 held for approval

---

## Demo Accounts

| Username | Password | Display name | Active period     |
|----------|----------|--------------|-------------------|
| aisha    | pass123  | Aisha        | Feb 2026–present  |
| rohan    | pass123  | Rohan        | Feb 2026–present  |
| priya    | pass123  | Priya        | Feb 2026–present  |
| meera    | pass123  | Meera        | Feb–Mar 2026      |
| sam      | pass123  | Sam          | Apr 2026–present  |
| dev      | pass123  | Dev          | Mar 2026 (Goa)    |

---

## Deployment (Render.com)

### Backend (Web Service)

| Field     | Value                              |
|-----------|------------------------------------|
| Root dir  | `backend/`                         |
| Build     | `pip install flask flask-cors pyjwt werkzeug && python seed.py` |
| Start     | `python app.py`                    |
| Env vars  | `SECRET_KEY=<random>`, `PORT=10000` |

### Frontend (Static Site)

| Field     | Value                                              |
|-----------|----------------------------------------------------|
| Root dir  | `frontend/`                                        |
| Build     | `npm install && npm run build`                     |
| Publish   | `build/`                                           |
| Env var   | `REACT_APP_API_URL=https://splitwise-api-urn0.onrender.com` |

---

## Tech Stack

| Layer    | Technology                                 |
|----------|--------------------------------------------|
| Backend  | Python 3.12 / Flask 3, PyJWT               |
| Database | SQLite 3 (relational, FK constraints, WAL) |
| Frontend | React 18, Create React App (single SPA)    |
| Auth     | JWT (7-day expiry, stored in localStorage) |
| AI       | Claude (Anthropic) — see `AI_USAGE.md`    |

**Why SQLite?** The assignment requires a relational DB. SQLite is fully relational (ACID, FK constraints, JOINs). For a flat of 6 people with ~50 expenses, it is more than adequate. See `DECISIONS.md` D1 for the full reasoning.

---

## Project Structure

```
splitwise-app/
├── backend/
│   ├── app.py          # All Flask routes + CSV importer (920 lines)
│   ├── schema.sql      # Relational DB schema (8 tables)
│   ├── seed.py         # Seeds demo users + group with correct membership dates
│   ├── requirements.txt
│   └── splitwise.db    # SQLite database (auto-created on first run)
├── frontend/
│   └── src/
│       ├── App.js      # Complete React SPA (969 lines, intentionally single file)
│       └── App.css     # All styles (626 lines, full dark mode + design tokens)
├── expenses_export.csv # Sample CSV with deliberate anomalies
├── SCOPE.md            # Anomaly log (27 detected) + DB schema documentation
├── DECISIONS.md        # Engineering decision log (10 decisions)
└── AI_USAGE.md         # AI tool usage, key prompts, 4 cases where AI was wrong
```

---

## Features

- **Login/register** with JWT authentication
- **Group management** with time-based membership (join/leave dates)
- **Expense creation** supporting `equal`, `exact`, `percentage`, `share` split types
- **Multi-currency** — USD expenses are converted to INR at historical monthly rates
- **Balance summary** — net balance per person + minimum suggested payments (Aisha's requirement)
- **Expense drill-down** — see exactly which expenses make up any balance (Rohan's requirement)
- **Settlement recording** — record payments to clear debts
- **CSV import** with a full anomaly report: 27 anomalies detected, policies documented per anomaly
- **Duplicate approval queue** — potential duplicates held for user approval before import (Meera's requirement)
- **Membership-aware splits** — expenses dated outside a member's active period don't affect them (Sam's requirement)
- **Dark mode** — toggle between light and dark themes, preference saved to localStorage
