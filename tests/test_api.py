from uuid import UUID, uuid4

import pytest
from conftest import _make_key, make_token
from sqlmodel import Session, select

from task_app_api import api
from task_app_api.db import engine
from task_app_api.models import Task, User

VALID = {"title": "Buy milk", "status": "todo"}
UPDATE = {"title": "Buy oat milk", "status": "done"}


def post(client, body=VALID, headers=None):
    return client.post("/tasks/", json=body, headers=headers)


def headers_for(username):
    return {"Authorization": f"Bearer {make_token(username)}"}


def create(client, headers, title, status="todo"):
    response = client.post(
        "/tasks/", json={"title": title, "status": status}, headers=headers
    )
    assert response.status_code == 201
    return response.json


def titles(response):
    return [task["title"] for task in response.json["items"]]


class TestCreateTask:
    def test_creates_task(self, client, auth_headers):
        response = post(client, headers=auth_headers)

        assert response.status_code == 201
        body = response.json
        assert body["title"] == "Buy milk"
        assert body["status"] == "todo"
        UUID(body["id"])
        UUID(body["owner_id"])
        assert body["created_date"]

    def test_persists_task_for_token_user(self, client, auth_headers):
        task_id = post(client, headers=auth_headers).json["id"]

        with Session(engine) as session:
            task = session.get(Task, UUID(task_id))
            user = session.exec(select(User)).one()
            assert user.username == "tom"
            assert task.owner_id == user.id

    def test_user_is_created_once(self, client, auth_headers):
        first = post(client, headers=auth_headers).json
        second = post(client, headers=auth_headers).json

        assert first["owner_id"] == second["owner_id"]
        with Session(engine) as session:
            assert len(session.exec(select(User)).all()) == 1

    def test_tasks_of_different_users_have_different_owners(self, client):
        tom = {"Authorization": f"Bearer {make_token('tom')}"}
        ann = {"Authorization": f"Bearer {make_token('ann')}"}

        assert (
            post(client, headers=tom).json["owner_id"]
            != post(client, headers=ann).json["owner_id"]
        )

    def test_ignores_server_controlled_fields(self, client, auth_headers):
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
    def test_invalid_body_returns_400(self, client, auth_headers, body):
        response = post(client, body, auth_headers)

        assert response.status_code == 400
        assert "detail" in response.json

    def test_non_json_body_returns_400(self, client, auth_headers):
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
    def test_unauthenticated_returns_401(self, client, headers):
        response = post(client, headers=headers)

        assert response.status_code == 401
        assert "detail" in response.json
        with Session(engine) as session:
            assert session.exec(select(Task)).all() == []
            assert session.exec(select(User)).all() == []


