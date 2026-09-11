"""Local deployed UI regression. Never prints credentials or page contents."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    values = dict(os.environ)
    parents = Path(__file__).resolve().parents
    env_file = parents[2] / '.env.public' if len(parents) > 2 else None
    if env_file and env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(os.getenv('DISCOVERY_UI_BASE_URL', 'http://localhost:8080'))
            page.locator('input[autocomplete="username"]').fill(values['DEMO_AUTH_USERNAME'])
            page.locator('input[type="password"]').fill(values['DEMO_AUTH_PASSWORD'])
            page.get_by_role('button', name='로그인', exact=True).click()
            scenario_nav = page.get_by_role('button', name='AI 시나리오', exact=True)
            expect(scenario_nav).to_be_visible(timeout=15000)
            page.wait_for_timeout(2000)
            scenario_nav.click()
            assert page.evaluate('document.documentElement.scrollWidth') <= 1280
            url = page.locator('.page-first-input input')
            expect(url).to_have_value('')
            url.fill('https://not-allowed.example')
            page.get_by_role('button', name='페이지 분석 시작', exact=True).click()
            error_card = page.locator('.persistent-error')
            expect(error_card).to_contain_text('허용', timeout=45000)
            page.wait_for_timeout(2500)
            expect(error_card).to_be_visible()
            target_url = os.getenv('DISCOVERY_UI_TARGET_URL', 'http://demo-target')
            url.fill(target_url)
            page.get_by_role('button', name='페이지 분석 시작', exact=True).click()
            expect(page.get_by_role('button', name='기본 시나리오 생성', exact=True)).to_be_visible(timeout=45000)
            print('UI PASS: empty start URL, persistent validation error, completed discovery panel')
            page.get_by_role('button', name='테스트 케이스').click()
            page.get_by_role('button', name='새 테스트 케이스', exact=True).click()
            page.locator('.author-page .tc-editor').fill(
                f'단계 1: {target_url} 접속\n'
                '단계 2: 로딩 완료 대기\n'
                '단계 3: 기대결과: 메인 표시 확인\n'
                f'대상 URL: {target_url}'
            )
            page.get_by_role('button', name='선택한 TC 구조화').click()
            expect(page.locator('.structured-step small').filter(has_text='NAVIGATE')).to_have_count(1, timeout=15000)
            expect(page.locator('.structured-step small').filter(has_text='WAIT')).to_contain_text('문서 로딩 완료 대기')
            assert page.evaluate('document.documentElement.scrollWidth') <= 1280
            button = page.get_by_role('button', name='페이지 분석 시작', exact=True)
            expect(button).to_be_enabled(timeout=15000)
            button.click()
            expect(page.locator('.discovery-panel')).to_be_visible(timeout=15000)
            expect(page.get_by_role('button', name='분석 결과 적용', exact=True)).to_be_visible(timeout=45000)
            print('UI PASS: deduplicated NAVIGATE, WAIT label, TC discovery, 1280px layout')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
