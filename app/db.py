"""
DuckDB schema management and bulk data loading for DevBuddy.
"""
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from .parser import parse_all_sessions, build_daily_usage, build_project_breakdown, build_top_prompts


def get_db_path() -> str:
    base = Path(__file__).parent.parent
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "devbuddy.duckdb")


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT,
            project TEXT,
            date DATE,
            timestamp TIMESTAMP,
            first_prompt TEXT,
            model TEXT,
            query_count INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_creation_tokens INTEGER,
            cache_read_tokens INTEGER,
            total_tokens INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id INTEGER,
            session_id TEXT,
            project TEXT,
            date DATE,
            timestamp TIMESTAMP,
            user_prompt TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_creation_tokens INTEGER,
            cache_read_tokens INTEGER,
            total_tokens INTEGER,
            tools TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            date DATE,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            session_count INTEGER,
            query_count INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS top_prompts (
            id INTEGER,
            project TEXT,
            user_prompt TEXT,
            total_tokens INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            query_count INTEGER
        )
    """)
    # Phase 2.1 migration: drop cost_usd columns from existing tables
    for _table in ("sessions", "queries", "daily_usage", "top_prompts"):
        try:
            con.execute(f"ALTER TABLE {_table} DROP COLUMN cost_usd")
        except Exception:
            pass


def load_real_data(
    con: duckdb.DuckDBPyConnection,
    sessions: list[dict],
    queries: list[dict],
    daily: list[dict],
    top_prompts: list[dict],
) -> None:
    con.execute("DELETE FROM sessions")
    con.execute("DELETE FROM queries")
    con.execute("DELETE FROM daily_usage")
    con.execute("DELETE FROM top_prompts")

    for s in sessions:
        con.execute(
            """INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                s["session_id"], s["project"],
                s["date"] if s["date"] != "unknown" else None,
                s["timestamp"], s["first_prompt"], s["model"],
                s["query_count"], s["input_tokens"], s["output_tokens"],
                s["cache_creation_tokens"], s["cache_read_tokens"],
                s["total_tokens"],
            ],
        )

    for i, q in enumerate(queries):
        ts = q.get("timestamp") or ""
        date = ts[:10] if ts else None
        con.execute(
            """INSERT INTO queries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                i, q["session_id"], q["project"], date,
                q["timestamp"], q["user_prompt"], q["model"],
                q["input_tokens"], q["output_tokens"],
                q["cache_creation_tokens"], q["cache_read_tokens"],
                q["total_tokens"], json.dumps(q["tools"]),
            ],
        )

    for d in daily:
        con.execute(
            """INSERT INTO daily_usage VALUES (?,?,?,?,?,?)""",
            [
                d["date"], d["input_tokens"], d["output_tokens"],
                d["total_tokens"], d["session_count"], d["query_count"],
            ],
        )

    for i, p in enumerate(top_prompts):
        con.execute(
            """INSERT INTO top_prompts VALUES (?,?,?,?,?,?,?)""",
            [
                i, p["project"], p["user_prompt"],
                p["total_tokens"], p["input_tokens"], p["output_tokens"],
                p["query_count"],
            ],
        )


def load_demo_data(con: duckdb.DuckDBPyConnection) -> None:
    """
    Populate all tables with 30 days of realistic fake data for 3 fake projects.
    """
    con.execute("DELETE FROM sessions")
    con.execute("DELETE FROM queries")
    con.execute("DELETE FROM daily_usage")
    con.execute("DELETE FROM top_prompts")

    rng = random.Random(42)
    projects = ["my-app", "api-server", "scripts"]
    models = ["claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5"]
    model_weights = [0.6, 0.3, 0.1]

    now = datetime.now()
    sessions = []
    queries = []

    for day_offset in range(30):
        day = now - timedelta(days=29 - day_offset)
        n_sessions = rng.randint(1, 5)
        for _ in range(n_sessions):
            project = rng.choices(projects, weights=[0.5, 0.3, 0.2])[0]
            model = rng.choices(models, weights=model_weights)[0]
            session_id = f"demo-{day.strftime('%Y%m%d')}-{rng.randint(1000,9999)}"
            n_queries = rng.randint(3, 40)

            sample_prompts = [
                "Implement the authentication flow",
                "Fix the failing tests in the CI pipeline",
                "Refactor the database connection pooling",
                "Add error handling to the API endpoints",
                "Review and improve the logging strategy",
                "Write unit tests for the parser module",
                "Optimize the SQL queries for performance",
                "Add TypeScript types to the frontend",
                "Set up deployment pipeline",
                "Debug the memory leak in the worker",
            ]
            first_prompt = rng.choice(sample_prompts)

            session_input = 0
            session_output = 0
            session_cache_write = 0
            session_cache_read = 0

            session_queries = []
            for qi in range(n_queries):
                inp = rng.randint(2000, 20000) + qi * rng.randint(500, 2000)
                out = rng.randint(200, 3000)
                cw = rng.randint(0, 2000) if rng.random() < 0.3 else 0
                cr = rng.randint(0, 5000) if rng.random() < 0.4 else 0
                total = inp + out
                ts_offset = timedelta(hours=rng.uniform(0, 8), minutes=rng.uniform(0, 60))
                ts = day.replace(hour=9, minute=0, second=0, microsecond=0) + ts_offset

                session_queries.append({
                    "session_id": session_id,
                    "project": project,
                    "timestamp": ts.isoformat(),
                    "user_prompt": first_prompt if qi == 0 else (rng.choice(sample_prompts) if rng.random() < 0.2 else None),
                    "model": model,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_creation_tokens": cw,
                    "cache_read_tokens": cr,
                    "total_tokens": total,
                    "tools": rng.sample(["bash", "read", "write", "edit", "glob", "grep"], rng.randint(0, 3)),
                })
                session_input += inp
                session_output += out
                session_cache_write += cw
                session_cache_read += cr

            queries.extend(session_queries)
            session_ts = day.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()

            sessions.append({
                "session_id": session_id,
                "project": project,
                "date": day.strftime("%Y-%m-%d"),
                "timestamp": session_ts,
                "first_prompt": first_prompt,
                "model": model,
                "query_count": n_queries,
                "input_tokens": session_input,
                "output_tokens": session_output,
                "cache_creation_tokens": session_cache_write,
                "cache_read_tokens": session_cache_read,
                "total_tokens": session_input + session_output,
            })

    daily = build_daily_usage(queries)
    top_prompts = build_top_prompts(queries, n=20)
    load_real_data(con, sessions, queries, daily, top_prompts)


def refresh_db() -> dict:
    """
    Parse real logs; fall back to demo data if none found.
    Returns {status, sessions_loaded, using_demo}.
    """
    db_path = get_db_path()
    con = duckdb.connect(db_path)
    try:
        init_schema(con)
        sessions, queries = parse_all_sessions()

        if sessions:
            daily = build_daily_usage(queries)
            top_prompts = build_top_prompts(queries, n=20)
            load_real_data(con, sessions, queries, daily, top_prompts)
            return {"status": "ok", "sessions_loaded": len(sessions), "using_demo": False}
        else:
            load_demo_data(con)
            session_count = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            return {"status": "ok", "sessions_loaded": session_count, "using_demo": True}
    finally:
        con.close()
