from flask import Flask, g, jsonify, request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from task_app_api import auth
from task_app_api.db import get_session
from task_app_api.models import Task, TaskInput, User

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


@app.get("/tasks/")
def list_tasks():
    raise NotImplementedError()


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


@app.get("/tasks/<uuid:task_id>/")
def get_task(task_id):
    raise NotImplementedError()


@app.put("/tasks/<uuid:task_id>/")
def update_task(task_id):
    raise NotImplementedError()
