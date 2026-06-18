# NMALIS — National Medical Accreditation and Licensing Information System

B2B regulatory platform for reciprocal credibility verification between KMPDC (regulator), hospital administrators, and medical practitioners.

**Stack:** Django 5 · PostgreSQL (SQLite for local dev) · Bootstrap 5

## Features

| Module | Role | Capabilities |
|--------|------|----------------|
| Authority Control | `regulator` | Document verification, accountability-gated enforcement, compliance analytics, audit trail |
| Institutional Management | `hospital_admin` | Staff roster, **Doctor Credibility Check**, facility renewal |
| Practitioner Professional | `practitioner` | License dashboard, CPD renewal, **Hospital Credibility Check** |
| Trust Bridge | All | Suspension propagation alerts, verification logging, automated compliance |

## Quick start

```bash
cd "project 4th year"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py seed_large_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/

### Regulator workflow (login as `regulator`)

1. **Documents** — review licenses, indemnity, CPD, and accreditation files; mark verified or rejected.
2. **Practitioners / Facilities** — open a record, review documents, then **Enforce** to change status.
3. **Accountability checkbox** — required before any status change; suspension/revocation also requires a written reason. Logged in the audit trail.

### Demo accounts (password: `demo1234`)

| Username | Role |
|----------|------|
| `regulator` | KMPDC regulator |
| `hospital_admin` | Hospital administrator |
| `doctor_sample` | Practitioner (Dr. Sample) |

**Credibility check examples:**

- Doctor license: `KMP-2024-001` (active) · `KMP-2022-118` (suspended)
- Facility: `FAC-KEN-001` (accredited) · `FAC-GHOST-999` (suspended)

## PostgreSQL

Set in `.env`:

```
DATABASE_URL=postgresql://user:password@localhost:5432/nmalis
```

Create the database, then run `migrate` and `seed_demo` as above.

## Project structure

```
config/          # Django settings
registry/        # Models, views, Trust Bridge services
templates/       # Role-based dashboards
static/          # CSS
```

## Author

Cyprian Abel Kigen Rotich — Kabarak University, CS/MK/0741/09/23
