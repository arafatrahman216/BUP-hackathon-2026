"""Application exceptions.

Raise these from services; the global error handler turns them into the standard
JSON error shape. Add a subclass when you need a new status/code pair.
"""

from typing import Any


class AppException(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    default_message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(self.message)


class BadRequestError(AppException):
    pass


class UnauthorizedError(AppException):
    status_code = 401
    code = "UNAUTHORIZED"
    default_message = "Authentication required"


class ForbiddenError(AppException):
    status_code = 403
    code = "FORBIDDEN"
    default_message = "You do not have permission to do this"


class NotFoundError(AppException):
    status_code = 404
    code = "NOT_FOUND"
    default_message = "Resource not found"


class ConflictError(AppException):
    status_code = 409
    code = "CONFLICT"
    default_message = "Resource already exists"


class ExternalServiceError(AppException):
    status_code = 502
    code = "EXTERNAL_SERVICE_ERROR"
    default_message = "An external service failed"


class ServiceUnavailableError(AppException):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    default_message = "Service is not available"
