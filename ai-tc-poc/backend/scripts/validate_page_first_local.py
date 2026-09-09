"""Synthetic local staging smoke. Credentials are read locally, never printed."""
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    values = {}
    for line in (Path(__file__).resolve().parents[2] / '.env.public').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    # Fixed loopback URL: never send local credentials to a supplied remote host.
    with httpx.Client(base_url='http://127.0.0.1:8080', timeout=30) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/v1/environments').status_code == 401
        login = client.post('/api/v1/auth/login', json={
            'username': values['DEMO_AUTH_USERNAME'], 'password': values['DEMO_AUTH_PASSWORD']})
        assert login.status_code == 200, 'Local demo login failed'
        # Secure production cookies remain unchanged; loopback smoke sends them explicitly.
        client.headers['Cookie'] = '; '.join(f'{c.name}={c.value}' for c in client.cookies.jar)

        def api(method, path, body=None, expected=200):
            response = client.request(method, '/api/v1' + path, json=body,
                headers={'Idempotency-Key': str(uuid4())} if path == '/executions' else {})
            if response.status_code != expected:
                code = response.json().get('code', 'unknown')
                raise RuntimeError(f'{method} {path}: HTTP {response.status_code}, {code}')
            return response.json()

        policy = api('GET', '/execution-policies/current')
        limits = policy.get('limits', policy)
        assert limits['maxAiCalls'] == 0, 'Smoke requires AI disabled'
        environments = api('GET', '/environments')
        env = next(e for e in environments if e['baseUrl'].startswith('http://demo-target'))
        accounts = api('GET', '/test-accounts')
        discovery = api('POST', '/page-discoveries', {'environmentId': env['id'],
            'startUrl': env['baseUrl'], 'maxPages': 1, 'maxAiCalls': 0}, 202)
        for _ in range(45):
            found = api('GET', '/page-discoveries/' + discovery['discoveryId'])
            if found['status'] in ('COMPLETED', 'FAILED'):
                break
            time.sleep(1)
        assert found['status'] == 'COMPLETED', found.get('errorCode')
        scenario = api('POST', '/page-discoveries/' + discovery['discoveryId'] + '/scenarios', {'maxAiCalls': 0}, 201)
        path = '/page-scenarios/' + scenario['scenarioId']
        scenario = api('PATCH', path + '/review', {'expectedRevision': scenario['revision'],
            'selections': [{'comparisonId': row['id'], 'decision': 'ADD'} for row in scenario['comparisons']]})
        approved = api('POST', path + '/approve', {'expectedRevision': scenario['revision']})
        repeated = api('POST', path + '/approve', {'expectedRevision': scenario['revision']})
        assert repeated['versionId'] == approved['versionId']
        plan = api('GET', '/test-case-versions/' + approved['versionId'] + '/execution-plan?environmentId=' + env['id'])
        assert plan['executable']
        execution = api('POST', '/executions', {'testCaseVersionId': approved['versionId'],
            'environmentId': env['id'], 'accountId': accounts[0]['id'], 'browser': 'Chromium',
            'viewport': '1280x720', 'locale': 'en-US', 'limits': {'timeoutMinutes': 5,
                'maxAiCalls': 0, 'retryCount': 0}, 'requireRiskApproval': True}, 202)
        for _ in range(45):
            result = api('GET', '/executions/' + execution['id'])
            if result['status'] in ('PASS', 'FAIL', 'SYSTEM_ERROR', 'BLOCKED', 'NEEDS_REVIEW', 'CANCELLED'):
                break
            time.sleep(1)
        details = api('GET', '/executions/' + execution['id'] + '/details')
        print(json.dumps({'discovery': found['status'], 'scenario': approved['status'],
            'executionId': execution['id'], 'execution': result['status'],
            'errorCode': details.get('errorCode'), 'steps': len(details['steps']), 'aiCalls': 0}))
        assert result['status'] == 'PASS', 'Worker execution did not pass'
        failed_case = api('POST', '/test-case-versions/current/structure', {
            'title': 'Synthetic artifact smoke',
            'rawText': 'http://demo-target 접속\n[data-testid="email"]에 "qa@example.test" 입력\n[data-testid="login"] 클릭\n[data-testid="welcome"] 문구 "deliberately absent synthetic text" 확인'})
        assert failed_case['aiUsage']['callCount'] == 0
        api('POST', '/test-case-versions/' + failed_case['versionId'] + '/approve')
        failed_run = api('POST', '/executions', {'testCaseVersionId': failed_case['versionId'],
            'environmentId': env['id'], 'accountId': accounts[0]['id'], 'browser': 'Chromium',
            'viewport': '1280x720', 'locale': 'en-US', 'limits': {'timeoutMinutes': 5,
                'maxAiCalls': 0, 'retryCount': 0}, 'requireRiskApproval': True}, 202)
        for _ in range(45):
            failure = api('GET', '/executions/' + failed_run['id'])
            if failure['status'] in ('PASS', 'FAIL', 'SYSTEM_ERROR', 'BLOCKED', 'NEEDS_REVIEW', 'CANCELLED'):
                break
            time.sleep(1)
        assert failure['status'] == 'FAIL', 'Expected intentional assertion failure'
        failure_details = api('GET', '/executions/' + failed_run['id'] + '/details')
        artifact = failure_details['artifacts'][0]
        png = client.get('/api/v1/executions/' + failed_run['id'] + '/artifacts/' + artifact['id'])
        assert png.status_code == 200 and png.content.startswith(b'\x89PNG\r\n\x1a\n')
        print(json.dumps({'intentionalFailure': failure['status'], 'executionId': failed_run['id'],
            'artifactDownload': png.status_code, 'pngValid': True, 'aiCalls': 0}))


if __name__ == '__main__':
    main()
