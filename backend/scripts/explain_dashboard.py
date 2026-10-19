"""
EXPLAIN ANALYZE harness for the DevTrack dashboard queries.

Runs the *exact* production statements (imported from
app.api.v1.analytics.build_dashboard_statements — no copy-paste drift)
through the target database's EXPLAIN machinery and prints the plans, so
index choices and real execution times can be inspected against realistic
data volumes.

Usage (from backend/):
  # Local throwaway SQLite benchmark that seeds its own demo data:
  python scripts/explain_dashboard.py --database-url sqlite:///./bench.db --seed 2000

  # Local Postgres (falls back to DATABASE_URL/.env settings when the
  # --database-url flag is omitted):
  python scripts/explain_dashboard.py --seed 2000

  # Remove seeded benchmark data again:
  python scripts/explain_dashboard.py --database-url sqlite:///./bench.db --cleanup

Safety rails (this project never touches production data):
- A non-localhost host (e.g. *.neon.tech) is REFUSED unless --allow-remote
  is passed explicitly — and even then the harness is strictly read-only:
  EXPLAIN ANALYZE executes the SELECTs (that is how Postgres gets real
  timings) but --seed and --cleanup are permanently disabled for remote
  targets. When in doubt, point it at a local clone.
- The connection URL is always printed redacted (credentials masked).
"""
import argparse
import os
import random
import re
import sys
from datetime import date, timedelta
from time import perf_counter

# backend/ on sys.path so `app.*` imports work when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.v1.analytics import build_dashboard_statements  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.dsa_problem import DSAProblem  # noqa: E402
from app.models.goal import Goal  # noqa: E402
from app.models.project import Milestone, Project  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User  # noqa: E402

BENCH_EMAIL = "bench@devtrack.local"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "")


def redact(url: str) -> str:
    """Masks credentials in a connection URL for safe printing."""
    return re.sub(r"//[^@/]+@", "//***@", url)


def host_of(url: str) -> str:
    """Best-effort host extraction without importing URL parsers."""
    after_scheme = re.sub(r"^[^:]+://", "", url)
    authority = after_scheme.split("/")[0]
    return authority.split("@")[-1].split(":")[0]


def is_remote(url: str) -> bool:
    return host_of(url) not in LOCAL_HOSTS


