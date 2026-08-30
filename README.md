# RevShield AI — Autonomous Failed Payment Recovery Engine

An autonomous engine that detects, diagnoses, and recovers failed payments using a rule-based + ML + LLM progressive intelligence architecture.

> **Primary KPI:** Incremental Net Revenue Recovered

---

## Architecture

```
Payment Event → Detection → Diagnosis → Strategy → Policy Gateway → Action → Outcome → Learning
```

Full architecture and implementation plan: see `implementation_plan.md` in AI memory.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Database | PostgreSQL 16 / SQLite fallback |
| Workflow Engine | Temporal |
| Event Queue | Redis Streams |
| ML | scikit-learn, XGBoost |
| LLM | OpenAI (Phase 9, with guardrails) |
| Frontend | Next.js 14 + TypeScript |

---

## Cloud Deployment (Render)

The backend engine is live and deployed on **Render**:

- **Live Service URL**: `https://revshield-ai.onrender.com`
- **Live Health Check**: `https://revshield-ai.onrender.com/health`
- **Interactive Swagger UI**: `https://revshield-ai.onrender.com/docs`
- **Public Razorpay Webhook Target**: `https://revshield-ai.onrender.com/api/v1/webhooks/razorpay/payment`

### Deployment Architecture & Environment Configuration

| Setting | Configuration Value | Description |
|---|---|---|
| **Python Version** | `3.11.9` | Pinned in Render environment variables (`PYTHON_VERSION=3.11.9`) for Pydantic v2 / Maturin wheel stability. |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Production Uvicorn ASGI server bound to dynamic Render `$PORT`. |
| **CORS Policy** | Wildcard / Multi-Origin Enabled | Allows cross-origin REST requests from local (`http://localhost:3000`) and cloud frontends (Vercel/Netlify). |
| **Database Resilience** | Dual-Engine DB | Automatic fallback between PostgreSQL 16 and SQLite for zero-downtime container launches. |
| **Queue Fallback** | Graceful Single-Node Handling | EventQueuePublisher operates seamlessly with or without external Redis instance. |

### Frontend Environment Setup
To connect your local Next.js frontend or production deployment to the live Render backend, configure `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=https://revshield-ai.onrender.com/api/v1
```

---

## Quick Start

### Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js 20+

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env with your values
```

### 2. Start Infrastructure

```bash
docker-compose up -d postgres redis temporal temporal-ui pgadmin
```

Services available:
| Service | URL |
|---|---|
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Temporal Server | `localhost:7233` |
| Temporal UI | http://localhost:8080 |
| pgAdmin | http://localhost:5050 |

### 3. Run Database Migrations

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
```

### 4. Start Backend

