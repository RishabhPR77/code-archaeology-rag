# app/services/audit.py
"""Security events: a short history of what happened to each account, shown to its owner.

It lets people spot something they didn't do (a sign-in from an unknown device, a password change),
and it's the trail to look at after an incident. IP addresses are shortened before they're stored."""
import ipaddress
import re
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import SecurityEvent, User, utcnow
from app.schemas import SecurityEventOut, as_utc

KEEP_FOR = timedelta(days=90)

LABELS = {
    "account_created":          "Account created",
    "sign_in":                  "Signed in",
    "sign_in_failed":           "Wrong password entered",
    "two_factor_failed":        "Wrong two-step code entered",
    "password_changed":         "Password changed",
    "password_set":             "Password added",
    "password_reset":           "Password reset by email",
    "signed_out_everywhere":    "Signed out everywhere",
    "two_factor_enabled":       "Two-step sign-in turned on",
    "two_factor_disabled":      "Two-step sign-in turned off",
    "recovery_codes_created":   "New recovery codes created",
    "recovery_code_used":       "Recovery code used",
    "api_key_saved":            "Model API key saved",
    "api_key_removed":          "Model API key removed",
    "github_connected":         "GitHub connected",
    "github_disconnected":      "GitHub disconnected",
}

_BROWSERS = [("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
             ("Safari/", "Safari")]
_SYSTEMS = [("Windows", "Windows"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
            ("Mac OS X", "macOS"), ("CrOS", "ChromeOS"), ("Linux", "Linux")]


def short_ip(ip: str) -> str:
    """Enough to recognise a network, not to pinpoint a person: 203.0.113.x, 2001:db8:1::/48."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.version == 4:
        return ".".join(str(addr).split(".")[:3]) + ".x"
    return str(ipaddress.ip_network(f"{addr}/48", strict=False))


def device(user_agent: str) -> str:
    """"Chrome on Windows" from a User-Agent header; "" if it isn't recognisable."""
    ua = user_agent or ""
    browser = next((name for marker, name in _BROWSERS if marker in ua), "")
    system = next((name for marker, name in _SYSTEMS if marker in ua), "")
    if re.search(r"python|curl|httpx|wget", ua, re.I):
        return "A script"
    return " on ".join(x for x in (browser, system) if x)


def record(db: Session, user: User, kind: str, request: Request | None = None, detail: str = ""):
    """Add an event and commit. The demo account is shared, so it keeps no history."""
    if user.is_demo:
        return
    from app.deps import client_ip   # deps imports the models; importing it here avoids a cycle
    db.add(SecurityEvent(
        user_id=user.id, kind=kind, detail=detail[:200],
        ip=short_ip(client_ip(request)) if request else "",
        device=device(request.headers.get("user-agent", ""))[:120] if request else ""))
    db.commit()


def recent(db: Session, user: User, limit: int = 30) -> list[SecurityEventOut]:
    events = db.scalars(select(SecurityEvent).where(SecurityEvent.user_id == user.id)
                        .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc()).limit(limit))
    return [SecurityEventOut(kind=e.kind, label=LABELS.get(e.kind, e.kind.replace("_", " ").capitalize()),
                             detail=e.detail, ip=e.ip, device=e.device, created_at=as_utc(e.created_at))
            for e in events]


def prune(db: Session) -> int:
    result = db.execute(delete(SecurityEvent).where(SecurityEvent.created_at < utcnow() - KEEP_FOR))
    db.commit()
    return result.rowcount or 0
