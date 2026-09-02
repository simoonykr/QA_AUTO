# 로컬 Playwright 통합 검증 결과

검증일: 2026-09-01  
기준 브랜치: `main` (`0c31329` 기준 검증 시작)

## 결론

Docker Compose의 프론트, API, PostgreSQL, Redis, MinIO, Outbox Publisher, Playwright Worker, demo-target를 함께 실행했다. Chromium이 성공 TC의 `navigate → fill → click → assert` 4단계를 실제 수행해 최종 `PASS`가 됐고, assertion 기대값만 틀린 실패 TC는 최종 `FAIL`과 PNG 증적을 생성했다.

두 실행 모두 요청과 DB 저장값이 `maxAiCalls=0`이었다. API·Outbox·Worker 로그에서 OpenAI API 키, 데모 비밀번호, 세션 서명 키의 실제 값은 발견되지 않았으며 OpenAI API 네트워크 호출 표식도 없었다. 관찰된 AI 호출과 비용은 각각 `0회`, `$0`이다.

## 실행 명령

로컬 비밀값은 Git에서 제외된 `.env.public` 또는 현재 프로세스 환경변수로만 주입했다.

```powershell
docker compose --env-file .env.public -f compose.public-demo.yml up --build -d
docker compose --env-file .env.public -f compose.public-demo.yml ps
docker compose --env-file .env.public -f compose.public-demo.yml build migrate
docker compose --env-file .env.public -f compose.public-demo.yml run --rm migrate
```

API 검증 순서:

1. `POST /api/v1/auth/login`
2. 성공 버전 `00000000-0000-0000-0000-000000000501`로 `POST /api/v1/executions`
3. 종료까지 `GET /api/v1/executions/{executionId}` polling
4. `GET /api/v1/executions/{executionId}/details`
5. 실패 버전 `00000000-0000-0000-0000-000000000502`로 동일 실행
6. `GET /api/v1/executions/{executionId}/artifacts/{artifactId}`로 PNG 다운로드

공통 실행 설정:

```json
{
  "browser": "Chromium",
  "viewport": "1440x900",
  "locale": "ko-KR",
  "limits": {
    "timeoutMinutes": 5,
    "maxAiCalls": 0,
    "retryCount": 0
  }
}
```

## 서비스 상태

| 서비스 | 결과 |
|---|---|
| frontend | Up, healthy |
| api | Up, `/health` 200 (`public-demo`) |
| PostgreSQL | Up, healthy |
| Redis | Up, healthy |
| MinIO | Up |
| Outbox Publisher | Up |
| Playwright Worker | Up |
| demo-target | Up, healthy |
| migrate | `0005_seed_worker_failure`, 정상 종료 |

## 성공 TC 결과

- Execution ID: `201c45fc-c846-4cce-b847-1a9fd01c3202`
- 최종 상태: `PASS`
- 실행 오류 코드: 없음
- DB `maxAiCalls`: `0`

| 단계 | action | 상태 | 오류 코드 |
|---:|---|---|---|
| 1 | navigate | PASS | 없음 |
| 2 | fill | PASS | 없음 |
| 3 | click | PASS | 없음 |
| 4 | assert | PASS | 없음 |

`fill` 단계의 저장 action은 실제 입력값 대신 `***`로 마스킹되는 것도 확인했다.

## 실패 TC 결과

재현 가능한 실패 데이터는 migration `0005_seed_worker_failure`로 추가했다. 성공 TC와 같은 동작을 수행하되 마지막 assertion의 기대 문구만 의도적으로 존재하지 않는 값으로 지정한다.

- Execution ID: `0a5c5cf4-2179-464e-8504-7df5cb78084c`
- 최종 상태: `FAIL`
- 실행 오류 코드: `ASSERTION_FAILED`
- 실패 단계: 4번 `assert`
- 단계 오류 코드: `STEP_FAILED`
- DB `maxAiCalls`: `0`

| 단계 | action | 상태 | 오류 코드 |
|---:|---|---|---|
| 1 | navigate | PASS | 없음 |
| 2 | fill | PASS | 없음 |
| 3 | click | PASS | 없음 |
| 4 | assert | FAIL | `STEP_FAILED` |

증적:

- Artifact ID: `8c980f7a-d1e9-4b83-a569-40ba6f6e4ad6`
- 종류: `FAILURE_SCREENSHOT`
- 크기: `19,569 bytes`
- PNG signature: `89504E470D0A1A0A`
- 실행 상세 endpoint에서 단계와 증적 목록 조회 성공
- 증적 다운로드 endpoint에서 HTTP 응답 본문을 내려받아 PNG signature 확인 성공

프론트 담당자는 위 실패 Execution ID의 상세 endpoint와 Artifact ID의 다운로드 endpoint를 사용해 실행 상세·스크린샷 화면을 교차 검증할 수 있다. 로컬 재구축 시 ID가 새로 생성되므로 고정 실패 버전 ID `...0502`로 다시 실행해 새 Execution ID를 사용한다.

