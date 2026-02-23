"""
Example DevBuddy plugin — copy this file and customize.

A plugin must define a generate_insights(sessions, queries) function that returns
a list of insight dicts. Each dict should have:
    id          str  — unique identifier (e.g. "my-plugin-insight")
    type        str  — "warning" | "info" | "neutral"
    title       str  — short headline shown in bold
    description str  — longer explanation
    action      str | None  — optional actionable tip (shown in green)

Plugins are auto-loaded from the plugins/ directory on every /api/insights call.
Any exception raised by a plugin is silently ignored so the dashboard stays stable.
"""


def generate_insights(sessions: list, queries: list) -> list:
    """Return custom insights derived from sessions and queries."""
    return []
