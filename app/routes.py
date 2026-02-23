"""
API routes for DevBuddy Phase 2.
"""
from datetime import datetime, date as _date, timedelta as _timedelta
from pathlib import Path
from typing import Optional
import glob
import os
import time

import duckdb
from fastapi import APIRouter, Query

from .db import get_db_path, init_schema, refresh_db
from .insights import generate_insights

router = APIRouter()

_last_check_mtime: float = 0.0

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _open_db() -> duckdb.DuckDBPyConnection:
    path = get_db_path()
    con = duckdb.connect(path)
    init_schema(con)
    return con


def _ensure_data(con: duckdb.DuckDBPyConnection) -> None:
    """Load demo data if all tables are empty."""
    count = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if count == 0:
        from .db import load_demo_data
        load_demo_data(con)


def _date_filter(
    from_date: Optional[str],
    to_date: Optional[str],
    date_col: str = "date",
) -> tuple[str, list]:
    clauses, params = [], []
    if from_date:
        clauses.append(f"{date_col} >= ?")
        params.append(from_date)
    if to_date:
        clauses.append(f"{date_col} <= ?")
        params.append(to_date)
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def _session_filter(
    from_date: Optional[str],
    to_date: Optional[str],
    project: Optional[str],
    model: Optional[str],
    date_col: str = "date",
) -> tuple[str, list]:
    clauses, params = [], []
    if from_date:
        clauses.append(f"{date_col} >= ?")
        params.append(from_date)
    if to_date:
        clauses.append(f"{date_col} <= ?")
        params.append(to_date)
    if project:
        clauses.append("project = ?")
        params.append(project)
    if model:
        clauses.append("model = ?")
        params.append(model)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/overview")
def get_overview(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)
        where, params = _session_filter(from_date, to_date, project, model)
        row = con.execute(
            f"""
            SELECT
                COUNT(*) AS sessions,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                MIN(date) AS first_date,
                MAX(date) AS last_date,
                COALESCE(SUM(query_count), 0) AS total_queries
            FROM sessions{where}
            """,
            params,
        ).fetchone()

        # Active hours: count distinct hours across session timestamps
        ts_rows = con.execute(
            f"SELECT timestamp FROM sessions{where}", params
        ).fetchall()
        active_hours = len({
            r[0].strftime("%Y-%m-%d %H") if hasattr(r[0], "strftime") else str(r[0])[:13]
            for r in ts_rows
            if r[0]
        })

        return {
            "sessions": row[0],
            "total_tokens": row[1],
            "active_hours": active_hours,
            "total_queries": row[4],
            "date_range": {"from": str(row[2]) if row[2] else None, "to": str(row[3]) if row[3] else None},
        }
    finally:
        con.close()


@router.get("/api/daily")
def get_daily(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)

        if project or model:
            # Re-aggregate from sessions table with filters
            where, params = _session_filter(from_date, to_date, project, model)
            rows = con.execute(
                f"""
                SELECT
                    date,
                    SUM(input_tokens),
                    SUM(output_tokens),
                    SUM(total_tokens),
                    COUNT(*),
                    SUM(query_count)
                FROM sessions{where}
                GROUP BY date
                ORDER BY date
                """,
                params,
            ).fetchall()
        else:
            df_where, params = _date_filter(from_date, to_date)
            rows = con.execute(
                f"""
                SELECT date, input_tokens, output_tokens, total_tokens,
                       session_count, query_count
                FROM daily_usage{df_where}
                ORDER BY date
                """,
                params,
            ).fetchall()

        return {
            "labels": [str(r[0]) for r in rows],
            "tokens": [r[3] for r in rows],
            "values": [r[3] for r in rows],  # backwards compat alias
        }
    finally:
        con.close()


