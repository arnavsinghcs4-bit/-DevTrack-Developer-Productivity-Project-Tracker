# DevTrack — Developer Productivity & Project Tracker

DevTrack is a full-stack developer cockpit designed to track DSA problem-solving, daily and weekly study goals, personal project milestones, and productivity metrics backed by genuine SQL analytics.

---

## 🛠️ Technology Stack

| Layer | Technology | Key Details |
| :--- | :--- | :--- |
| **Frontend** | React 19 + Vite | JavaScript, Plain CSS (CSS Modules), Reusable Components |
| **Backend** | Python 3.13 + FastAPI | RESTful API, Pydantic v2 schemas, Dependency Injection |
| **Database** | PostgreSQL 18 | Normalized 3NF Schema, Foreign Keys (`ON DELETE CASCADE`), Indexes |
| **ORM** | SQLAlchemy 2.x | Modern `Mapped[...]` and `mapped_column(...)` declarative syntax |
| **Migrations** | Alembic | Version-controlled schema migrations (`alembic upgrade head`) |
| **Authentication**| PyJWT + bcrypt | Secure salt hashing, Stateless Bearer token verification |
| **Testing** | pytest + httpx | Automated test suite for API endpoints |

---

## 📁 Project Architecture & Directory Structure

```text
DevTrack/
├── backend/
│   ├── alembic/              # Alembic migration environment and versions
│   │   ├── versions/         # Migration revision scripts
│   │   └── env.py            # Migration runtime configuration
│   ├── app/
│   │   ├── api/              # API endpoints and dependency injection
│   │   │   ├── deps.py       # get_db, get_current_user dependencies
│   │   │   └── v1/           # API v1 routers
│   │   ├── core/             # Configuration, database engine, security
│   │   │   ├── config.py     # Pydantic Settings and environment management
│   │   │   ├── database.py   # SQLAlchemy 2.0 engine and session factory
│   │   │   └── security.py   # bcrypt password hashing & JWT utilities
│   │   ├── models/           # SQLAlchemy 2.0 Declarative ORM models
│   │   │   ├── user.py
│   │   │   ├── dsa_problem.py
│   │   │   ├── goal.py
│   │   │   ├── task.py
│   │   │   └── project.py
│   │   ├── schemas/          # Pydantic models for validation and serialization
│   │   └── main.py           # FastAPI entrypoint, CORS configuration
│   ├── tests/                # Automated pytest suite
│   ├── alembic.ini           # Alembic CLI configuration
│   ├── pytest.ini            # Pytest configuration
│   ├── requirements.txt      # Python dependencies
│   ├── .env.example          # Template environment file
│   └── .env                  # Local environment file
├── frontend/                 # Vite + React Single Page Application
│   ├── src/
│   │   └── App.jsx           # App entrypoint (UI pending)
│   ├── package.json
│   └── vite.config.js
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### 1. Backend Setup
From the root directory:
```bash
# Navigate to backend
cd backend

