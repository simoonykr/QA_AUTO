import type { StructuredStep, TestCaseSummary } from './types'

export const mockTestCases: TestCaseSummary[] = [
  { id: 'TC-142', title: '신규 사용자 이메일 회원가입', group: 'Authentication', status: 'READY', passRate: 96, lastExecutedAt: '12분 전' },
  { id: 'TC-138', title: '상품 검색 및 가격 필터 적용', group: 'Search', status: 'READY', passRate: 89, lastExecutedAt: '어제' },
  { id: 'TC-131', title: '장바구니 수량 변경 후 합계 검증', group: 'Checkout', status: 'REVIEW_REQUIRED', passRate: 72, lastExecutedAt: '2일 전' },
  { id: 'TC-127', title: '만료된 세션에서 로그인 화면 이동', group: 'Authentication', status: 'READY', passRate: 100, lastExecutedAt: '4일 전' },
]

export const mockSteps: StructuredStep[] = [
  { id: 'step-1', title: '로그인 페이지 진입', note: 'URL과 로그인 폼을 확인합니다.', action: 'navigate' },
  { id: 'step-2', title: '테스트 계정 입력', note: '보안 저장소의 계정 별칭을 사용합니다.', action: 'fill' },
  { id: 'step-3', title: '로그인 버튼 선택', note: 'role=button, name=로그인 후보를 탐색합니다.', action: 'click' },
  { id: 'step-4', title: '대시보드 노출 검증', note: 'URL과 환영 문구를 규칙 기반으로 확인합니다.', action: 'assert' },
]
