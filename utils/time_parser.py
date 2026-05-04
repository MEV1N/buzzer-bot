# ──────────────────────────────────────────────────────────────────────────────
# utils/time_parser.py
# Parses human-readable time strings (e.g. "2h", "30m") into seconds.
# ──────────────────────────────────────────────────────────────────────────────

import re

UNITS = {
    's': 1,
    'm': 60,
    'h': 3600,
    'd': 86400,
    'w': 604800,
}


def parse_time(s: str) -> float | None:
    """
    Parse a time string like '30s', '10m', '2h', '1d' into seconds.
    Returns None if the format is invalid.
    """
    if not isinstance(s, str):
        return None
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([smhdw])', s.strip().lower())
    if not match:
        return None
    value = float(match.group(1))
    unit  = match.group(2)
    if value <= 0:
        return None
    return value * UNITS[unit]


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.
    e.g. 7200 → '2h', 90 → '1m 30s'
    """
    seconds = int(seconds)
    if seconds <= 0:
        return '0s'
    parts = []
    for unit, secs in [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]:
        if seconds >= secs:
            parts.append(f'{seconds // secs}{unit}')
            seconds %= secs
    return ' '.join(parts)
