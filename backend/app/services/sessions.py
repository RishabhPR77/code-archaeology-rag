# app/services/sessions.py
"""Signing in: the session cookie, and the step between the first factor and an authenticator code."""
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.schemas import MeOut, TwoFactorRequiredOut
from app.security import (SESSION_COOKIE, TWO_FACTOR_COOKIE, create_session_token, create_two_factor_token,
                          decode_session_token, decode_two_factor_token, session_cookie_kwargs,
                          two_factor_cookie_kwargs)
from app.services import audit, two_factor
from app.services.users import limits_for, user_out

METHODS = {"password": "with a password", "google": "with Google", "github": "with GitHub",
           "email": "after confirming the email address"}


def me(db: Session, user: User) -> MeOut:
    return MeOut(user=user_out(db, user), limits=limits_for(db, user))


def start(response: Response, user: User):
    response.set_cookie(value=create_session_token(user.id, user.session_version or 0), **session_cookie_kwargs())


def end(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


def session_user(request: Request, db: Session) -> User | None:
    """The signed-in user, or None. For routes that work with or without a session."""
    token = request.cookies.get(SESSION_COOKIE)
    session = decode_session_token(token) if token else None
    user = db.get(User, session[0]) if session else None
    return user if user is not None and session[1] == (user.session_version or 0) else None


def sign_in(db: Session, request: Request, response: Response, user: User, method: str) -> MeOut | TwoFactorRequiredOut:
    """The first factor passed. Start a session, or ask for the authenticator code first."""
    if two_factor.enabled(user):
        response.set_cookie(value=create_two_factor_token(user.id, user.session_version or 0, method),
                            **two_factor_cookie_kwargs())
        return TwoFactorRequiredOut()
    start(response, user)
    audit.record(db, user, "sign_in", request, METHODS.get(method, ""))
    return me(db, user)


def sign_in_redirect(db: Session, request: Request, user: User, method: str, landing: str) -> RedirectResponse:
    """The same, for Google and GitHub, which come back through a redirect."""
    frontend = get_settings().frontend_url
    if two_factor.enabled(user):
        resp = RedirectResponse(f"{frontend}/two-factor", status_code=302)
        resp.set_cookie(value=create_two_factor_token(user.id, user.session_version or 0, method),
                        **two_factor_cookie_kwargs())
        return resp
    resp = RedirectResponse(f"{frontend}{landing}", status_code=302)
    start(resp, user)
    audit.record(db, user, "sign_in", request, METHODS.get(method, ""))
    return resp


def pending_two_factor(request: Request, db: Session) -> tuple[User, str] | None:
    """Who passed the first step in the last five minutes, and how."""
    token = request.cookies.get(TWO_FACTOR_COOKIE)
    pending = decode_two_factor_token(token) if token else None
    user = db.get(User, pending[0]) if pending else None
    if user is None or pending[1] != (user.session_version or 0) or not two_factor.enabled(user):
        return None
    return user, pending[2]


def end_two_factor(response: Response):
    response.delete_cookie(TWO_FACTOR_COOKIE, path="/api/auth")
