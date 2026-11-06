import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from story_api import auth, main
from story_api.auth import Identity, TokenVerifier

ISSUER = "https://auth.example.invalid"
AUDIENCE = "story-api"
PARTY = "http://localhost:3000"


@pytest.fixture
def signer(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = TokenVerifier(ISSUER, AUDIENCE, ISSUER + "/.well-known/jwks.json", (PARTY,))
    monkeypatch.setattr(
        verifier.keys,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=key.public_key()),
    )
    monkeypatch.setattr(auth, "get_verifier", lambda: verifier)

    def token(subject="user-a", **changes):
        claims = {
            "sub": subject,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "azp": PARTY,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})

    return verifier, token, key


def test_valid_token_returns_verified_identity(signer):
    verifier, token, _ = signer
    assert verifier.verify(token()) == Identity(ISSUER, "user-a")


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 1},
        {"iss": "https://other.invalid"},
        {"aud": "other-api"},
        {"azp": "https://attacker.invalid"},
        {"sub": ""},
        {"sub": "x" * 256},
        {"iat": 9999999999},
        {"nbf": 9999999999},
        {"aud": None},
        {"azp": None},
        {"sts": "pending"},
    ],
)
def test_invalid_claims_rejected(signer, changes):
    verifier, token, _ = signer
    with pytest.raises(HTTPException) as error:
        verifier.verify(token(**changes))
    assert error.value.status_code == 401


def test_forged_signature_and_wrong_algorithm_rejected(signer):
    verifier, token, _ = signer
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(token(), options={"verify_signature": False})
    for forged in [
        jwt.encode(claims, other, algorithm="RS256", headers={"kid": "test-key"}),
        jwt.encode(
            claims,
            "test-only-hmac-key-not-used-by-app-123",
            algorithm="HS256",
            headers={"kid": "test-key"},
        ),
        "not-a-jwt",
    ]:
        with pytest.raises(HTTPException) as error:
            verifier.verify(forged)
        assert error.value.status_code == 401


def test_provider_outage_is_not_an_authentication_bypass(signer, monkeypatch):
    verifier, token, _ = signer

    def unavailable(token):
        raise jwt.PyJWKClientConnectionError("private details")

    monkeypatch.setattr(verifier.keys, "get_signing_key_from_jwt", unavailable)
    with pytest.raises(HTTPException) as error:
        verifier.verify(token())
    assert error.value.status_code == 503
    assert "private details" not in error.value.detail


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/auth/me", None),
        ("get", "/api/stories", None),
        ("post", "/api/stories", {}),
        ("post", "/api/stories/generate", {}),
        ("get", "/api/stories/00000000-0000-0000-0000-000000000001", None),
        ("patch", "/api/stories/00000000-0000-0000-0000-000000000001", {}),
        ("get", "/api/stories/00000000-0000-0000-0000-000000000001/runs", None),
        ("post", "/api/stories/00000000-0000-0000-0000-000000000001/runs", None),
    ],
)
def test_missing_token_denied_on_every_protected_route(method, path, payload):
    response = TestClient(main.app).request(method, path, json=payload)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_real_jwks_key_selection_and_untrusted_jku_ignored(signer, monkeypatch):
    verifier, token, key = signer
    client = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json")
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    monkeypatch.setattr(client, "fetch_data", lambda: {"keys": [public]})
    verifier.keys = client
    claims = jwt.decode(token(), options={"verify_signature": False})
    signed = jwt.encode(
        claims,
        key,
        algorithm="RS256",
        headers={"kid": "test-key", "jku": "https://attacker.invalid/keys"},
    )
    assert verifier.verify(signed).subject == "user-a"
    unknown = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "unknown"})
    with pytest.raises(HTTPException) as error:
        verifier.verify(unknown)
    assert error.value.status_code == 401
