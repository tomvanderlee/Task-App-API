import logging

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from task_app_api.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(detail=error.detail), error.status_code

    # We need to explicitly handle HTTPExceptions as we already catch their super class (Exception).
    # Not doing this would result in a NotFound being interpreted an InternalServerError
    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        return jsonify(detail=error.description), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("Unhandled exception")
        return jsonify(detail="Internal server error"), 500
