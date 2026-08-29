from fastapi import APIRouter, Request, Response

from app.core.config import get_settings
from app.core.errors import DomainError
from app.modules.auth.service import COOKIE_NAME, create_session, credentials_match, verify_session
from app.schemas.auth import AuthenticatedUser, DemoLoginRequest, LoginResponse


router = APIRouter(prefix="/auth", tags=["auth"])


def _user(username: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=f"demo:{username}",
        displayName=username,
        role="OWNER",
        approvalStatus="APPROVED",
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: DemoLoginRequest, response: Response) -> LoginResponse:
    settings = get_settings()
    if not settings.demo_auth_enabled:
        raise DomainError("AUTH_NOT_ENABLED", "데모 로그인이 활성화되지 않았습니다.", 404)
    if not credentials_match(body.username, body.password, settings):
        raise DomainError("INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.", 401)
    token, ttl_seconds = create_session(settings)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=ttl_seconds,
        httponly=True,
        secure=settings.demo_cookie_secure,
        samesite="lax",
        path="/",
    )
    return LoginResponse(user=_user(body.username), expiresIn=ttl_seconds)


@router.get("/me", response_model=AuthenticatedUser)
async def me(request: Request) -> AuthenticatedUser:
    settings = get_settings()
    payload = verify_session(request.cookies.get(COOKIE_NAME), settings)
    if not payload:
        raise DomainError("AUTH_REQUIRED", "로그인이 필요합니다.", 401)
    return _user(payload["sub"])


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
