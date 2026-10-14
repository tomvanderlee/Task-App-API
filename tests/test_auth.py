import json
import time
from uuid import uuid4

import jwt
import pytest
from conftest import KID, _make_key, make_token
from flask import g

from task_app_api.api import app
from task_app_api.auth import authenticate, get_jwks

MALFORMED = "Expected 'Authorization: Bearer <token>'"
INVALID = "Invalid token"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def run(headers):
    """Call authenticate() directly, returns (result, g.username)"""
    with app.test_request_context(headers=headers):
        result = authenticate()
        return result, g.get("username")


def jwk(key, kid):
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


class TestGetJwks:
    def test_returns_contents_of_jwks_file(self, tmp_path, monkeypatch):
        path = tmp_path / "jwks.json"
        path.write_text(json.dumps({"keys": [{"kid": "abc"}]}))
        monkeypatch.setenv("JWKS_FILE", str(path))

        assert get_jwks() == {"keys": [{"kid": "abc"}]}

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JWKS_FILE", str(tmp_path / "missing.json"))

        with pytest.raises(FileNotFoundError):
            get_jwks()

    def test_unset_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("JWKS_FILE")

        with pytest.raises(KeyError):
            get_jwks()


class TestAuthenticate:
    def test_valid_token_sets_username(self):
        result, username = run(bearer(make_token("tom")))

        assert result is None
        assert username == "tom"

    def test_surrounding_whitespace_is_ignored(self):
        result, username = run({"Authorization": f"Bearer  {make_token('tom')} "})

        assert result is None
        assert username == "tom"

    def test_extra_claims_are_ignored(self):
        result, username = run(bearer(make_token("tom", admin=True)))

        assert result is None
        assert username == "tom"

    def test_selects_key_by_kid(self, tmp_path, monkeypatch):
        other = _make_key()
        path = tmp_path / "jwks.json"
        path.write_text(
            json.dumps({"keys": [jwk(_make_key(), KID), jwk(other, "rotated")]})
        )
        monkeypatch.setenv("JWKS_FILE", str(path))

        result, username = run(bearer(make_token("ann", key=other, kid="rotated")))

        assert result is None
        assert username == "ann"

    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"Authorization": ""},
            {"Authorization": "Bearer"},
            {"Authorization": "Bearer "},
            {"Authorization": "Bearer    "},
            {"Authorization": "User tom"},
            {"Authorization": "Basic dG9tOnBhc3M="},
            {"Authorization": f"bearer {make_token()}"},
            {"Authorization": make_token()},
        ],
        ids=[
            "missing",
            "empty",
            "scheme-only",
            "scheme-and-space",
            "scheme-and-spaces",
            "user-scheme",
            "basic-scheme",
            "lowercase-scheme",
            "no-scheme",
        ],
    )
    def test_malformed_header_is_rejected(self, headers):
        result, username = run(headers)

        response, status = result
        assert status == 401
        assert response.json == {"detail": MALFORMED}
        assert username is None

    @pytest.mark.parametrize(
        "token",
        [
            "not-a-jwt",
            "a.b.c",
            make_token(expires_in=-60),
            make_token(key=_make_key()),
            make_token(kid="unknown"),
            make_token(username=None),
            make_token(exp=None),
            make_token(username=""),
            make_token(username="   "),
            make_token(username=123),
            jwt.encode(
                {"username": "tom", "exp": int(time.time()) + 60}, _make_key(), "RS256"
            ),
            jwt.encode(
                {"username": "tom", "exp": int(time.time()) + 60},
                None,
                "none",
                {"kid": KID},
            ),
            jwt.encode(
                {"username": "tom", "exp": int(time.time()) + 60},
                "secret" * 8,
                "HS256",
                {"kid": KID},
            ),
        ],
        ids=[
            "garbage",
            "three-garbage-segments",
            "expired",
            "wrong-signing-key",
            "unknown-kid",
            "missing-username-claim",
            "missing-exp-claim",
            "empty-username",
            "blank-username",
            "non-string-username",
            "missing-kid-header",
            "alg-none",
            "alg-hs256",
        ],
    )
    def test_invalid_token_is_rejected(self, token):
        result, username = run(bearer(token))

        response, status = result
        assert status == 401
        assert response.json == {"detail": INVALID}
        assert username is None


class TestWiring:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/tasks/"),
            ("post", "/tasks/"),
            ("get", f"/tasks/{uuid4()}/"),
            ("put", f"/tasks/{uuid4()}/"),
            ("delete", f"/tasks/{uuid4()}/"),
        ],
    )
    def test_every_endpoint_requires_a_token(self, client, method, path):
        response = getattr(client, method)(path)

        assert response.status_code == 401
        assert response.json == {"detail": MALFORMED}