class TestListTasks:
    def test_empty_list_for_new_user(self, client, auth_headers):
        response = client.get("/tasks/", headers=auth_headers)

        assert response.status_code == 200
        assert response.json == {"next": None, "prev": None, "items": []}

    def test_lists_created_tasks(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = client.get("/tasks/", headers=auth_headers)

        assert response.json == {"next": None, "prev": None, "items": [created]}

    def test_only_lists_own_tasks(self, client):
        create(client, headers_for("tom"), "Tom's task")
        create(client, headers_for("ann"), "Ann's task")

        response = client.get("/tasks/", headers=headers_for("tom"))

        assert titles(response) == ["Tom's task"]

    def test_search_is_case_insensitive_substring(self, client, auth_headers):
        create(client, auth_headers, "Buy MILK")
        create(client, auth_headers, "Walk the dog")

        response = client.get("/tasks/?q=milk", headers=auth_headers)

        assert titles(response) == ["Buy MILK"]

    def test_search_treats_wildcards_literally(self, client, auth_headers):
        create(client, auth_headers, "100% done")
        create(client, auth_headers, "Something else")

        response = client.get("/tasks/?q=%25", headers=auth_headers)

        assert titles(response) == ["100% done"]

    def test_filters_by_status(self, client, auth_headers):
        create(client, auth_headers, "A", "todo")
        create(client, auth_headers, "B", "done")

        response = client.get("/tasks/?status=done", headers=auth_headers)

        assert titles(response) == ["B"]

    def test_sorts_by_title(self, client, auth_headers):
        for title in ["b", "c", "a"]:
            create(client, auth_headers, title)

        response = client.get("/tasks/?sort=title", headers=auth_headers)

        assert titles(response) == ["a", "b", "c"]

    def test_sorts_by_created_date_by_default(self, client, auth_headers):
        for title in ["b", "c", "a"]:
            create(client, auth_headers, title)

        default = client.get("/tasks/", headers=auth_headers)
        explicit = client.get("/tasks/?sort=created_date", headers=auth_headers)

        assert titles(default) == ["b", "c", "a"]
        assert titles(explicit) == titles(default)

    def test_paginates(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(api, "PAGE_SIZE", 2)
        for title in "abcde":
            create(client, auth_headers, title)

        def page(n):
            return client.get(f"/tasks/?sort=title&page={n}", headers=auth_headers).json

        first, second, third, fourth = page(1), page(2), page(3), page(4)
        assert (first["prev"], first["next"]) == (None, 2)
        assert (second["prev"], second["next"]) == (1, 3)
        assert (third["prev"], third["next"]) == (2, None)
        assert [t["title"] for t in first["items"]] == ["a", "b"]
        assert [t["title"] for t in second["items"]] == ["c", "d"]
        assert [t["title"] for t in third["items"]] == ["e"]
        assert fourth["items"] == []
        assert fourth["next"] is None

    def test_page_holds_page_size_items(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(api, "PAGE_SIZE", 20)
        for i in range(21):
            create(client, auth_headers, f"task {i}")

        response = client.get("/tasks/", headers=auth_headers)

        assert len(response.json["items"]) == 20
        assert response.json["next"] == 2

    @pytest.mark.parametrize(
        "query",
        ["status=finished", "sort=owner", "page=0", "page=-1", "page=abc", "page="],
    )
    def test_invalid_query_returns_400(self, client, auth_headers, query):
        response = client.get(f"/tasks/?{query}", headers=auth_headers)

        assert response.status_code == 400
        assert "detail" in response.json

    def test_unauthenticated_returns_401(self, client):
        response = client.get("/tasks/")

        assert response.status_code == 401


class TestGetTask:
    def test_returns_task(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = client.get(f"/tasks/{created['id']}/", headers=auth_headers)

        assert response.status_code == 200
        assert response.json == created

    def test_unknown_id_returns_404(self, client, auth_headers):
        response = client.get(f"/tasks/{uuid4()}/", headers=auth_headers)

        assert response.status_code == 404
        assert response.json == {"detail": "Task not found"}

    def test_other_users_task_returns_404(self, client):
        created = create(client, headers_for("ann"), "Ann's task")

        response = client.get(f"/tasks/{created['id']}/", headers=headers_for("tom"))

        assert response.status_code == 404

    def test_invalid_id_returns_404(self, client, auth_headers):
        response = client.get("/tasks/not-a-uuid/", headers=auth_headers)

        assert response.status_code == 404

    def test_unauthenticated_returns_401(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = client.get(f"/tasks/{created['id']}/")

        assert response.status_code == 401


class TestUpdateTask:
    def put(self, client, task_id, body=UPDATE, headers=None):
        return client.put(f"/tasks/{task_id}/", json=body, headers=headers)

    def test_updates_task(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = self.put(client, created["id"], headers=auth_headers)

        assert response.status_code == 200
        assert response.json["title"] == "Buy oat milk"
        assert response.json["status"] == "done"

    def test_persists_update(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")
        self.put(client, created["id"], headers=auth_headers)

        response = client.get(f"/tasks/{created['id']}/", headers=auth_headers)

        assert response.json["title"] == "Buy oat milk"
        assert response.json["status"] == "done"

    def test_keeps_server_controlled_fields(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")
        body = {
            **UPDATE,
            "id": str(uuid4()),
            "owner_id": str(uuid4()),
            "created_date": "2000-01-01T00:00:00Z",
        }

        response = self.put(client, created["id"], body, auth_headers)

        assert response.status_code == 200
        for field in ("id", "owner_id", "created_date"):
            assert response.json[field] == created[field]

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
    def test_invalid_body_returns_400(self, client, auth_headers, body):
        created = create(client, auth_headers, "Buy milk")

        response = self.put(client, created["id"], body, auth_headers)

        assert response.status_code == 400
        assert "detail" in response.json
        unchanged = client.get(f"/tasks/{created['id']}/", headers=auth_headers)
        assert unchanged.json == created

    def test_unknown_id_returns_404(self, client, auth_headers):
        response = self.put(client, uuid4(), headers=auth_headers)

        assert response.status_code == 404
        assert response.json == {"detail": "Task not found"}

    def test_other_users_task_returns_404_and_is_unchanged(self, client):
        ann = headers_for("ann")
        created = create(client, ann, "Ann's task")

        response = self.put(client, created["id"], headers=headers_for("tom"))

        assert response.status_code == 404
        assert client.get(f"/tasks/{created['id']}/", headers=ann).json == created

    def test_unauthenticated_returns_401(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = self.put(client, created["id"])

        assert response.status_code == 401


class TestDeleteTask:
    def test_deletes_task(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = client.delete(f"/tasks/{created['id']}/", headers=auth_headers)

        assert response.status_code == 204
        assert response.data == b""
        with Session(engine) as session:
            assert session.get(Task, UUID(created["id"])) is None

    def test_deleted_task_is_gone(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")
        client.delete(f"/tasks/{created['id']}/", headers=auth_headers)

        get = client.get(f"/tasks/{created['id']}/", headers=auth_headers)
        again = client.delete(f"/tasks/{created['id']}/", headers=auth_headers)

        assert get.status_code == 404
        assert again.status_code == 404

    def test_only_deletes_the_given_task(self, client, auth_headers):
        keep = create(client, auth_headers, "Keep")
        remove = create(client, auth_headers, "Remove")

        client.delete(f"/tasks/{remove['id']}/", headers=auth_headers)

        assert titles(client.get("/tasks/", headers=auth_headers)) == ["Keep"]
        assert keep["id"] != remove["id"]

    def test_unknown_id_returns_404(self, client, auth_headers):
        response = client.delete(f"/tasks/{uuid4()}/", headers=auth_headers)

        assert response.status_code == 404
        assert response.json == {"detail": "Task not found"}

    def test_other_users_task_returns_404_and_is_kept(self, client):
        ann = headers_for("ann")
        created = create(client, ann, "Ann's task")

        response = client.delete(f"/tasks/{created['id']}/", headers=headers_for("tom"))

        assert response.status_code == 404
        assert client.get(f"/tasks/{created['id']}/", headers=ann).json == created

    def test_unauthenticated_returns_401(self, client, auth_headers):
        created = create(client, auth_headers, "Buy milk")

        response = client.delete(f"/tasks/{created['id']}/")

        assert response.status_code == 401
        assert (
            client.get(f"/tasks/{created['id']}/", headers=auth_headers).status_code
            == 200
        )
