"""Weekly home-workout streak (CAP-10). Pure: local dates in, a Streak out. Weeks are Monday to Sunday."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

RECENT_WEEKS = 8


@dataclass(frozen=True)
class Streak:
    weeks: int
    this_week: bool
    last_streak: int
    recent: list[tuple[date, bool]]  # (week's Monday, counted), oldest first, the current week last


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def streak(local_dates: Iterable[date], today: date) -> Streak:
    counted = {week_start(d) for d in local_dates}
    this = week_start(today)
    this_week = this in counted
    end = this if this_week else this - timedelta(weeks=1)  # the open week never breaks the chain

    def run_ending(at: date) -> int:
        n = 0
        while at in counted:
            n += 1
            at -= timedelta(weeks=1)
        return n

    weeks = run_ending(end)
    if weeks:
        last = weeks
    else:  # broken: the most recent run of counted weeks, if any
        past = [w for w in counted if w <= this]
        last = run_ending(max(past)) if past else 0
    recent = [(this - timedelta(weeks=i), (this - timedelta(weeks=i)) in counted) for i in range(RECENT_WEEKS - 1, -1, -1)]
    return Streak(weeks, this_week, last, recent)
