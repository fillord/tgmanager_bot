# utils/time_parser.py
from datetime import datetime, timedelta

def parse_time(time_str: str) -> timedelta | None:
    """Парсит строку времени (1d, 2h, 30m) и возвращает timedelta."""
    if not time_str or not time_str[:-1].isdigit():
        return None

    unit = time_str[-1].lower()
    value = int(time_str[:-1])

    if unit == 'm':
        return timedelta(minutes=value)
    if unit == 'h':
        return timedelta(hours=value)
    if unit == 'd':
        return timedelta(days=value)

    return None