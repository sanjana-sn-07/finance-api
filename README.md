# Personal Finance REST API

A production-grade REST API for personal finance management — built with FastAPI, PostgreSQL, Redis, JWT auth, Plaid bank integration, and OpenAI auto-categorization.

**Live:** https://finance-api-production-7467.up.railway.app
**Docs:** https://finance-api-production-7467.up.railway.app/docs
**Blog post:** https://medium.com/@sanjana.sn.07/how-i-built-a-production-grade-personal-finance-rest-api-with-fastapi-plaid-and-gpt-4o-mini-5bfd108c803a

---

## Features

- **JWT Authentication** — register, login, token-based access on all endpoints
- **Transaction Management** — create, list, and retrieve transactions
- **AI Auto-Categorization** — GPT-4o-mini automatically categorizes transactions by description
- **Budget Tracking** — spending totals grouped by category
- **Financial Summary** — total spent, transaction count, top spending category (Redis-cached)
- **Plaid Bank Integration** — link real/sandbox bank accounts, sync transactions via webhook
- **Pandas Report** — monthly spending breakdown by category
- **86% test coverage** — 30 pytest unit tests

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL (SQLAlchemy ORM) |
| Cache | Redis (60s TTL on /summary) |
| Auth | JWT (python-jose) + bcrypt |
| AI | OpenAI GPT-4o-mini |
| Bank Data | Plaid API (sandbox) |
| Analytics | Pandas |
| Testing | pytest + pytest-cov |
| Deployment | Railway (Docker) |

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/register` | No | Create account |
| POST | `/token` | No | Login, get JWT |
| GET | `/transactions` | Yes | List all transactions |
| GET | `/transactions/{id}` | Yes | Get one transaction |
| POST | `/transactions` | Yes | Create transaction (AI-categorized) |
| GET | `/budget` | Yes | Spending by category |
| GET | `/summary` | Yes | Total spent + top category (cached) |
| GET | `/report` | Yes | Monthly Pandas breakdown |
| POST | `/plaid/sandbox/setup` | Yes | Link sandbox bank account |
| POST | `/plaid/sync` | Yes | Sync transactions from bank |
| POST | `/plaid/webhook` | No | Receive Plaid webhook events |

---

## Run Locally

**Prerequisites:** Docker Desktop, Python 3.12

```bash
git clone https://github.com/sanjana-sn-07/finance-api.git
cd finance-api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create `.env`:
```
DATABASE_URL=postgresql://financeuser:financepass@localhost:5432/financedb
OPENAI_API_KEY=your-openai-key
PLAID_CLIENT_ID=your-plaid-client-id
PLAID_SECRET=your-plaid-sandbox-secret
PLAID_ENV=sandbox
SECRET_KEY=your-secret-key
REDIS_URL=redis://localhost:6379/0
```

Start services and run:
```bash
docker-compose up -d
uvicorn main:app --reload
```

Open http://localhost:8000/docs

---

## Run Tests

```bash
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Architecture

Built with a clean layered structure:

```
main.py          — FastAPI app + all endpoints
auth.py          — JWT token creation + bcrypt password hashing
cache.py         — Redis caching helpers
database.py      — SQLAlchemy engine + session management
models.py        — PostgreSQL table definitions (Transaction, User)
schemas.py       — Pydantic request/response validation
plaid_service.py — Plaid API client + transaction sync
tests/           — 30 pytest unit tests (86% coverage)
Dockerfile       — Production container
docker-compose.yaml — Local dev (PostgreSQL + Redis)
```
