"""Local deployed UI regression. Never prints credentials or page contents."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    values = {}
    for line in (Path(__file__).resolve().parents[2] / '.env.public').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto('http://localhost:8080')
            page.locator('input[autocomplete="username"]').fill(values['DEMO_AUTH_USERNAME'])
            page.locator('input[type="password"]').fill(values['DEMO_AUTH_PASSWORD'])
            page.get_by_role('button', name='로그인', exact=True).click()
            page.get_by_role('button', name='AI 시나리오', exact=True).click()
            url = page.locator('.page-first-input input')
            expect(url).to_have_value('')
            url.fill('https://not-allowed.example')
            page.get_by_role('button', name='페이지 분석 시작', exact=True).click()
            expect(page.get_by_role('status')).to_contain_text('허용', timeout=15000)
            page.wait_for_timeout(2500)
            expect(page.get_by_role('status')).to_be_visible()
            url.fill('http://demo-target')
            page.get_by_role('button', name='페이지 분석 시작', exact=True).click()
            expect(page.get_by_role('button', name='기본 시나리오 생성', exact=True)).to_be_visible(timeout=45000)
            print('UI PASS: empty start URL, persistent validation error, completed discovery panel')
            page.get_by_role('button', name='테스트 케이스').click()
            page.get_by_role('button', name='새 테스트 케이스', exact=True).click()
            page.locator('.author-page .tc-editor').fill('http://demo-target 접속\n로그인 버튼 클릭\n기대결과: 로그인 표시 확인')
            page.get_by_role('button', name='선택한 TC 구조화').click()
            button = page.get_by_role('button', name='페이지 분석 시작', exact=True)
            expect(button).to_be_enabled(timeout=15000)
            button.click()
            expect(page.locator('.discovery-panel')).to_be_visible(timeout=15000)
            expect(page.get_by_role('button', name='분석 결과 적용', exact=True)).to_be_visible(timeout=45000)
            print('UI PASS: TC structure review discovery panel and results')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
