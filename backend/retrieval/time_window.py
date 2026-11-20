# retrieval/time_window.py
"""Questions about a period: "what happened in the last month?", "changes since October", "in 2025".

Search hands the model the few commits most similar to a question. That suits "why was X changed?",
but a question about everything in a period isn't similar to any one commit, so search would return a
handful and the answer would miss most of the period. When a question names a period, the answer is
built from every commit in it instead (see app/services/rag.py)."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UNIT_DAYS = {"day": 1, "week": 7, "fortnight": 14, "month": 30, "quarter": 91, "year": 365}
WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "couple of": 2, "few": 3}
_MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
                "october", "november", "december"]
MONTHS = {**{m: i for i, m in enumerate(_MONTH_NAMES, 1)},
          **{m[:3]: i for i, m in enumerate(_MONTH_NAMES, 1)}, "sept": 9}

_NUMBER = r"(\d{1,3}|couple of|few|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_UNIT = r"(day|week|fortnight|month|quarter|year)s?"
_MONTH = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
_YEAR = r"((?:19|20)\d\d)"

_ROLLING = re.compile(rf"\b(?:last|past|previous)\s+(?:{_NUMBER}\s+)?{_UNIT}\b")
_THIS = re.compile(r"\bthis\s+(week|month|year)\b")
_DAY = re.compile(r"\b(today|yesterday)\b")
_SINCE_DATE = re.compile(r"\b(?:since|after|from)\s+(\d{4}-\d{2}-\d{2})\b")
_SINCE_MONTH = re.compile(rf"\b(?:since|from)\s+{_MONTH}(?:\s+{_YEAR})?\b")
_SINCE_YEAR = re.compile(rf"\b(?:since|from)\s+{_YEAR}\b")
_IN_MONTH = re.compile(rf"\b(?:in|during|for)\s+{_MONTH}(?:\s+{_YEAR})?\b")
_IN_YEAR = re.compile(rf"\b(?:in|during)\s+{_YEAR}\b")


@dataclass(frozen=True)
class Period:
    start: datetime   # inclusive, UTC
    end: datetime     # exclusive, UTC
    label: str        # the words in the question, e.g. "last 1 month"
    # "Last month", "since October": up to now. Commit times come from authors' clocks, which can run a
    # little ahead, so these periods have no upper limit; "in October" or "yesterday" keep their end
    until_now: bool = False


def _count(word: str | None) -> int:
    if not word:
        return 1
    return int(word) if word.isdigit() else WORD_NUMBERS.get(word, 1)


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _next_month(start: datetime) -> datetime:
    return _month_start(start.year + (start.month == 12), start.month % 12 + 1)


def _recent_year(month: int, now: datetime) -> int:
    """A month named without a year means the most recent one that has started."""
    return now.year if month <= now.month else now.year - 1


def find_period(question: str, now: datetime | None = None) -> Period | None:
    """The period a question asks about, or None if it doesn't name one."""
    now = now or datetime.now(timezone.utc)
    q = " ".join(question.lower().split())
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if m := _ROLLING.search(q):
        days = _count(m.group(1)) * UNIT_DAYS[m.group(2)]
        return Period(now - timedelta(days=days), now, m.group(0), until_now=True)
    if m := _THIS.search(q):
        unit = m.group(1)
        start = (midnight - timedelta(days=midnight.weekday()) if unit == "week"
                 else midnight.replace(day=1) if unit == "month" else midnight.replace(month=1, day=1))
        return Period(start, now, m.group(0), until_now=True)
    if m := _DAY.search(q):
        if m.group(1) == "today":
            return Period(midnight, now, "today", until_now=True)
        return Period(midnight - timedelta(days=1), midnight, "yesterday")
    if m := _SINCE_DATE.search(q):
        try:
            start = datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return Period(start, now, m.group(0), until_now=True)
    if m := _SINCE_MONTH.search(q):
        month = MONTHS[m.group(1)]
        year = int(m.group(2)) if m.group(2) else _recent_year(month, now)
        return Period(_month_start(year, month), now, m.group(0), until_now=True)
    if m := _SINCE_YEAR.search(q):
        return Period(_month_start(int(m.group(1)), 1), now, m.group(0), until_now=True)
    if m := _IN_MONTH.search(q):
        month = MONTHS[m.group(1)]
        # "may" is also a verb: only count it as a month when a year follows ("in May 2025")
        if m.group(1) == "may" and not m.group(2):
            return None
        start = _month_start(int(m.group(2)) if m.group(2) else _recent_year(month, now), month)
        return Period(start, _next_month(start), m.group(0))
    if m := _IN_YEAR.search(q):
        year = int(m.group(1))
        return Period(_month_start(year, 1), _month_start(year + 1, 1), m.group(0))
    return None


def committed_at(chunk: dict) -> datetime:
    """A stored commit's time, in UTC."""
    when = datetime.fromisoformat(chunk["metadata"]["timestamp"])
    return when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)


def commits_in(period: Period, chunks: list[dict]) -> list[dict]:
    """Every commit in the period, oldest first."""
    def inside(when: datetime) -> bool:
        return period.start <= when and (period.until_now or when < period.end)
    return sorted((c for c in chunks if inside(committed_at(c))), key=committed_at)
