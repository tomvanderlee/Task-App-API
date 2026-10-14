import pytest

from task_app_api.api import app
from task_app_api.exceptions import (
    AppError,
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
)


class TestAppErrors:
    @pytest.mark.parametrize(
        ("error", "status", "detail"),
        [
            (BadRequestError, 400, "Bad request"),
            (UnauthorizedError, 401, "Invalid token"),
            (NotFoundError, 404, "Not found"),
            (AppError, 500, "Internal server error"),
        ],
    )
    def test_defaults(self, error, status, detail):
        assert error().status_code == status
        assert error().detail == detail

    def test_custom_detail_overrides_default(self):
        assert NotFoundError("Task not found").detail == "Task not found"


class TestHandlers:
    def test_app_error_becomes_json_response(self, client, auth_headers, monkeypatch):
        def boom():
            raise NotFoundError("Nope")

        monkeypatch.setitem(app.view_functions, "list_tasks", boom)

        response = client.get("/tasks/", headers=auth_headers)

        assert response.status_code == 404
        assert response.json == {"detail": "Nope"}

    def test_unknown_route_returns_json_404(self, client):
        response = client.get("/nope/")

        assert response.status_code == 404
        assert "detail" in response.json

    def test_wrong_method_returns_json_405(self, client):
        response = client.patch("/tasks/")

        assert response.status_code == 405
        assert "detail" in response.json

    def test_unexpected_error_returns_generic_500(
        self, client, auth_headers, monkeypatch, caplog
    ):
        def boom():
            raise RuntimeError("secret internals")

        monkeypatch.setitem(app.view_functions, "list_tasks", boom)

        response = client.get("/tasks/", headers=auth_headers)

        assert response.status_code == 500
        assert response.json == {"detail": "Internal server error"}
        assert "secret internals" not in response.get_data(as_text=True)
        assert "secret internals" in caplog.text
