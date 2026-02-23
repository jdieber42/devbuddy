"""
Parse Claude Code session JSONL logs from ~/.claude/projects/.
Python equivalent of features/prototype/src/parser.js.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

def _claude_dir():
    return Path.home() / ".claude"


def parse_content(content):
    """Return plain text from a content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if b.get("type") == "text"]
        return "\n".join(parts).strip()
    return ""


def parse_session_file(path: Path, project_name: str) -> list[dict]:
    """
    Parse a single JSONL session file.
    Returns a list of query dicts (one per assistant turn).
    """
    entries = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []

    session_id = path.stem
    queries = []
    pending_user = None  # {text, timestamp}

    for entry in entries:
        etype = entry.get("type")

        # --- User turn ---
        if etype == "user":
            msg = entry.get("message", {})
            if msg.get("role") != "user":
                continue
            if entry.get("isMeta"):
                continue
            content = msg.get("content", "")
            text = parse_content(content)
            if text.startswith("<local-command") or text.startswith("<command-name"):
                continue
            pending_user = {
                "text": text or None,
                "timestamp": entry.get("timestamp"),
            }

        # --- Assistant turn ---
        elif etype == "assistant":
            msg = entry.get("message", {})
            usage = msg.get("usage")
            if not usage:
                continue
            model = msg.get("model", "unknown")
            if model == "<synthetic>":
                continue

            input_tok = (
                (usage.get("input_tokens") or 0)
                + (usage.get("cache_creation_input_tokens") or 0)
                + (usage.get("cache_read_input_tokens") or 0)
            )
            output_tok = usage.get("output_tokens") or 0
            cache_write = usage.get("cache_creation_input_tokens") or 0
            cache_read = usage.get("cache_read_input_tokens") or 0

            tools = []
            content_blocks = msg.get("content")
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    if block.get("type") == "tool_use" and block.get("name"):
                        tools.append(block["name"])

            timestamp = entry.get("timestamp") or (
                pending_user["timestamp"] if pending_user else None
            )

            queries.append({
                "session_id": session_id,
                "project": project_name,
                "timestamp": timestamp,
                "user_prompt": pending_user["text"] if pending_user else None,
                "model": model,
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cache_creation_tokens": cache_write,
                "cache_read_tokens": cache_read,
                "total_tokens": input_tok + output_tok,
                "tools": tools,
            })

    return queries


