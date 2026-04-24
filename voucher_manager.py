"""
voucher_manager.py
Manages auto-incrementing daily voucher numbers in format DDMMYYXXXX.
Counter is persisted to a local JSON file so it survives app restarts.
"""

import json
import os
from datetime import date

COUNTER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voucher_counter.json")


def _load_counter() -> dict:
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_counter(data: dict):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_voucher_number() -> str:
    """
    Returns next voucher number in format DDMMYYXXXX.
    The date is always TODAY (the day of scanning).
    XXXX is a zero-padded counter that resets to 0001 each new day.
    Example: 1304260001, 1304260002 ...
    """
    today_str = date.today().strftime("%d%m%y")  # e.g. "130426"
    data = _load_counter()

    last_date = data.get("date", "")
    last_count = data.get("count", 0)

    if last_date == today_str:
        new_count = last_count + 1
    else:
        # New day — reset counter
        new_count = 1

    data["date"] = today_str
    data["count"] = new_count
    _save_counter(data)

    return f"{today_str}{str(new_count).zfill(4)}"


def peek_current_count() -> int:
    """Returns the current counter value for today without incrementing."""
    today_str = date.today().strftime("%d%m%y")
    data = _load_counter()
    if data.get("date", "") == today_str:
        return data.get("count", 0)
    return 0