def seed_benchmark_data(session: Session, problems: int) -> None:
    """Seeds one bench user with volumes proportional to `problems`."""
    rng = random.Random(20261019)
    today = date.today()
    topics = ["Arrays", "Trees", "Graphs", "Dynamic Programming", "Binary Search"]
    difficulties = ["Easy", "Medium", "Hard"]

    session.add(
        User(
            email=BENCH_EMAIL,
            hashed_password="bench-seed-not-a-real-hash",
            full_name="Benchmark User",
        )
    )
    session.flush()  # obtain user.id

    uid = session.execute(select(User.id).where(User.email == BENCH_EMAIL)).scalar_one()

    session.execute(
        DSAProblem.__table__.insert(),
        [
            {
                "user_id": uid,
                "title": f"Bench problem {i}",
                "platform": "LeetCode",
                "topic": rng.choice(topics),
                "difficulty": rng.choice(difficulties),
                "solved_date": today - timedelta(days=rng.randrange(0, 730)),
            }
            for i in range(problems)
        ],
    )
    session.execute(
        Goal.__table__.insert(),
        [
            {
                "user_id": uid,
                "title": f"Bench goal {i}",
                "goal_type": rng.choice(["daily", "weekly"]),
                "target_count": 5,
                "current_count": rng.randint(0, 5),
                "start_date": today - timedelta(days=rng.randrange(0, 90)),
                "is_completed": rng.random() < 0.6,
            }
            for i in range(max(10, problems // 10))
        ],
    )
    session.execute(
        Task.__table__.insert(),
        [
            {
                "user_id": uid,
                "title": f"Bench task {i}",
                "status": rng.choice(["todo", "in_progress", "done"]),
                "priority": rng.choice(["low", "medium", "high"]),
                "due_date": today + timedelta(days=rng.randint(-30, 30)),
            }
            for i in range(max(20, problems // 3))
        ],
    )
    n_projects = max(4, problems // 50)
    session.execute(
        Project.__table__.insert(),
        [
            {"user_id": uid, "title": f"Bench project {i}", "status": "in_progress"}
            for i in range(n_projects)
        ],
    )
    project_ids = [
        row[0]
        for row in session.execute(select(Project.id).where(Project.user_id == uid)).all()
    ]
    session.execute(
        Milestone.__table__.insert(),
        [
            {
                "project_id": pid,
                "title": f"Bench milestone {pid}-{j}",
                "is_completed": rng.random() < 0.5,
            }
            for pid in project_ids
            for j in range(4)
        ],
    )
    session.commit()
    print(
        f"Seeded bench user: {problems} problems, {max(10, problems // 10)} goals, "
        f"{max(20, problems // 3)} tasks, {len(project_ids)} projects "
        f"(+{len(project_ids) * 4} milestones)\n"
    )


def cleanup_benchmark_data(session: Session) -> None:
    user = session.execute(
        select(User).where(User.email == BENCH_EMAIL)
    ).scalar_one_or_none()
    if user is None:
        print("No bench user found; nothing to clean up.")
        return
    session.delete(user)  # ORM cascade removes goals/tasks/projects/milestones/tokens
    session.commit()
    print("Removed bench user and all associated rows.")


def explain_all(url: str, days: int) -> None:
    """EXPLAINs every dashboard statement against the target engine."""
    engine = create_engine(url)
    dialect = engine.dialect.name
    today = date.today()

    with Session(engine) as session:
        bench_uid = session.execute(
            select(User.id).where(User.email == BENCH_EMAIL)
        ).scalar_one_or_none()
        if bench_uid is None:
            any_uid = session.execute(select(User.id)).scalars().first()
            if any_uid is None:
                sys.exit("No users in the database — run with --seed first.")
            bench_uid = any_uid
            print(f"(no bench user; using existing user id {bench_uid})\n")

        stmts = build_dashboard_statements(bench_uid, today, days)

        for name, stmt in stmts.items():
            compiled = stmt.compile(
                dialect=engine.dialect, compile_kwargs={"literal_binds": True}
            )
            print(f"--- {name} " + "-" * max(1, 62 - len(name)))
            if dialect == "postgresql":
                # ANALYZE actually executes the query (read-only) and reports
                # real per-node timings and buffer usage
                for row in session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {compiled}")):
                    print(f"  {row[0]}")
            else:
                for row in session.execute(text(f"EXPLAIN QUERY PLAN {compiled}")):
                    print(f"  {row[-1]}")
                started = perf_counter()
                session.execute(stmt).all()
                print(f"  [executed in {(perf_counter() - started) * 1000:.2f} ms]")
            print()

    engine.dispose()


def main() -> None:
    from app.core.config import settings  # deferred: needs sys.path set first

    parser = argparse.ArgumentParser(
        description="EXPLAIN the production dashboard queries against a real database."
    )
    parser.add_argument("--database-url", default=None,
                        help="Target URL (default: DATABASE_URL/.env settings)")
    parser.add_argument("--days", type=int, default=30,
                        help="Trend window in days (default 30)")
    parser.add_argument("--seed", type=int, default=0, metavar="N",
                        help="Seed a bench user with N DSA problems (local targets only)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete the bench user and all its rows (local targets only)")
    parser.add_argument("--allow-remote", action="store_true",
                        help="Permit connecting to a non-localhost host (read-only; no seeding)")
    args = parser.parse_args()

    url = args.database_url or settings.SQLALCHEMY_DATABASE_URI
    print(f"Target: {redact(url)}")

    if is_remote(url):
        if not args.allow_remote:
            sys.exit(
                "REFUSED: this looks like a remote database. This harness runs "
                "EXPLAIN ANALYZE (which executes the queries). Per project policy, "
                "production data is never touched — run against a local clone, or "
                "pass --allow-remote for strictly read-only EXPLAIN on a dev endpoint."
            )
        if args.seed or args.cleanup:
            sys.exit("--seed/--cleanup are disabled for remote targets (read-only mode).")
        print("Remote target: read-only EXPLAIN mode (seeding/cleanup unavailable).")

    engine = create_engine(url)
    tables_present = inspect(engine).has_table("users")

    if args.seed:
        if not tables_present:
            if url.startswith("sqlite"):
                Base.metadata.create_all(engine)
                print("Created schema in throwaway SQLite benchmark file.\n")
            else:
                sys.exit("Tables missing — run `alembic upgrade head` first.")
        with Session(engine) as session:
            if session.execute(
                select(User.id).where(User.email == BENCH_EMAIL)
            ).scalar_one_or_none():
                sys.exit("Bench user already exists — run --cleanup first.")
            seed_benchmark_data(session, args.seed)
    elif args.cleanup:
        with Session(engine) as session:
            cleanup_benchmark_data(session)
        engine.dispose()
        return
    elif not tables_present:
        sys.exit("Tables missing — run `alembic upgrade head` or use --seed with SQLite.")

    engine.dispose()
    explain_all(url, args.days)


if __name__ == "__main__":
    main()
