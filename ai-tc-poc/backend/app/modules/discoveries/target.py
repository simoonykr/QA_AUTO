"""Fail-closed target selection and sanitized discovery failures."""
import re
from playwright.async_api import Error, TimeoutError
from app.core.errors import DomainError
from app.modules.discoveries.page_first import allowed_url


def discovery_target(raw_text, allowed_domains):
    urls = list(dict.fromkeys(url.rstrip('.,)') for url in re.findall(r'https?://[^\s<>"\']+', raw_text or '')))
    if not urls:
        raise DomainError('TARGET_URL_REQUIRED', 'TC 대상 URL을 명시하거나 페이지 우선 분석에서 시작 URL을 입력해 주세요.', 422)
    if len(urls) != 1:
        raise DomainError('TARGET_URL_AMBIGUOUS', '대상 URL이 여러 개입니다. 페이지 우선 분석에서 시작 URL을 지정해 주세요.', 422)
    if not allowed_url(urls[0], allowed_domains):
        raise DomainError('TARGET_URL_NOT_ALLOWED', 'TC URL과 실행 환경의 허용 도메인을 확인해 주세요.', 422)
    return urls[0]


def discovery_error(exc):
    if isinstance(exc, DomainError):
        return exc.code, exc.message
    if isinstance(exc, TimeoutError):
        return 'DISCOVERY_TIMEOUT', '페이지 접속 또는 요소 검증 시간이 초과됐습니다. 대상 상태를 확인하고 재분석해 주세요.'
    if getattr(exc, 'code', '') == 'DOMAIN_NOT_ALLOWED':
        return 'TARGET_URL_NOT_ALLOWED', '허용되지 않은 도메인으로 이동하여 분석을 차단했습니다.'
    if isinstance(exc, Error):
        if 'net::ERR_' in str(exc):
            return 'DISCOVERY_CONNECTION_FAILED', '대상 페이지 연결에 실패했습니다. URL, DNS, 인증서와 네트워크 상태를 확인해 주세요.'
        return 'DISCOVERY_BROWSER_ERROR', '브라우저 접속 또는 요소 수집에 실패했습니다. 대상 URL과 연결 상태를 확인해 주세요.'
    return 'DISCOVERY_INTERNAL_ERROR', '분석 처리 중 서버 오류가 발생했습니다. 분석 ID로 관리자에게 확인을 요청해 주세요.'
