from uuid import uuid4
from fastapi import Request
from fastapi.exceptions import RequestValidationError
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


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(status_code=422, content={
        "code": "VALIDATION_ERROR",
        "message": "요청 값이 올바르지 않습니다.",
        "requestId": request_id,
        "retryable": False,
        "details": {"errors": exc.errors()},
    })


async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(status_code=500, content={
        "code": "INTERNAL_SERVER_ERROR",
        "message": "서버에서 요청을 처리하지 못했습니다.",
        "requestId": request_id,
        "retryable": True,
        "details": {},
    })
