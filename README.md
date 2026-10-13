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
│   │   ├── components/       # Reusable UI components
│   │   ├── context/          # Global AuthContext & state
│   │   ├── services/         # Centralized API fetch wrapper
│   │   └── App.jsx           # App entrypoint
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

## 💡 Key Software Engineering Decisions (Interview Talking Points)

1. **SQLAlchemy 2.0 Modern Declarative Syntax**:
   Instead of legacy `Column(Integer, ...)` declarations, models use type-annotated `Mapped[int] = mapped_column(...)`. This provides strict static analysis and autocomplete.

2. **Multi-Tenant User Isolation (IDOR Protection)**:
   Every business entity (`DSAProblem`, `Goal`, `Task`, `Project`) strictly references `users.id` with `ondelete="CASCADE"`. Every single database query explicitly filters by `user_id == current_user.id`, preventing Insecure Direct Object References.

3. **Composite Database Indexing**:
   Indices such as `(user_id, topic)`, `(user_id, difficulty)`, and `(user_id, status, priority)` are placed at the database layer to ensure queries execute in $O(\log n)$ time rather than full table scans when aggregating dashboard metrics.

4. **Python 3.13 Security Compatibility**:
   In Python 3.13, the legacy standard library `crypt` module was removed (PEP 594), causing unmaintained packages like `passlib` to fail. DevTrack uses `bcrypt` directly with cryptographically secure random salts, paired with `PyJWT` for stateless tokens.
