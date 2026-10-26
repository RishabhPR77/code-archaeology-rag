# app/services/oauth.py
"""Pieces shared by the GitHub and Google sign-in flows: state, PKCE and HTTP."""
import base64
import hashlib
import json
import secrets

import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import get_settings

FLOW_COOKIE = "ca_oauth"
FLOW_TTL = 600  # seconds the user has to finish signing in


def http() -> httpx.Client:
    """Outbound HTTP for OAuth calls — one seam, so tests can swap the transport."""
    return httpx.Client(timeout=15, headers={"User-Agent": "code-archaeologist"})


def callback_url(provider: str) -> str:
    # The frontend proxies /api to this server, so OAuth stays on one origin
    return f"{get_settings().frontend_url}/api/auth/{provider}/callback"


def start_flow(provider: str, authorize_url: str, params: dict) -> RedirectResponse:
    """Redirect to the provider with a fresh state and PKCE challenge, remembered in a cookie."""
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = httpx.QueryParams({**params, "state": state, "code_challenge": challenge,
                               "code_challenge_method": "S256"})
    resp = RedirectResponse(f"{authorize_url}?{query}", status_code=302)
    flow = json.dumps({"provider": provider, "state": state, "verifier": verifier})
    resp.set_cookie(FLOW_COOKIE, flow, max_age=FLOW_TTL, httponly=True, samesite="lax",
                    secure=get_settings().is_production, path="/api/auth")
    return resp


def finish_flow(request: Request, provider: str, state: str) -> str | None:
    """Return the PKCE verifier if the callback's state matches what we sent, else None."""
    try:
        flow = json.loads(request.cookies.get(FLOW_COOKIE, ""))
    except ValueError:
        return None
    if flow.get("provider") != provider or not secrets.compare_digest(flow.get("state", ""), state or "-"):
        return None
    return flow.get("verifier")


def fail(reason: str) -> RedirectResponse:
    resp = RedirectResponse(f"{get_settings().frontend_url}/login?error={reason}", status_code=302)
    resp.delete_cookie(FLOW_COOKIE, path="/api/auth")
    return resp
