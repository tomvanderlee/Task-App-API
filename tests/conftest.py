import json
import os
import tempfile
import time
from pathlib import Path

tmp_dir = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{tmp_dir / 'test.sqlite'}"
os.environ["JWKS_FILE"] = str(tmp_dir / "jwks.json")

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlmodel import SQLModel

from task_app_api.api import app
from task_app_api.db import engine

KID = "test-key"


def _make_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_key = _make_key()
_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_key.public_key()))
_jwk.update(kid=KID, use="sig", alg="RS256")
Path(os.environ["JWKS_FILE"]).write_text(json.dumps({"keys": [_jwk]}))


def make_token(username="tom", *, key=_key, kid=KID, expires_in=3600, **claims):
    now = int(time.time())
    payload = {"username": username, "iat": now, "exp": now + expires_in, **claims}
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture(autouse=True)
def database():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {make_token()}"}
