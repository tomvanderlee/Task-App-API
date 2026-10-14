import json
import os
from functools import wraps

import jwt
from flask import g, request
from jwt import PyJWKSet

from task_app_api.exceptions import UnauthorizedError

ALGORITHMS = ["RS256"]


def get_jwks() -> dict:
    # Mock JWKS retrieval: reads the file written by scripts/generate_jwt.py.
    # Replace this with a fetch of the OIDC provider's JWKS URI.
    with open(os.environ["JWKS_FILE"]) as f:
        return json.load(f)


def authenticate() -> None:
    """Verify the bearer token and store the username on `g`.

    Raises UnauthorizedError when the token is missing or invalid.
    """
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme != "Bearer" or not token.strip():
        raise UnauthorizedError("Expected 'Authorization: Bearer <token>'")

    try:
        header = jwt.get_unverified_header(token.strip())
        key = PyJWKSet.from_dict(get_jwks())[header["kid"]]
        claims = jwt.decode(
            token.strip(),
            key.key,
            algorithms=ALGORITHMS,
            options={"require": ["exp", "username"]},
        )
    except (jwt.PyJWTError, KeyError) as e:
        raise UnauthorizedError from e

    username = claims["username"]
    if not isinstance(username, str) or not username.strip():
        raise UnauthorizedError

    g.username = username


def require_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        authenticate()
        return view(*args, **kwargs)

    return wrapper
