"""
Generates usage insights from sessions and queries.
Python translation of parser.js generateInsights().
"""
import importlib.util
from pathlib import Path


def _fmt(n: int | float) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.0f}K"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def load_plugins(sessions: list[dict], queries: list[dict]) -> list[dict]:
    """Load plugins from plugins/ directory and gather their insights."""
    plugins_dir = Path(__file__).parent.parent / "plugins"
    extra: list[dict] = []
    if not plugins_dir.exists():
        return extra
    for plugin_path in sorted(plugins_dir.glob("*.py")):
        if plugin_path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"devbuddy_plugin_{plugin_path.stem}", plugin_path
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "generate_insights"):
                result = module.generate_insights(sessions, queries)
                if isinstance(result, list):
                    extra.extend(result)
        except Exception:
            pass  # Never crash on plugin errors
    return extra


def generate_insights(sessions: list[dict], queries: list[dict]) -> list[dict]:
    """
    Generate up to 10 insights from sessions and queries.
    Both lists use the dict schemas from db.py/parser.py.
    """
    insights: list[dict] = []

    total_tokens = sum(s["total_tokens"] for s in sessions)
    total_output = sum(s["output_tokens"] for s in sessions)

    # Build top prompts list from queries for insights 1 and 6
    # (reuse the same grouping logic inline for simplicity)
    prompt_groups: list[dict] = _build_prompt_groups(queries)

    # 1. Short, vague messages that cost a lot
    short_expensive = [
        p for p in prompt_groups
        if len(p["user_prompt"].strip()) < 30 and p["total_tokens"] > 100_000
    ]
    if short_expensive:
        total_wasted = sum(p["total_tokens"] for p in short_expensive)
        examples = list(dict.fromkeys(p["user_prompt"].strip() for p in short_expensive))[:4]
        ex_str = ", ".join(f'"{e}"' for e in examples)
        insights.append({
            "id": "vague-prompts",
            "type": "warning",
            "title": "Short, vague messages are costing you the most",
            "description": (
                f"{len(short_expensive)} times you sent a short message like {ex_str} — "
                f"and each time, Claude used over 100K tokens to respond. That adds up to "
                f"{_fmt(total_wasted)} tokens total. When you say just \"Yes\" or \"Do it\", "
                f"Claude doesn't know exactly what you want, so it tries harder — reading more "
                f"files, running more tools, making more attempts. Each of those steps re-sends "
                f"the entire conversation, which multiplies the cost."
            ),
            "action": (
                "Try being specific. Instead of \"Yes\", say \"Yes, update the login page and "
                "run the tests.\" It gives Claude a clear target, so it finishes faster and "
                "uses fewer tokens."
            ),
        })

    # 2. Context growth — sessions where token cost grows 2x from start to end
    # queries grouped by session
    session_queries: dict[str, list[dict]] = {}
    for q in queries:
        session_queries.setdefault(q["session_id"], []).append(q)

    long_session_ids = {s["session_id"] for s in sessions if s["query_count"] > 50}
    growth_data = []
    for sid in long_session_ids:
        qs = session_queries.get(sid, [])
        if len(qs) < 10:
            continue
        first5_avg = sum(q["total_tokens"] for q in qs[:5]) / 5
        last5_avg = sum(q["total_tokens"] for q in qs[-5:]) / 5
        ratio = last5_avg / max(first5_avg, 1)
        if ratio > 2:
            sess = next((s for s in sessions if s["session_id"] == sid), None)
            growth_data.append({"session": sess, "ratio": ratio})

    if growth_data:
        avg_growth = sum(g["ratio"] for g in growth_data) / len(growth_data)
        worst = max(growth_data, key=lambda g: g["ratio"])
        worst_prompt = (worst["session"]["first_prompt"][:50] + "...") if worst["session"] else "..."
        insights.append({
            "id": "context-growth",
            "type": "warning",
            "title": "The longer you chat, the more each message costs",
            "description": (
                f"In {len(growth_data)} of your conversations, the messages near the end cost "
                f"{avg_growth:.1f}x more than the ones at the start. Why? Every time you send a "
                f"message, Claude re-reads the entire conversation from the beginning. So message "
                f"#5 is cheap, but message #80 is expensive because Claude is re-reading 79 "
                f"previous messages plus all the code it wrote. Your worst conversation "
                f"(\"{worst_prompt}\") grew {worst['ratio']:.1f}x more expensive by the end."
            ),
            "action": (
                "Start a fresh conversation when you move to a new task. If you need context "
                "from before, paste a short summary in your first message."
            ),
        })

    # 3. Marathon sessions
    marathon = [s for s in sessions if s["query_count"] > 200]
    all_turns = sorted(s["query_count"] for s in sessions)
    median_turns = all_turns[len(all_turns) // 2] if all_turns else 0
    if len(marathon) >= 3:
        marathon_tokens = sum(s["total_tokens"] for s in marathon)
        pct = int(marathon_tokens / max(total_tokens, 1) * 100)
        insights.append({
            "id": "marathon-sessions",
            "type": "info",
            "title": f"Just {len(marathon)} long conversations used {pct}% of all your tokens",
            "description": (
                f"You have {len(marathon)} conversations with over 200 messages each. These alone "
                f"consumed {_fmt(marathon_tokens)} tokens — that's {pct}% of everything. Meanwhile, "
                f"your typical conversation is about {median_turns} messages. Long conversations "
                f"aren't always bad, but they're disproportionately expensive because of how "
                f"context builds up."
            ),
            "action": (
                "Try keeping one conversation per task. When a conversation starts drifting into "
                "different topics, that is a good time to start a new one."
            ),
        })

    # 4. Input-heavy — output < 2% of total
    if total_tokens > 0:
        output_pct = total_output / total_tokens * 100
        if output_pct < 2:
            insights.append({
                "id": "input-heavy",
                "type": "info",
                "title": f"{output_pct:.1f}% of your tokens are Claude actually writing",
                "description": (
                    f"Out of {_fmt(total_tokens)} total tokens, only {_fmt(total_output)} are "
                    f"from Claude writing responses. The other {100 - output_pct:.1f}% is Claude "
                    f"re-reading your conversation history, files, and context before each response. "
                    f"The biggest factor in token usage isn't how much Claude writes — it's how "
                    f"long your conversations are."
                ),
                "action": (
                    "Keeping conversations shorter has more impact than asking for shorter answers."
                ),
            })

    # 5. Day-of-week pattern
    if len(sessions) >= 10:
        day_map: dict[int, dict] = {}
        for s in sessions:
            ts = s.get("timestamp")
            if not ts:
                continue
            try:
                from datetime import datetime as _dt
                d = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                dow = d.weekday()  # 0=Mon … 6=Sun
            except Exception:
                continue
            if dow not in day_map:
                day_map[dow] = {"tokens": 0, "sessions": 0}
            day_map[dow]["tokens"] += s["total_tokens"]
            day_map[dow]["sessions"] += 1

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        days = [
            {"day": day_names[d], "avg": v["tokens"] / v["sessions"], **v}
            for d, v in day_map.items()
        ]
        if len(days) >= 3:
            days.sort(key=lambda x: x["avg"], reverse=True)
            busiest = days[0]
            quietest = days[-1]
            insights.append({
                "id": "day-pattern",
                "type": "neutral",
                "title": f"You use Claude the most on {busiest['day']}s",
                "description": (
                    f"Your {busiest['day']} conversations average "
                    f"{_fmt(busiest['avg'])} tokens each, compared to "
                    f"{_fmt(quietest['avg'])} on {quietest['day']}s."
                ),
                "action": None,
            })

    # 6. Model mismatch — Opus used for simple sessions
    opus_sessions = [s for s in sessions if "opus" in s.get("model", "")]
    if opus_sessions:
        simple_opus = [s for s in opus_sessions if s["query_count"] < 10 and s["total_tokens"] < 200_000]
        if len(simple_opus) >= 3:
            wasted = sum(s["total_tokens"] for s in simple_opus)
            examples = ", ".join(
                f'"{s["first_prompt"][:40]}"' for s in simple_opus[:3]
            )
            insights.append({
                "id": "model-mismatch",
                "type": "warning",
                "title": f"{len(simple_opus)} simple conversations used Opus unnecessarily",
                "description": (
                    f"These conversations had fewer than 10 messages and used {_fmt(wasted)} "
                    f"tokens on Opus: {examples}. Opus is the most capable model but also the "
                    f"most expensive. For quick questions and small tasks, Sonnet or Haiku would "
                    f"give similar results at a fraction of the cost."
                ),
                "action": "Use /model to switch to Sonnet or Haiku for simple tasks.",
            })

    # 7. Tool-heavy conversations
    if len(sessions) >= 5:
        tool_heavy = []
        for s in sessions:
            qs = session_queries.get(s["session_id"], [])
            user_msgs = sum(1 for q in qs if q.get("user_prompt"))
            tool_calls = s["query_count"] - user_msgs
            if user_msgs > 0 and tool_calls > user_msgs * 3:
                tool_heavy.append({"session": s, "ratio": tool_calls / user_msgs})
        if len(tool_heavy) >= 3:
            total_tool_tokens = sum(g["session"]["total_tokens"] for g in tool_heavy)
            avg_ratio = sum(g["ratio"] for g in tool_heavy) / len(tool_heavy)
            insights.append({
                "id": "tool-heavy",
                "type": "info",
                "title": f"{len(tool_heavy)} conversations had {avg_ratio:.0f}x more tool calls than messages",
                "description": (
                    f"In these conversations, Claude made ~{avg_ratio:.0f} tool calls for every "
                    f"message you sent. Each tool call (reading files, running commands, searching "
                    f"code) is a full round trip that re-reads the entire conversation. These "
                    f"{len(tool_heavy)} conversations used {_fmt(total_tool_tokens)} tokens total."
                ),
                "action": (
                    "Point Claude to specific files and line numbers when you can. "
                    "\"Fix the bug in src/auth.js line 42\" triggers fewer tool calls than "
                    "\"fix the login bug\" where Claude has to search for the right file first."
                ),
            })

    # 8. Project dominance — top project ≥ 60%
    if len(sessions) >= 5:
        proj_tokens: dict[str, int] = {}
        for s in sessions:
            p = s.get("project") or "unknown"
            proj_tokens[p] = proj_tokens.get(p, 0) + s["total_tokens"]
        sorted_proj = sorted(proj_tokens.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_proj) >= 2:
            top_proj, top_tok = sorted_proj[0]
            pct = int(top_tok / max(total_tokens, 1) * 100)
            if pct >= 60:
                proj_display = top_proj.replace("C--Users-", "").replace("-", "/")[:40]
                insights.append({
                    "id": "project-dominance",
                    "type": "info",
                    "title": f"{pct}% of your tokens went to one project: {proj_display}",
                    "description": (
                        f"Your \"{proj_display}\" project used {_fmt(top_tok)} tokens out of "
                        f"{_fmt(total_tokens)} total. That is {pct}% of all your usage. "
                        f"The next closest project used {_fmt(sorted_proj[1][1])} tokens."
                    ),
                    "action": (
                        "Not necessarily a problem, but if this project has long-running "
                        "conversations, breaking them into smaller sessions could reduce its footprint."
                    ),
                })

    # 9. Conversation efficiency — cost per message in short vs long sessions
    if len(sessions) >= 10:
        short_sessions = [s for s in sessions if 3 <= s["query_count"] <= 15]
        long_sessions_2 = [s for s in sessions if s["query_count"] > 80]
        if len(short_sessions) >= 3 and len(long_sessions_2) >= 2:
            short_avg = sum(s["total_tokens"] / s["query_count"] for s in short_sessions) / len(short_sessions)
            long_avg = sum(s["total_tokens"] / s["query_count"] for s in long_sessions_2) / len(long_sessions_2)
            ratio = long_avg / max(short_avg, 1)
            if ratio >= 2:
                insights.append({
                    "id": "conversation-efficiency",
                    "type": "warning",
                    "title": f"Each message costs {ratio:.1f}x more in long conversations",
                    "description": (
                        f"In your short conversations (under 15 messages), each message costs "
                        f"~{_fmt(short_avg)} tokens. In your long ones (80+ messages), each "
                        f"message costs ~{_fmt(long_avg)} tokens. That is {ratio:.1f}x more per "
                        f"message, because Claude re-reads the entire history every turn."
                    ),
                    "action": (
                        "Start fresh conversations more often. A 5-conversation workflow costs "
                        "far less than one 500-message marathon."
                    ),
                })

    # 10. Heavy context — first message > 50K tokens
    if len(sessions) >= 5:
        heavy_starts = [
            s for s in sessions
            if session_queries.get(s["session_id"]) and
            session_queries[s["session_id"]][0]["input_tokens"] > 50_000
        ]
        if len(heavy_starts) >= 5:
            avg_start = sum(
                session_queries[s["session_id"]][0]["input_tokens"] for s in heavy_starts
            ) / len(heavy_starts)
            total_overhead = sum(
                session_queries[s["session_id"]][0]["input_tokens"] for s in heavy_starts
            )
            insights.append({
                "id": "heavy-context",
                "type": "info",
                "title": f"{len(heavy_starts)} conversations started with {_fmt(avg_start)}+ tokens of context",
                "description": (
                    f"Before you type your first message, Claude reads your CLAUDE.md, project "
                    f"files, and system context. In {len(heavy_starts)} conversations, this "
                    f"starting context averaged {_fmt(avg_start)} tokens. Across all of them, "
                    f"that is {_fmt(total_overhead)} tokens just on setup — and this context "
                    f"gets re-read with every message."
                ),
                "action": (
                    "Keep your CLAUDE.md files concise. Remove sections you rarely need. "
                    "A smaller starting context compounds into savings across every message."
                ),
            })

    insights.extend(load_plugins(sessions, queries))
    return insights


def _build_prompt_groups(queries: list[dict]) -> list[dict]:
    """Build prompt groups from queries for insight analysis."""
    sessions_map: dict[str, list[dict]] = {}
    for q in queries:
        sessions_map.setdefault(q["session_id"], []).append(q)

    groups: list[dict] = []
    for sid, qs in sessions_map.items():
        cur: list = [None, 0, 0]
        for q in qs:
            up = q.get("user_prompt")
            if up and up != cur[0]:
                if cur[0] and (cur[1] + cur[2]) > 0:
                    groups.append({
                        "user_prompt": cur[0],
                        "total_tokens": cur[1] + cur[2],
                        "input_tokens": cur[1],
                        "output_tokens": cur[2],
                    })
                cur = [up, 0, 0]
            cur[1] += q["input_tokens"]
            cur[2] += q["output_tokens"]
        if cur[0] and (cur[1] + cur[2]) > 0:
            groups.append({
                "user_prompt": cur[0],
                "total_tokens": cur[1] + cur[2],
                "input_tokens": cur[1],
                "output_tokens": cur[2],
            })
    return groups
