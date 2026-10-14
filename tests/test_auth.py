import json
import time
from uuid import uuid4

import jwt
import pytest
from conftest import KID, _make_key, make_token
from flask import g

from task_app_api.api import app
from task_app_api.auth import authenticate, get_jwks, require_auth
from task_app_api.exceptions import UnauthorizedError

MALFORMED = "Expected 'Authorization: Bearer <token>'"
INVALID = "Invalid token"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def run(headers):
    """Call authenticate() directly, returns g.username"""
    with app.test_request_context(headers=headers):
        authenticate()
        return g.get("username")


def run_rejected(headers):
    """Call authenticate() expecting a rejection, returns (error, g.username)"""
    with app.test_request_context(headers=headers):
        with pytest.raises(UnauthorizedError) as exc_info:
            authenticate()
        return exc_info.value, g.get("username")


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
        username = run(bearer(make_token("tom")))

        assert username == "tom"

    def test_surrounding_whitespace_is_ignored(self):
        username = run({"Authorization": f"Bearer  {make_token('tom')} "})

        assert username == "tom"

    def test_extra_claims_are_ignored(self):
        username = run(bearer(make_token("tom", admin=True)))

        assert username == "tom"

    def test_selects_key_by_kid(self, tmp_path, monkeypatch):
        other = _make_key()
        path = tmp_path / "jwks.json"
        path.write_text(
            json.dumps({"keys": [jwk(_make_key(), KID), jwk(other, "rotated")]})
        )
        monkeypatch.setenv("JWKS_FILE", str(path))

        username = run(bearer(make_token("ann", key=other, kid="rotated")))

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
        error, username = run_rejected(headers)

        assert error.detail == MALFORMED
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
        error, username = run_rejected(bearer(token))

        assert error.detail == INVALID
        assert username is None


class TestRequireAuth:
    def test_calls_view_with_arguments_and_returns_its_response(self):
        @require_auth
        def view(a, b=None):
            return {"a": a, "b": b}

        with app.test_request_context(headers=bearer(make_token("tom"))):
            assert view(1, b=2) == {"a": 1, "b": 2}

    def test_sets_username_before_calling_view(self):
        @require_auth
        def view():
            return g.username

        with app.test_request_context(headers=bearer(make_token("tom"))):
            assert view() == "tom"

    def test_view_is_not_called_without_valid_token(self):
        calls = []

        @require_auth
        def view():
            calls.append(1)

        with (
            app.test_request_context(headers=bearer("garbage")),
            pytest.raises(UnauthorizedError),
        ):
            view()

        assert calls == []


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
