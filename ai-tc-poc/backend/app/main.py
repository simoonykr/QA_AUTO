from uuid import UUID, uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.core.errors import DomainError, domain_error_handler, unexpected_error_handler, validation_error_handler
from app.modules.executions.router import router as execution_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import COOKIE_NAME, validate_demo_auth_config, verify_session
from app.modules.resources.router import router as resource_router
from app.modules.test_cases.router import router as test_case_router, version_router


settings = get_settings()
validate_demo_auth_config(settings)
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)


@app.middleware("http")
async def request_context(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID")
    try:
        request.state.request_id = str(UUID(supplied_request_id)) if supplied_request_id else str(uuid4())
    except ValueError:
        request.state.request_id = str(uuid4())
    if (
        settings.demo_auth_enabled
        and request.url.path.startswith("/api/v1/")
        and not request.url.path.startswith("/api/v1/auth/")
        and not verify_session(request.cookies.get(COOKIE_NAME), settings)
    ):
        return JSONResponse(
            status_code=401,
            headers={"X-Request-ID": request.state.request_id},
            content={
                "code": "AUTH_REQUIRED",
                "message": "로그인이 필요합니다.",
                "requestId": request.state.request_id,
                "retryable": False,
                "details": {},
            },
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


app.include_router(test_case_router, prefix="/api/v1")
app.include_router(version_router, prefix="/api/v1")
app.include_router(execution_router, prefix="/api/v1")
app.include_router(resource_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
