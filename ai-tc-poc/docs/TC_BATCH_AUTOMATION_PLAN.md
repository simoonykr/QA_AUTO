# 다중 TC 구조화·실행 상세 기획

마지막 갱신: 2026-09-28

## 1. 배경과 결정

XLSX 한 파일에서 KG-WEB-001~021처럼 여러 TC를 감지해도 현재 화면은 선택한 TC 1건만 구조화한다. 승인과 실행 역시 해당 TC의 `versionId` 1건만 대상으로 한다. 따라서 21개가 감지됐다는 표시는 21개가 구조화·실행됐다는 뜻이 아니다.

TC별 원문, revision, 승인 이력, 실행 결과를 추적해야 하므로 **TC 1건 = TestCase 1건 = Version 계보 1개** 원칙은 유지한다. 여러 TC를 하나의 Version에 합치지 않는다. 파일 전체 처리는 개별 Version을 묶어 관리하는 Batch와, 승인된 Version을 묶어 실행하는 Suite로 제공한다.

## 2. 현재 동작과 P0 보완

### 현재 동작

1. 파일 업로드 후 서버가 TC 목록을 분리한다.
2. 사용자가 TC 카드 1건을 선택한다.
3. 선택한 원문만 구조화해 새 Version을 만든다.
4. 검토·승인 후 해당 `versionId`만 실행한다.
5. 다른 TC는 자동 처리되지 않는다.

### 즉시 반영하는 P0

- 감지 TC를 가로 캐러셀이 아닌 세로 목록으로 보여 전체 건수를 확인할 수 있게 한다.
- `선택 1 / 전체 N`, 이번 처리 대상, 미처리 건수를 지속 표시한다.
- 구조화 버튼에 선택 TC ID를 표시한다.
- 테스트 케이스 목록의 실행 버튼은 행별 `latestVersionId`를 사용한다. 직전에 열었던 다른 TC나 페이지 시나리오의 전역 Version을 재사용하지 않는다.
- READY가 아니거나 최신 Version ID가 없으면 실행 버튼을 비활성화한다.

## 3. 목표 사용자 흐름

### 3.1 가져오기

1. 사용자가 XLSX를 업로드한다.
2. 시스템은 `importBatchId`, 감지·제외·경고 건수와 TC별 안정 ID를 반환한다.
3. 화면은 전체 TC를 표 형태로 보여준다. 사용자는 전체 선택, 일부 선택, 검색과 필터를 사용할 수 있다.
4. 중복 external ID, 원문 누락, 메타데이터 행은 구조화 시작 전에 구분한다.

### 3.2 일괄 구조화

1. 사용자가 선택한 TC를 일괄 구조화한다.
2. Batch는 TC별 독립 요청으로 처리하며 각 항목마다 새 `versionId`를 만든다.
3. 진행 화면은 대기/처리/검토 필요/실패/완료 건수를 보여준다.
4. 일부 실패가 전체 성공을 취소하지 않는다. 실패 TC의 선택과 원문을 보존하고 사용자가 해당 건만 다시 시도한다.
5. 409 충돌은 자동 재시도하지 않는다. 현재 revision과 서버 revision을 표시하고 직접 다시 구조화하도록 한다.

### 3.3 검토·승인

1. 검토 대기열은 TC별 Version, 자동화 가능 여부, 미해결 selector, 경고를 표시한다.
2. 사용자는 항목을 열어 수정하고 저장할 때 `expectedRevision`을 보낸다.
3. 일괄 승인은 실행 가능한 항목만 대상으로 하며 제외된 항목과 이유를 먼저 보여준다.
4. 승인 성공 응답의 새 `versionId`만 실행에 사용한다. 이전 승인 Version과 페이지 분석 선택 상태는 재구조화 시작 시 초기화한다.

### 3.4 Suite 실행

1. 사용자가 승인된 Version 여러 건을 선택해 Suite를 만든다.
2. 서버는 Version마다 독립 Execution을 생성하고 `executionSuiteId`로 묶는다.
3. 결과 화면은 전체 PASS/FAIL/BLOCKED, TC별 단계와 증적, 실패만 재실행을 제공한다.
4. Suite PASS는 모든 포함 Execution이 PASS일 때만 표시한다. 일부 실행 결과로 파일 전체 성공처럼 표시하지 않는다.

## 4. 백엔드 계약 제안

### 가져오기 Batch

기존 import 응답에 선택적으로 `importBatchId`와 항목별 `itemId`, `externalId`, `title`, `status`를 추가한다.

### 구조화 Batch

`POST /api/v1/test-case-structure-batches`

```json
{
  "importBatchId": "uuid",
  "itemIds": ["uuid"],
  "maxConcurrency": 3,
  "maxAiCallsPerCase": 0
}
```

응답은 `batchId`, 항목별 `testCaseId`, `versionId`, `revision`, `status`, `error`를 반환한다. 조회는 `GET /api/v1/test-case-structure-batches/{batchId}`로 제공한다.