# Activate virtual environment (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Configure your PostgreSQL database password in .env:
# POSTGRES_PASSWORD=your_password_here

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```
API Documentation will be interactively available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 2. Frontend Setup
In a new terminal window:
```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
The React application will be available at [http://localhost:5173](http://localhost:5173).

### 3. Running Backend Tests
```bash
cd backend
.venv\Scripts\pytest.exe
```

---

## 📡 API Overview

All endpoints below except `register` and `login` require a Bearer token obtained from `POST /api/v1/auth/login`.

| Method | Path | Description | Success |
| :--- | :--- | :--- | :--- |
| POST | `/api/v1/auth/register` | Create an account (8+ chars, ≤72 UTF-8 bytes); rate-limited per IP | 201 |
| POST | `/api/v1/auth/login` | Authenticate and obtain a JWT access token; rate-limited, timing-equalized | 200 |
| GET | `/api/v1/auth/me` | Current user profile | 200 |
| POST | `/api/v1/dsa-problems` | Create a DSA problem record | 201 |
| GET | `/api/v1/dsa-problems` | List own records (paginated: `page`, `page_size` ≤ 100) | 200 |
| GET | `/api/v1/dsa-problems/{id}` | Retrieve one record (owner only) | 200 |
| PATCH | `/api/v1/dsa-problems/{id}` | Partial update of allowed fields (owner only) | 200 |
| DELETE | `/api/v1/dsa-problems/{id}` | Delete a record (owner only) | 204 |
| POST | `/api/v1/goals` | Create a daily/weekly goal (date range validated) | 201 |
| GET | `/api/v1/goals` | List own goals (paginated) | 200 |
| GET / PATCH / DELETE | `/api/v1/goals/{id}` | Retrieve / update / delete a goal (owner only) | 200 / 200 / 204 |
| POST | `/api/v1/tasks` | Create a task (`project_id` must reference an owned project) | 201 |
| GET | `/api/v1/tasks` | List own tasks (paginated; filter by `status`, `priority`) | 200 |
| GET / PATCH / DELETE | `/api/v1/tasks/{id}` | Retrieve / update / delete a task (owner only) | 200 / 200 / 204 |
| POST | `/api/v1/projects` | Create a project (http(s)-only URLs) | 201 |
| GET | `/api/v1/projects` | List own projects (paginated) | 200 |
| GET / PATCH / DELETE | `/api/v1/projects/{id}` | Retrieve / update / delete a project (owner only) | 200 / 200 / 204 |
| POST | `/api/v1/projects/{id}/milestones` | Create a milestone under an owned project | 201 |
| GET | `/api/v1/projects/{id}/milestones` | List a project's milestones (paginated) | 200 |
| GET / PATCH / DELETE | `/api/v1/projects/{id}/milestones/{mid}` | Retrieve / update / delete a milestone | 200 / 200 / 204 |
| GET | `/api/v1/analytics/dashboard` | SQL-aggregated metrics: breakdowns, dense solve trend (`days` = 1-365), completion and overdue rates | 200 |

Ownership is enforced inside every SQL query: another user's record returns the same `404` as a missing one, and client-supplied ownership fields are rejected with `422`. Milestones have no `user_id` column — ownership flows through the parent project via a SQL join. All analytics queries are aggregated in the database (`GROUP BY`, `COUNT(DISTINCT)`, conditional `SUM(CASE)`, `AVG`) and scoped to the authenticated user.

---

## 💡 Key Software Engineering Decisions (Interview Talking Points)

1. **SQLAlchemy 2.0 Modern Declarative Syntax**:
   Instead of legacy `Column(Integer, ...)` declarations, models use type-annotated `Mapped[int] = mapped_column(...)`. This provides strict static analysis and autocomplete.

2. **Multi-Tenant User Isolation (IDOR Protection)**:
   Every business entity (`DSAProblem`, `Goal`, `Task`, `Project`) strictly references `users.id` with `ondelete="CASCADE"`. Every single database query explicitly filters by `user_id == current_user.id`, preventing Insecure Direct Object References.

3. **Composite Database Indexing**:
   Indices such as `(user_id, topic)`, `(user_id, difficulty)`, and `(user_id, status, priority)` are placed at the database layer to ensure queries execute in $O(\log n)$ time rather than full table scans when aggregating dashboard metrics.

4. **Python 3.13 Security Compatibility**:
   In Python 3.13, the legacy standard library `crypt` module was removed (PEP 594), causing unmaintained packages like `passlib` to fail. DevTrack uses `bcrypt` directly with cryptographically secure random salts, paired with `PyJWT` for stateless tokens.

5. **Auth Abuse Protection (Rate Limiting + Timing Equalization)**:
   `POST /auth/login` and `POST /auth/register` are guarded by a per-IP sliding-window limiter (default 10/min and 5/min) returning `429` with a `Retry-After` header; rejected requests are not recorded so a blocked client cannot extend its own lockout. Independently, login performs exactly one bcrypt comparison on every attempt — against a dummy hash when the email is unknown — so response timing cannot reveal whether an account exists (user enumeration via timing side channel). The limiter is an injectable FastAPI dependency: tests override it exactly like `get_db`, and storage is single-process by design (swap `app/core/rate_limit.py` for Redis when scaling to multiple workers).

6. **Continuous Integration (GitHub Actions)**:
   Every push and pull request to `main` runs the full pytest suite on a clean Linux runner with no `.env`, no secrets, and no database service — the suite executes entirely against in-memory SQLite, proving test isolation from the Neon production database.
