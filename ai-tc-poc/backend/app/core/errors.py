from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, *, retryable: bool = False, details: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(status_code=exc.status_code, content={
        "code": exc.code, "message": exc.message, "requestId": request_id,
        "retryable": exc.retryable, "details": exc.details,
    })