@router.get("/api/projects")
def get_projects(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)
        clauses, params = [], []
        if from_date:
            clauses.append("date >= ?")
            params.append(from_date)
        if to_date:
            clauses.append("date <= ?")
            params.append(to_date)
        if model:
            clauses.append("model = ?")
            params.append(model)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        total_row = con.execute(
            f"SELECT COALESCE(SUM(total_tokens), 1) FROM sessions{where}", params
        ).fetchone()
        grand_total = total_row[0] or 1

        rows = con.execute(
            f"""
            SELECT
                project,
                SUM(total_tokens) AS total_tokens,
                COUNT(*) AS session_count
            FROM sessions{where}
            GROUP BY project
            ORDER BY total_tokens DESC
            """,
            params,
        ).fetchall()

        return [
            {
                "project": r[0],
                "total_tokens": r[1],
                "session_count": r[2],
                "pct": round(r[1] / grand_total * 100, 1),
            }
            for r in rows
        ]
    finally:
        con.close()


@router.get("/api/top-prompts")
def get_top_prompts(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)
        # If no filters just read from top_prompts table
        if not any([from_date, to_date, project, model]):
            rows = con.execute(
                "SELECT user_prompt, total_tokens, query_count, project FROM top_prompts ORDER BY total_tokens DESC LIMIT 20"
            ).fetchall()
            return [
                {
                    "user_prompt": r[0],
                    "total_tokens": r[1],
                    "query_count": r[2],
                    "project": r[3],
                }
                for r in rows
            ]

        # Filtered: re-aggregate from queries
        clauses = ["user_prompt IS NOT NULL"]
        params = []
        if from_date:
            clauses.append("date >= ?")
            params.append(from_date)
        if to_date:
            clauses.append("date <= ?")
            params.append(to_date)
        if project:
            clauses.append("project = ?")
            params.append(project)
        if model:
            clauses.append("model = ?")
            params.append(model)
        where = " WHERE " + " AND ".join(clauses)

        rows = con.execute(
            f"""
            SELECT user_prompt, SUM(total_tokens), COUNT(*), project
            FROM queries{where}
            GROUP BY user_prompt, project
            ORDER BY SUM(total_tokens) DESC
            LIMIT 20
            """,
            params,
        ).fetchall()
        return [
            {
                "user_prompt": r[0],
                "total_tokens": r[1],
                "query_count": r[2],
                "project": r[3],
            }
            for r in rows
        ]
    finally:
        con.close()


