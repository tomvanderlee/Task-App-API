# Task App API

A small task API built with Flask and SQLModel. The endpoints are described in
[`docs/openapi.yaml`](docs/openapi.yaml).

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## Setup

```sh
# Install dependencies
uv sync

# Create your local configuration
cp .env.example .env

# Create the database tables
uv run alembic upgrade head
```

Configuration lives in `.env`:

| Variable       | Description                                          | Default in `.env.example` |
|----------------|------------------------------------------------------|---------------------------|
| `DATABASE_URL` | SQLAlchemy database url                              | `sqlite:///db.sqlite`     |
| `JWKS_FILE`    | JWKS file used to verify tokens (see below)          | `.jwt/jwks.json`          |
| `PAGE_SIZE`    | Number of tasks per page when listing tasks          | `20`                      |

## Run

```sh
uv run flask --app task_app_api.api run --port 8000 --debug
```

The API is now available at <http://localhost:8000>.

## Authentication

Requests need an `Authorization: Bearer <token>` header with a JWT that has a `username` claim. Users are
created automatically the first time their token is used.

Real token verification is not set up yet. Instead, a script generates a signing key and the matching JWKS
file (in `.jwt/`, which is not committed) and creates tokens for you:

```sh
uv run python scripts/generate_jwt.py <username>

# Optional: change the lifetime (in seconds, default is 3600)
uv run python scripts/generate_jwt.py <username> --expires-in 86400
```

Try it:

```sh
TOKEN=$(uv run python scripts/generate_jwt.py tom)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/tasks/
```

If you delete `.jwt/` and generate new keys, restart the server.

## Example requests

`requests.http` contains ready-to-run requests (JetBrains HTTP client format, also works with
other tools that support it). Copy `http-client.env.json` to `http-client.private.env.json` and put your jwt token in.

```json
{
  "local": {
    "token": "<output of scripts/generate_jwt.py>"
  }
}
```

## Tests

```sh
uv run pytest
```

This also prints a coverage report and writes a `.coverage` file.

## Development

Formatting and linting run with [pre-commit](https://pre-commit.com/) and ruff:

```sh
uv run pre-commit install
```

After changing the models, create a migration with:

```sh
uv run alembic revision --autogenerate -m "Describe the change"
uv run alembic upgrade head
```
