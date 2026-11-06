"""Verify provider-issued bearer tokens; never accept a caller-supplied owner ID."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse
from uuid import uuid4

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from story_api.database import get_engine
from story_api.storage import AppUser

bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/auth", tags=["authentication"])


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str


@dataclass(frozen=True)
class User:
    id: str
    issuer: str
    subject: str


def unauthorized():
    return HTTPException(
        401, detail="Invalid or missing access token.", headers={"WWW-Authenticate": "Bearer"}
    )


class TokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str, parties: tuple[str, ...]):
        if not issuer or not audience or not parties:
            raise ValueError("Missing authentication configuration")
        for value in (issuer, jwks_url):
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Authentication URLs must use HTTPS")
        self.issuer, self.audience, self.parties = issuer, audience, parties
        # The URL comes only from server configuration, never jku/iss inside a token.
        self.keys = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)

    def verify(self, token: str) -> Identity:
        try:
            if len(token) > 16384:
                raise jwt.InvalidTokenError()
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise jwt.InvalidTokenError()
            signing_key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "azp"]},
            )
            if (
                not isinstance(claims["sub"], str)
                or not claims["sub"].strip()
                or len(claims["sub"]) > 255
                or claims["azp"] not in self.parties
                or claims.get("sts", "active") != "active"
            ):
                raise jwt.InvalidTokenError()
            return Identity(self.issuer, claims["sub"])
        except jwt.PyJWKClientConnectionError as exc:
            raise HTTPException(503, detail="Authentication provider is unavailable.") from exc
        except jwt.PyJWTError as exc:
            raise unauthorized() from exc


@lru_cache(maxsize=1)
def get_verifier():
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    try:
        return TokenVerifier(
            os.getenv("AUTH_ISSUER", "").strip(),
            os.getenv("AUTH_AUDIENCE", "").strip(),
            os.getenv("AUTH_JWKS_URL", "").strip(),
            tuple(
                p.strip() for p in os.getenv("AUTH_AUTHORIZED_PARTIES", "").split(",") if p.strip()
            ),
        )
    except ValueError as exc:
        raise HTTPException(503, detail="Authentication is not configured.") from exc


def verified_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Identity:
    if credentials is None:
        raise unauthorized()
    return get_verifier().verify(credentials.credentials)


def resolve_user(engine, identity: Identity) -> User:
    with Session(engine) as session, session.begin():
        session.execute(
            insert(AppUser)
            .values(
                id=str(uuid4()),
                issuer=identity.issuer,
                subject=identity.subject,
            )
            .on_conflict_do_nothing(index_elements=["issuer", "subject"])
        )
        user = session.scalar(
            select(AppUser).where(
                AppUser.issuer == identity.issuer,
                AppUser.subject == identity.subject,
            )
        )
        return User(user.id, user.issuer, user.subject)


def current_user(identity: Annotated[Identity, Depends(verified_identity)]) -> User:
    return resolve_user(get_engine(), identity)


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]):
    return {"id": user.id, "issuer": user.issuer, "subject": user.subject}
