import os

from flask import Flask, g, jsonify, request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from task_app_api import auth
from task_app_api.db import get_session
from task_app_api.models import Task, TaskInput, TaskStatus, User

app = Flask(__name__)
app.before_request(auth.authenticate)


def get_or_create_user(session, username: str) -> User:
    query = select(User).where(User.username == username)
    user = session.exec(query).first()
    if user is None:
        user = User(username=username)
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            user = session.exec(query).one()
        session.refresh(user)
    return user


PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "20"))
SORT_FIELDS = {"title": Task.title, "created_date": Task.created_date}


@app.get("/tasks/")
def list_tasks():
    page = request.args.get("page", "1")
    if not page.isdecimal() or int(page) < 1:
        return jsonify(detail="page must be an integer of at least 1"), 400

    page = int(page)

    sort = request.args.get("sort", "created_date")
    if sort not in SORT_FIELDS:
        return jsonify(detail=f"sort must be one of: {', '.join(SORT_FIELDS)}"), 400

    try:
        status = TaskStatus(s) if (s := request.args.get("status")) else None
    except ValueError:
        statuses = ", ".join(TaskStatus)
        return jsonify(detail=f"status must be one of: {statuses}"), 400

    with get_session() as session:
        user = get_or_create_user(session, g.username)

        query = select(Task).where(Task.owner_id == user.id)
        if q := request.args.get("q"):
            query = query.where(
                Task.title.icontains(q, autoescape=True)
            )  # Ideally this would be a fuzzy search, but left out for time sake
        if status:
            query = query.where(Task.status == status)

        query = (
            query.order_by(SORT_FIELDS[sort], Task.id)
            .offset((page - 1) * PAGE_SIZE)
            .limit(
                PAGE_SIZE + 1
            )  # Fetch one extra row so we can check if there is a next page
        )
        tasks = session.exec(query).all()

        return jsonify(
            next=page + 1 if len(tasks) > PAGE_SIZE else None,
            prev=page - 1 if page > 1 else None,
            items=[task.model_dump(mode="json") for task in tasks[:PAGE_SIZE]],
        )


@app.post("/tasks/")
def create_task():
    try:
        data = TaskInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(detail=str(e)), 400

    with get_session() as session:
        user = get_or_create_user(session, g.username)

        task = Task.model_validate(data, update={"owner_id": user.id})
        session.add(task)
        session.commit()
        session.refresh(task)
        return jsonify(task.model_dump(mode="json")), 201


def get_owned_task(session, task_id, username: str) -> Task | None:
    """Tasks of other users are treated as if they do not exist"""
    user = get_or_create_user(session, username)
    task = session.get(Task, task_id)
    return task if task and task.owner_id == user.id else None


@app.get("/tasks/<uuid:task_id>/")
def get_task(task_id):
    with get_session() as session:
        task = get_owned_task(session, task_id, g.username)
        if task is None:
            return jsonify(detail="Task not found"), 404
        return jsonify(task.model_dump(mode="json"))


@app.put("/tasks/<uuid:task_id>/")
def update_task(task_id):
    try:
        data = TaskInput.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(detail=str(e)), 400

    with get_session() as session:
        task = get_owned_task(session, task_id, g.username)
        if task is None:
            return jsonify(detail="Task not found"), 404

        task.sqlmodel_update(data)
        session.add(task)
        session.commit()
        session.refresh(task)
        return jsonify(task.model_dump(mode="json"))


@app.delete("/tasks/<uuid:task_id>/")
def delete_task(task_id):
    with get_session() as session:
        task = get_owned_task(session, task_id, g.username)
        if task is None:
            return jsonify(detail="Task not found"), 404

        session.delete(task)
        session.commit()
        return "", 204
