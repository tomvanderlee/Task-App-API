class AppError(Exception):
    status_code = 500
    detail = "Internal server error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.detail
        super().__init__(self.detail)


class BadRequestError(AppError):
    status_code = 400
    detail = "Bad request"


class UnauthorizedError(AppError):
    status_code = 401
    detail = "Invalid token"


class NotFoundError(AppError):
    status_code = 404
    detail = "Not found"