```bash
cd backend
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### 5. Start Temporal Worker

```bash
cd backend
python -m temporal.worker
```

---

## Project Structure

```
Revenue Recovery Agent/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI route handlers
│   │   ├── core/            # Config, DB, logging, exceptions
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic schemas + agent contracts
│   │   ├── repositories/    # DB access layer (Phase 1+)
│   │   └── services/        # Business logic (Phase 2+)
│   ├── alembic/             # Database migrations
│   ├── failure_taxonomy.yaml
│   └── requirements.txt
├── temporal/
│   ├── workflows/           # Temporal workflow definitions (Phase 4+)
│   └── activities/          # Temporal activity implementations (Phase 2+)
├── frontend/                # Next.js dashboard (Phase 1+)
├── infra/
│   └── scripts/init.sql
├── docker-compose.yaml
└── .env.example
```

---

## Build Phases

| Phase | Goal | Status |
|---|---|---|
| **Phase 0** | Project foundation | ✅ Complete |
| **Phase 1** | Payment event pipeline | ✅ Complete |
| **Phase 2** | Detection agent | ✅ Complete |
| **Phase 3** | Diagnosis agent | ✅ Complete |
| **Phase 4** | Strategy engine | ✅ Complete |
| **Phase 5** | Policy gateway & Human Approval Queue | ✅ Complete |
| **Phase 6** | Action agent & Intervention execution | ✅ Complete |
| **Phase 7** | Outcome & Incremental Learning | ✅ Complete |
| **Phase 8** | ML models & predictive scoring | ⬜ Planned |
| **Phase 9** | LLM capabilities & guardrails | ⬜ Planned |

---

## Key System Features & Architecture

### 1. Autonomous 6-Stage Recovery Pipeline
The engine processes failed payment events through a deterministic, auditable 6-stage lifecycle:
1. **Detect Agent**: Evaluates event eligibility, calculates recoverability score, assigns priority (`HIGH`/`MEDIUM`/`LOW`), and instantiates `RecoveryOpportunity`.
2. **Diagnosis Agent**: Classifies failure cause using `failure_taxonomy.yaml` rule engine and customer history (`TAX-xxx` taxonomy classification).
3. **Strategy Engine**: Ranks candidate interventions using Expected Net Recovery ($\text{ENR} = P(\text{success}) \times \text{Revenue} - \text{Cost}$), selecting optimal actions (`PAYMENT_LINK`, `RETRY`, `REMINDER`, `HUMAN_ESCALATION`).
4. **Policy Gateway**: Enforces hard merchant guardrails (retry caps, channel restrictions, cost limits, auto-approval thresholds). Auto-issues HMAC clearance tokens for low-risk items and routes high-value transactions to the **Human Approval Queue**.
5. **Action Agent**: Dispatches approved intervention to gateway sandbox (`ActionService`), creating `Intervention` records.
6. **Outcome & Learning Agent**: Evaluates time-window attribution, records `RecoveryOutcome`, updates strategy probability feedback matrix, and marks status as `RECOVERED` or `FAILED`.

### 2. Single-Page Unified Control Dashboard
- **Hero Metrics Strip**: Top-level KPI cards for *Revenue at Risk*, *Recovered Amount*, *Net Profit*, and *Pending Actions* with animated gauge indicators.
- **Live Recovery Pipeline**: Real-time opportunity feed featuring a 6-dot stepper tracking live stage progression (`Detect` → `Diagnose` → `Strategy` → `Policy` → `Action` → `Outcome`).
- **Human Approval Queue**: High-value transaction sign-off panel issuing cryptographic HMAC clearance tokens.
- **Agent Trace Inspector**: Comprehensive modal inspector for deep-diving into formatted stage-by-stage outputs, AI reasoning narratives, policy rule checklists, and raw JSON snapshots (`GET /api/v1/opportunities/{id}/agent-trace`).

### 3. Engine Resilience & Database Flexibility
- **Dual DB Architecture**: Async PostgreSQL 16 primary connection pool with automatic fallback to local SQLite (`sqlite+aiosqlite:///./revenue_recovery.db`) for zero-dependency execution.
- **Robust Exception Handling**: Global FastAPI exception handlers and frontend `try/catch` wrappers ensuring high availability and zero runtime error modal crashes.

### 4. Real-Time Webhook & Gateway Integration (Razorpay)
- **Live Public Webhook Ingestion**: Deployed with active cloud webhook endpoint `https://revshield-ai.onrender.com/api/v1/webhooks/razorpay/payment` featuring HMAC-SHA256 signature validation (`X-Razorpay-Signature`) to ingest real-time payment failure events directly from Razorpay Dashboard.
- **Interactive Event Simulation**: Provides `/api/v1/simulate/payment-failure` for instant testing and multi-scenario demonstration without needing live credit card declines.
- **Intervention Execution**: Dispatches automated recovery actions via Razorpay API sandbox:
  - `PAYMENT_LINK`: Generates dynamic hosted payment links for customer re-payment.
  - `RETRY`: Re-attempts automated card/UPI charges during high-success bank time windows.
  - `REMINDER`: Dispatches automated SMS/email payment notifications.
- **Circuit Breaker Protection**: Wraps gateway calls in a `CircuitBreaker` (`razorpay_circuit_breaker`) to prevent cascading downstream timeout failures.
- **Production Schema Parity**: Operates on native Razorpay event payloads for zero-code changes when switching between sandbox and live production credentials.

---

## Code Standards

- **50 → 10-15 lines rule**: Review before writing. Reduce verbose patterns.
- **No raw dicts between agents**: All inter-agent communication uses Pydantic models.
- **Registry pattern** for routing/agent registration.
- **Repository pattern** for all DB access.
- **Config-driven** taxonomy and policy rules.

See `knowledge/code-writing-rules/artifacts/rules.md` for full standards.

---

## API Documentation

- **Live Deployed Swagger UI**: https://revshield-ai.onrender.com/docs
- **Local Development Swagger UI**: http://localhost:8000/docs
- **ReDoc**: https://revshield-ai.onrender.com/redoc
- **OpenAPI JSON**: https://revshield-ai.onrender.com/openapi.json