def parse_all_sessions() -> tuple[list[dict], list[dict]]:
    """
    Walk ~/.claude/projects/**/*.jsonl and parse all sessions.
    Returns (sessions_list, queries_list).
    """
    projects_dir = _claude_dir() / "projects"
    if not projects_dir.exists():
        return [], []

    # History file for first-prompt display names
    history_path = _claude_dir() / "history.jsonl"
    session_first_prompt: dict[str, str] = {}
    if history_path.exists():
        try:
            with open(history_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sid = entry.get("sessionId")
                    display = (entry.get("display") or "").strip()
                    if sid and display and sid not in session_first_prompt:
                        if display.startswith("/") and len(display) < 30:
                            continue
                        session_first_prompt[sid] = display
        except OSError:
            pass

    all_queries: list[dict] = []
    sessions: list[dict] = []

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name

        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            queries = parse_session_file(jsonl_file, project_name)
            if not queries:
                continue

            session_id = jsonl_file.stem

            # Dominant model
            model_counts: dict[str, int] = {}
            for q in queries:
                m = q["model"]
                model_counts[m] = model_counts.get(m, 0) + 1
            primary_model = max(model_counts, key=lambda k: model_counts[k])

            # Aggregate tokens
            input_tokens = sum(q["input_tokens"] for q in queries)
            output_tokens = sum(q["output_tokens"] for q in queries)
            cache_creation = sum(q["cache_creation_tokens"] for q in queries)
            cache_read = sum(q["cache_read_tokens"] for q in queries)
            total_tokens = sum(q["total_tokens"] for q in queries)

            # Timestamps
            first_ts = next((q["timestamp"] for q in queries if q["timestamp"]), None)
            date_str = first_ts[:10] if first_ts else "unknown"

            first_prompt = (
                session_first_prompt.get(session_id)
                or next((q["user_prompt"] for q in queries if q["user_prompt"]), None)
                or "(no prompt)"
            )

            sessions.append({
                "session_id": session_id,
                "project": project_name,
                "date": date_str,
                "timestamp": first_ts,
                "first_prompt": first_prompt[:200],
                "model": primary_model,
                "query_count": len(queries),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_tokens": cache_creation,
                "cache_read_tokens": cache_read,
                "total_tokens": total_tokens,
            })

            all_queries.extend(queries)

    return sessions, all_queries


def build_daily_usage(queries: list[dict]) -> list[dict]:
    """Aggregate queries by date."""
    daily: dict[str, dict] = {}
    for q in queries:
        ts = q.get("timestamp") or ""
        date = ts[:10] if ts else "unknown"
        if date == "unknown":
            continue
        if date not in daily:
            daily[date] = {
                "date": date,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "session_count": 0,
                "query_count": 0,
                "_sessions": set(),
            }
        d = daily[date]
        d["input_tokens"] += q["input_tokens"]
        d["output_tokens"] += q["output_tokens"]
        d["total_tokens"] += q["total_tokens"]
        d["query_count"] += 1
        d["_sessions"].add(q["session_id"])

    result = []
    for d in sorted(daily.values(), key=lambda x: x["date"]):
        d["session_count"] = len(d.pop("_sessions"))
        result.append(d)
    return result


def build_project_breakdown(sessions: list[dict]) -> list[dict]:
    """Aggregate sessions by project."""
    projects: dict[str, dict] = {}
    total_tokens = sum(s["total_tokens"] for s in sessions)
    for s in sessions:
        p = s["project"]
        if p not in projects:
            projects[p] = {
                "project": p,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "session_count": 0,
            }
        projects[p]["total_tokens"] += s["total_tokens"]
        projects[p]["input_tokens"] += s["input_tokens"]
        projects[p]["output_tokens"] += s["output_tokens"]
        projects[p]["session_count"] += 1

    result = sorted(projects.values(), key=lambda x: x["total_tokens"], reverse=True)
    for p in result:
        p["pct"] = round(p["total_tokens"] / max(total_tokens, 1) * 100, 1)
    return result


def build_top_prompts(queries: list[dict], n: int = 20) -> list[dict]:
    """
    Group consecutive queries under the same user prompt, accumulate tokens,
    return top-n by total tokens.
    """
    # Group by session first, then by prompt runs within session
    sessions_map: dict[str, list[dict]] = {}
    for q in queries:
        sid = q["session_id"]
        sessions_map.setdefault(sid, []).append(q)

    prompt_groups: list[dict] = []

    for sid, qs in sessions_map.items():
        project = qs[0]["project"] if qs else ""
        # Each "run" = [prompt_text, input, output, count]
        runs: list[tuple] = []  # (prompt, input, output, count)
        cur: list = [None, 0, 0, 0]  # [prompt, input, output, count]

        for q in qs:
            up = q.get("user_prompt")
            if up and up != cur[0]:
                if cur[0] and (cur[1] + cur[2]) > 0:
                    runs.append(tuple(cur))
                cur = [up, 0, 0, 0]
            cur[1] += q["input_tokens"]
            cur[2] += q["output_tokens"]
            cur[3] += 1

        if cur[0] and (cur[1] + cur[2]) > 0:
            runs.append(tuple(cur))

        for prompt, inp, out, count in runs:
            prompt_groups.append({
                "project": project,
                "user_prompt": prompt[:300],
                "total_tokens": inp + out,
                "input_tokens": inp,
                "output_tokens": out,
                "query_count": count,
            })

    prompt_groups.sort(key=lambda x: x["total_tokens"], reverse=True)
    return prompt_groups[:n]
