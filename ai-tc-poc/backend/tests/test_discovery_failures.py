import pytest
from playwright.async_api import Error, TimeoutError
from app.core.errors import DomainError
from app.modules.discoveries.target import discovery_target, discovery_error
from app.modules.ai.service import rule_based_structure
from app.schemas.test_cases import StructureRequest
from app.workers import playwright_worker


@pytest.mark.parametrize('raw,code', [('', 'TARGET_URL_REQUIRED'),
    ('https://evil.test', 'TARGET_URL_NOT_ALLOWED'),
    ('https://example.test https://other.test', 'TARGET_URL_AMBIGUOUS')])
def test_target_never_falls_back_to_demo(raw, code):
    with pytest.raises(DomainError) as error:
        discovery_target(raw, ['example.test'])
    assert error.value.code == code


def test_target_and_fingerprint_dependency():
    assert discovery_target('https://example.test/path 접속', ['example.test']) == 'https://example.test/path'
    assert len(playwright_worker.hashlib.sha256(b'synthetic').hexdigest()) == 64


@pytest.mark.parametrize('exc,code', [(TimeoutError('secret'), 'DISCOVERY_TIMEOUT'),
    (Error('secret'), 'DISCOVERY_BROWSER_ERROR'), (NameError('secret'), 'DISCOVERY_INTERNAL_ERROR')])
def test_safe_error_classification(exc, code):
    actual, message = discovery_error(exc)
    assert actual == code and 'secret' not in message


def test_metadata_and_expected_navigation_are_not_actions():
    result = rule_based_structure(StructureRequest(title='synthetic', rawText=
        'TC ID: KG-WEB-001\n제목: 페이지 접속\n전제조건: 준비\n1. https://example.test 접속\n2\n기대 결과: 페이지로 이동되어야 한다'))
    assert [s.action for s in result.steps] == ['navigate', 'assert']
    assert len(result.preconditions) == 3


def test_metadata_only_is_rejected():
    with pytest.raises(DomainError):
        rule_based_structure(StructureRequest(title='synthetic', rawText='TC ID: KG-WEB-001\n전제조건: 준비'))


def test_connection_error_is_sanitized():
    code, message = discovery_error(Error('net::ERR_NAME_NOT_RESOLVED https://secret.invalid/?token=secret'))
    assert code == 'DISCOVERY_CONNECTION_FAILED' and 'secret' not in message


def test_missing_navigation_url_cannot_use_environment_default():
    from types import SimpleNamespace
    from app.modules.test_cases.execution_plan import validate_execution_plan, ExecutionPlanError
    version = SimpleNamespace(structured_spec={'steps': [{'id': 's', 'action': 'navigate'}]})
    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan(version, SimpleNamespace(base_url='http://demo-target'))
    assert error.value.code == 'TARGET_URL_REQUIRED'


def test_import_wrappers_wait_and_duplicate_navigation():
    from app.modules.ai.service import enforce_selector_grounding
    raw = '단계 1: 1.\n단계 2: 2.\n대상 URL: https://example.test\n단계 3: https://example.test 접속\n단계 4: 로딩 완료 대기\n기대결과: 메뉴 표시 확인'
    result = enforce_selector_grounding(rule_based_structure(StructureRequest(title='synthetic', rawText=raw)), raw)
    assert [s.action for s in result.steps] == ['navigate', 'wait', 'assert']
    assert result.steps[1].selector is None
    assert result.steps[1].operator == 'domcontentloaded'
    assert result.automationStatus == 'MANUAL_REVIEW_REQUIRED'


def test_duplicate_navigation_is_removed_even_when_separated():
    raw = '단계 1: https://kakaogames.com/ 접속\n단계 2: 로딩 완료 대기\n단계 3: 기대결과: 메인 표시 확인\n대상 URL: https://kakaogames.com/'
    result = rule_based_structure(StructureRequest(title='synthetic', rawText=raw))
    assert [step.action for step in result.steps].count('navigate') == 1


@pytest.mark.asyncio
async def test_wait_does_not_require_selector():
    from app.workers.step_executor import execute_step
    class Page:
        async def wait_for_load_state(self, state, timeout):
            assert state == 'domcontentloaded' and timeout == 10000
    result = await execute_step(Page(), {'action': 'wait', 'operator': 'domcontentloaded'}, 'https://example.test')
    assert result.action['state'] == 'domcontentloaded'