## 비밀값·AI 사용 확인

- API·Outbox Publisher·Playwright Worker 로그에서 OpenAI API 키 실제 값: 미검출
- 데모 비밀번호 실제 값: 미검출
- 세션 서명 키 실제 값: 미검출
- `api.openai.com`, Responses/Chat Completions 호출 표식: 미검출
- 요청 및 DB의 `maxAiCalls`: `0`
- 관찰된 AI API 호출: `0회`
- 관찰된 AI 비용: `$0`

현재 OpenAI Gateway와 비용 원장이 아직 구현되지 않았기 때문에 이번 검증은 Playwright 결정적 실행만 수행했다.

## 자동 테스트

API 이미지에 개발 의존성을 설치한 일회성 컨테이너에서 실행했다.

```powershell
docker run --rm -v <backend>:/workspace -w /workspace ai-tc-poc-api `
  sh -lc "pip install --no-cache-dir '.[dev]' && pytest -q"
```

결과: `27 passed, 3 warnings` (`0.93s`). 경고는 Starlette/httpx deprecation 1건과 Pydantic schema 클래스 pytest collection 경고 2건이다.

## 발견된 문제와 조치

### Docker Desktop 4.88.1 시작 실패

Windows AF_UNIX 런타임 소켓을 제거하지 못해 `sailor-ingest.sock`과 `docker-secrets-engine/engine.sock`에서 Docker backend가 종료됐다. Docker 이미지·볼륨을 초기화하지 않고 프로세스와 WSL을 종료한 뒤 두 부모 런타임 폴더를 삭제 대신 백업 이동해 복구했다.

생성된 로컬 백업:

- `%LOCALAPPDATA%\Docker\run-stale-20260901-*`
- `%LOCALAPPDATA%\docker-secrets-engine-stale-20260901-*`

Docker Desktop이 안정적으로 재시작되는 것을 추가 확인한 뒤 오래된 백업을 정리할 수 있다. 이 현상은 Docker Desktop의 알려진 Windows AF_UNIX socket 오류와 동일한 형태다.

### 로컬 비밀파일

OneDrive 이동 직후 기존 `.env.public`이 사라져 일부 필수 비밀값이 빈칸이 됐다. 이번 검증은 보존된 컨테이너 설정과 실행 프로세스의 임시 값으로 완료했다. 다음 Compose 재생성 전 `.env.public`의 DB·MinIO·데모 인증·세션 값을 로컬에서 다시 채워야 한다. 파일은 계속 Git 제외 상태다.

### Secure 쿠키

`APP_ENV=public-demo`에서는 `DEMO_COOKIE_SECURE=true`가 강제된다. 로컬 HTTP API 검증은 로그인 응답의 Secure HttpOnly 쿠키를 테스트 요청에 명시적으로 전달했다. 실제 외부 공개는 HTTPS를 사용해야 한다.

## 영속 구조화 버전 통합 검증 (2026-09-02)

Temporary Staging HTTPS에서 AI 호출을 비활성화한 상태로 새 TC를 구조화했다. 응답 UUID `787dc8b2-cecf-4ae4-b438-9786a7a65e2f`가 `REVIEW_REQUIRED`로 저장됐고, 승인 전 실행 생성은 HTTP 409 `TC_NOT_READY`로 차단됐다. 승인 API 호출 후 같은 UUID가 `READY`가 됐다.

이 UUID로 생성한 Execution `f322af6c-c3f5-4b93-99ee-8fd0f5d6a24b`를 Outbox Publisher와 Playwright Worker가 처리했다. Worker는 DB `structured_spec`의 `navigate → fill → click → assert` 네 단계를 조회해 모두 `PASS`로 기록했고 최종 실행도 `PASS`였다. 구조화 응답은 `RULE_BASED`, `callCount=0`으로 실제 AI 호출과 비용은 없었다.

## 실행 계획 hash·실제 단계 일치 검증 (2026-09-02)

Version `5ea8101f-8ca9-4e19-ab83-d7fa5b3adc38`의 실행 계획을 조회해 64자 SHA-256 hash, revision 1, 네 단계와 `fill.value=***` 마스킹을 확인했다. 필수 입력값이 없는 별도 구조화 버전은 승인 시 `STEP_PARAMETER_MISSING`으로 차단됐다.

정상 계획으로 생성한 Execution `bbf2ac81-84e7-42ef-9529-bee62826ca48`는 최종 `PASS`였다. 상세 응답의 version UUID와 plan hash가 조회 응답과 동일했고, 계획/실제 단계 수는 각각 4개였으며 `stepCountMatches=true`였다. 실제 단계는 `step-1`부터 `step-4`까지 각각 `planStepId`로 연결됐다. AI 호출은 0회였다.
