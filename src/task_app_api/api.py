from flask import Flask

app = Flask(__name__)


@app.get('/tasks/')
def list_tasks():
    raise NotImplementedError()


@app.post('/tasks/')
def create_task():
    raise NotImplementedError()


@app.get('/tasks/<uuid:task_id>/')
def get_task(task_id):
    raise NotImplementedError()


@app.put('/tasks/<uuid:task_id>/')
def update_task(task_id):
    raise NotImplementedError()
