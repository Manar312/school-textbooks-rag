class ConfigError(Exception):
    """Misconfigured provider / environment. Raised at startup so problems surface immediately."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class Unauthorized(AppError):
    status_code, code = 401, "unauthorized"


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class QuotaExceeded(AppError):
    status_code, code = 429, "quota_exceeded"


class RateLimited(AppError):
    status_code, code = 429, "rate_limited"


class InvalidUpload(AppError):
    status_code, code = 422, "invalid_upload"
