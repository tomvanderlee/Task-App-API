from flask import g, jsonify, request

SCHEME = "User"


def authenticate():
    # TODO: Replace this with actual authentication using a OIDC provider
    scheme, _, username = request.headers.get("Authorization", "").partition(" ")

    username = username.strip()

    if scheme != SCHEME or not username:
        return jsonify(detail=f"Expected 'Authorization: {SCHEME} <username>'"), 401

    g.username = username
