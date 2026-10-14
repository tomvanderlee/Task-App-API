import json
import os

import jwt
from flask import g, jsonify, request
from jwt import PyJWKSet

ALGORITHMS = ["RS256"]


def get_jwks() -> dict:
    # Mock JWKS retrieval: reads the file written by scripts/generate_jwt.py.
    # Replace this with a fetch of the OIDC provider's JWKS URI.
    with open(os.environ["JWKS_FILE"]) as f:
        return json.load(f)


def authenticate():
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme != "Bearer" or not token.strip():
        return jsonify(detail="Expected 'Authorization: Bearer <token>'"), 401

    try:
        header = jwt.get_unverified_header(token.strip())
        key = PyJWKSet.from_dict(get_jwks())[header["kid"]]
        claims = jwt.decode(
            token.strip(),
            key.key,
            algorithms=ALGORITHMS,
            options={"require": ["exp", "username"]},
        )
    except (jwt.PyJWTError, KeyError):
        return jsonify(detail="Invalid token"), 401

    g.username = claims["username"]
