from fastapi import APIRouter
import duckdb
import os
from datetime import datetime, timedelta
import random

router = APIRouter()

DB_PATH = "data/devbuddy.duckdb"

def init_db():
    os.makedirs("data", exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            timestamp TIMESTAMP,
            tokens INTEGER
        )
    """)
    
    # insert demo data if empty
    count = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if count == 0:
        now = datetime.now()
        for i in range(30):
            con.execute(
                "INSERT INTO sessions VALUES (?, ?)",
                [now - timedelta(days=i), random.randint(1000, 5000)]
            )
    con.close()

@router.get("/api/stats")
def get_stats():
    init_db()
    con = duckdb.connect(DB_PATH)
    
    rows = con.execute("""
        SELECT 
            DATE(timestamp) as day,
            SUM(tokens) as tokens
        FROM sessions
        GROUP BY day
        ORDER BY day
    """).fetchall()
    
    con.close()
    
    return {
        "labels": [str(r[0]) for r in rows],
        "values": [r[1] for r in rows]
    }
