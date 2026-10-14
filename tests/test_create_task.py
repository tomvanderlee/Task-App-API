from uuid import UUID

import pytest
from conftest import _make_key, make_token
from sqlmodel import Session, select

from task_app_api.db import engine
from task_app_api.models import Task, User

VALID = {"title": "Buy milk", "status": "todo"}


def post(client, body=VALID, headers=None):
    return client.post("/tasks/", json=body, headers=headers)


def test_creates_task(client, auth_headers):
    response = post(client, headers=auth_headers)

    assert response.status_code == 201
    body = response.json
    assert body["title"] == "Buy milk"
    assert body["status"] == "todo"
    UUID(body["id"])
    UUID(body["owner_id"])
    assert body["created_date"]


def test_persists_task_for_token_user(client, auth_headers):
    task_id = post(client, headers=auth_headers).json["id"]

    with Session(engine) as session:
        task = session.get(Task, UUID(task_id))
        user = session.exec(select(User)).one()
        assert user.username == "tom"
        assert task.owner_id == user.id


def test_user_is_created_once(client, auth_headers):
    first = post(client, headers=auth_headers).json
    second = post(client, headers=auth_headers).json

    assert first["owner_id"] == second["owner_id"]
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == 1


def test_tasks_of_different_users_have_different_owners(client):
    tom = {"Authorization": f"Bearer {make_token('tom')}"}
    ann = {"Authorization": f"Bearer {make_token('ann')}"}

    assert (
        post(client, headers=tom).json["owner_id"]
        != post(client, headers=ann).json["owner_id"]
    )


def test_ignores_server_controlled_fields(client, auth_headers):
    body = {**VALID, "id": "11111111-1111-1111-1111-111111111111", "owner_id": "x"}
    response = post(client, body, auth_headers)

    assert response.status_code == 201
    assert response.json["id"] != body["id"]
    assert response.json["owner_id"] != "x"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": "No status"},
        {"status": "todo"},
        {"title": "Bad status", "status": "finished"},
        {"title": 123, "status": "todo"},
    ],
)
def test_invalid_body_returns_400(client, auth_headers, body):
    response = post(client, body, auth_headers)

    assert response.status_code == 400
    assert "detail" in response.json


def test_non_json_body_returns_400(client, auth_headers):
    response = client.post("/tasks/", data="nope", headers=auth_headers)

    assert response.status_code == 400


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "User tom"},
        {"Authorization": f"Bearer {make_token(expires_in=-60)}"},
        {"Authorization": f"Bearer {make_token(key=_make_key())}"},
        {"Authorization": f"Bearer {make_token(kid='unknown')}"},
        {"Authorization": f"Bearer {make_token(username=None)}"},
    ],
    ids=[
        "missing",
        "no-token",
        "garbage",
        "wrong-scheme",
        "expired",
        "wrong-signing-key",
        "unknown-kid",
        "missing-username-claim",
    ],
)
def test_unauthenticated_returns_401(client, headers):
    response = post(client, headers=headers)

    assert response.status_code == 401
    assert "detail" in response.json
    with Session(engine) as session:
        assert session.exec(select(Task)).all() == []
        assert session.exec(select(User)).all() == []