@router.get("/api/sessions")
def get_sessions(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)
        where, params = _session_filter(from_date, to_date, project, model)
        rows = con.execute(
            f"""
            SELECT session_id, project, date, model, query_count,
                   total_tokens, first_prompt
            FROM sessions{where}
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            params,
        ).fetchall()
        return [
            {
                "session_id": r[0],
                "project": r[1],
                "date": str(r[2]),
                "model": r[3],
                "query_count": r[4],
                "total_tokens": r[5],
                "first_prompt": r[6],
            }
            for r in rows
        ]
    finally:
        con.close()


@router.get("/api/insights")
def get_insights(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)
        where, params = _session_filter(from_date, to_date, project, model)
        session_rows = con.execute(
            f"""
            SELECT session_id, project, date, timestamp, first_prompt, model,
                   query_count, input_tokens, output_tokens, cache_creation_tokens,
                   cache_read_tokens, total_tokens
            FROM sessions{where}
            """,
            params,
        ).fetchall()
        sessions = [
            {
                "session_id": r[0], "project": r[1], "date": str(r[2]),
                "timestamp": str(r[3]) if r[3] else None,
                "first_prompt": r[4], "model": r[5],
                "query_count": r[6], "input_tokens": r[7], "output_tokens": r[8],
                "cache_creation_tokens": r[9], "cache_read_tokens": r[10],
                "total_tokens": r[11],
            }
            for r in session_rows
        ]

        # Fetch queries for the same filter
        q_clauses, q_params = [], []
        if from_date:
            q_clauses.append("date >= ?")
            q_params.append(from_date)
        if to_date:
            q_clauses.append("date <= ?")
            q_params.append(to_date)
        if project:
            q_clauses.append("project = ?")
            q_params.append(project)
        if model:
            q_clauses.append("model = ?")
            q_params.append(model)
        q_where = (" WHERE " + " AND ".join(q_clauses)) if q_clauses else ""

        query_rows = con.execute(
            f"""
            SELECT session_id, project, date, timestamp, user_prompt, model,
                   input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                   total_tokens, tools
            FROM queries{q_where}
            """,
            q_params,
        ).fetchall()
        import json
        queries = [
            {
                "session_id": r[0], "project": r[1], "date": str(r[2]),
                "timestamp": str(r[3]) if r[3] else None,
                "user_prompt": r[4], "model": r[5],
                "input_tokens": r[6], "output_tokens": r[7],
                "cache_creation_tokens": r[8], "cache_read_tokens": r[9],
                "total_tokens": r[10],
                "tools": json.loads(r[11]) if r[11] else [],
            }
            for r in query_rows
        ]

        return generate_insights(sessions, queries)
    finally:
        con.close()


@router.get("/api/filters")
def get_filters():
    con = _open_db()
    try:
        _ensure_data(con)
        projects = [r[0] for r in con.execute("SELECT DISTINCT project FROM sessions ORDER BY project").fetchall()]
        models = [r[0] for r in con.execute("SELECT DISTINCT model FROM sessions ORDER BY model").fetchall()]
        return {"projects": projects, "models": models}
    finally:
        con.close()


@router.get("/api/refresh")
def api_refresh():
    global _last_check_mtime
    _last_check_mtime = 0.0
    result = refresh_db()
    return result


@router.get("/api/has-changes")
def api_has_changes():
    global _last_check_mtime
    prev = _last_check_mtime
    _last_check_mtime = time.time()
    changed = False
    home = Path.home()
    for pattern in [
        str(home / ".claude" / "projects" / "**" / "*.jsonl"),
        str(home / ".claude" / "history.jsonl"),
    ]:
        for fpath in glob.glob(pattern, recursive=True):
            try:
                if os.path.getmtime(fpath) > prev:
                    changed = True
                    break
            except OSError:
                pass
        if changed:
            break
    return {"changed": changed}


@router.get("/api/heatmap")
def get_heatmap(metric: str = Query("tokens")):
    con = _open_db()
    try:
        _ensure_data(con)
        today = _date.today()
        start = today - _timedelta(days=364)

        if metric == "prompts":
            rows = con.execute(
                "SELECT date, SUM(query_count) FROM sessions WHERE date >= ? GROUP BY date",
                [start.isoformat()],
            ).fetchall()
        elif metric == "hours":
            rows = con.execute(
                "SELECT date, COUNT(DISTINCT EXTRACT(HOUR FROM timestamp)) FROM sessions WHERE date >= ? GROUP BY date",
                [start.isoformat()],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT date, SUM(total_tokens) FROM sessions WHERE date >= ? GROUP BY date",
                [start.isoformat()],
            ).fetchall()

        value_map = {}
        for r in rows:
            d = r[0]
            key = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
            value_map[key] = int(r[1] or 0)

        result = []
        for i in range(365):
            d = start + _timedelta(days=i)
            d_str = d.isoformat()
            result.append({
                "date": d_str,
                "value": value_map.get(d_str, 0),
                "week": i // 7,
                "day": d.weekday(),
            })
        return result
    finally:
        con.close()


@router.get("/api/model-stats")
def get_model_stats(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    con = _open_db()
    try:
        _ensure_data(con)
        where, params = _session_filter(from_date, to_date, project, model)
        rows = con.execute(
            f"""
            SELECT model,
                COUNT(*) AS session_count,
                SUM(total_tokens) AS total_tokens,
                AVG(total_tokens) AS avg_tokens_per_session,
                AVG(query_count) AS avg_queries_per_session
            FROM sessions{where}
            GROUP BY model
            ORDER BY total_tokens DESC
            """,
            params,
        ).fetchall()
        return [
            {
                "model": r[0],
                "session_count": r[1],
                "total_tokens": r[2],
                "avg_tokens_per_session": round(r[3]) if r[3] else 0,
                "avg_queries_per_session": round(r[4], 1) if r[4] else 0.0,
            }
            for r in rows
        ]
    finally:
        con.close()


# Backwards-compat alias
@router.get("/api/stats")
def get_stats(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
):
    return get_daily(from_date=from_date, to_date=to_date)