항목 상태는 `QUEUED | STRUCTURING | REVIEW_REQUIRED | READY | FAILED | CONFLICT | CANCELLED`를 사용한다. 같은 idempotency key 재전송은 같은 Batch를 반환해야 한다.

### 일괄 승인

`POST /api/v1/test-case-structure-batches/{batchId}/approve`

```json
{
  "items": [
    {"versionId": "uuid", "expectedRevision": 2}
  ]
}
```

항목별 성공·실패를 반환한다. `TC_IMPORT_CONFLICT`, `TC_VERSION_CONFLICT`, `MANUAL_REVIEW_REQUIRED`, `PLAN_NOT_EXECUTABLE`을 표준 오류 코드로 유지하며 부분 성공을 허용한다.

### 실행 Suite

`POST /api/v1/execution-suites`

```json
{
  "testCaseVersionIds": ["uuid"],
  "environmentId": "uuid",
  "retryPolicy": "MANUAL"
}
```

응답은 `executionSuiteId`와 Version별 `executionId`를 반환한다. `GET /api/v1/execution-suites/{id}`는 집계 상태와 항목 결과를, 기존 Execution 상세 API는 단계·증적을 반환한다. 재실행은 실패한 항목을 명시적으로 선택해 새 Suite를 만들며 기존 결과를 덮어쓰지 않는다.

### 목록 실행 계약

`GET /api/v1/test-cases`의 각 항목은 최신 Version의 상태와 함께 `latestVersionId`를 반환한다. READY 행 실행은 반드시 이 ID로 실행 계획을 조회한다. `latestVersionId=null`이면 실행할 수 없다.

## 5. 상태·동시성 규칙

- 파일 교체, TC 선택, 원문 편집 시 진행 중 요청의 client request token을 폐기하고 늦은 응답을 무시한다.
- 구조화 시작 시 이전 `versionId`, 승인 상태, 실행 계획, 페이지 분석 결과와 후보 선택을 초기화한다.
- 구조화·승인 버튼은 요청 중 비활성화하고 같은 idempotency key를 사용한다.
- Batch 내 동일 external ID는 기본 차단하며 사용자가 기존 TC 업데이트인지 신규 가져오기인지 결정한다.
- 자동 재시도는 네트워크 조회에만 제한한다. Version을 생성하거나 revision을 변경하는 요청과 409는 자동 재시도하지 않는다.
- 취소는 아직 시작하지 않은 항목만 취소하며 이미 생성된 Version은 이력으로 남긴다.

## 6. 데이터 모델

- `ImportBatch`: 파일 메타데이터, 감지·제외·경고 집계, 생성자와 생성 시각
- `ImportBatchItem`: external ID, 원문 snapshot, 분리 상태, TestCase 연결
- `StructureBatch`: 요청 범위, idempotency key, 진행 집계
- `StructureBatchItem`: item, 생성 Version, revision, 상태와 표준 오류
- `ExecutionSuite`: 환경, 집계 상태, 생성자와 실행 시각
- `ExecutionSuiteItem`: Version과 Execution 연결, 결과와 재실행 계보

원문 snapshot은 감사에 필요한 최소 범위만 저장하고 비밀값·쿠키·전체 페이지 HTML은 저장하지 않는다.

## 7. 완료 조건

KakaoGames XLSX 21건을 기준으로 다음을 만족해야 한다.

1. 화면에서 21건 전부 확인 가능하고 선택·미선택 범위가 명확하다.
2. 단건 구조화 시 해당 TC만 새 Version이 생성되며 다른 20건은 미처리로 남는다.
3. 일괄 구조화 시 선택 21건에 각각 Version과 결과 상태가 생성된다.
4. 한 항목의 409·분석 실패가 나머지 항목을 취소하지 않는다.
5. 승인되지 않거나 실행 불가능한 항목은 Suite에 포함되지 않고 이유가 표시된다.
6. Suite는 승인된 Version별 Execution을 만들고 전체/TC별 결과와 증적을 연결한다.
7. 테스트 케이스 목록에서 KG-WEB-021 실행 시 KG-WEB-021의 최신 READY Version만 실행한다.
8. 같은 파일을 다시 가져와도 동일 external ID의 TestCase가 무조건 중복 증가하지 않는다.

## 8. 단계별 개발 순서

1. **P0 프론트·목록 계약**: 단건 처리 범위 표시, 전체 목록 가시성, 행별 최신 Version 실행 연결
2. **P1 백엔드**: Import/Structure Batch와 항목별 상태·충돌·idempotency
3. **P1 프론트**: 다중 선택, 진행률, 검토 대기열, 실패 항목 재시도
4. **P2 백엔드**: Execution Suite 집계와 실패 항목 재실행
5. **P2 프론트**: Suite 실행 설정·집계 결과·TC별 증적 탐색
6. **P3**: 대용량 성능, 예약 실행, 알림과 감사 로그
