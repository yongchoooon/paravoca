# Phase 10.5 UI and Operations Surface Cleanup

작성 기준일: 2026-05-10

## 구현 상태

Phase 10.5는 구현 완료 상태입니다.

이번 Phase는 backend workflow, Agent 판단, Gemini prompt, TourAPI 호출, RAG, DB 저장 구조를 바꾸지 않고 frontend 표시 구조만 정리했습니다. 핵심은 일반 사용자가 보는 운영 화면과 개발자가 확인하는 debug 화면을 분리하는 것입니다.

## 구현 내용

### Run Detail 탭 구조 정리

대상 파일:

- `frontend/src/pages/RunDetail.tsx`

기존 탭:

- Result Review
- Evidence + QA
- Run Logs
- Raw JSON

현재 탭:

- Result Review
- Evidence + QA
- Developer

`Run Logs`, `Agent Steps`, `Tool Calls`, `LLM Calls`, `Raw JSON`은 제거하지 않고 `Developer` 탭 안으로 이동했습니다.

### 사용자용 진행 단계

기존에는 Run Detail에서 `Planner`, `Geo`, `Gemini Gap`, `Gemini Router`, 개별 planner lane 같은 내부 agent 단계가 그대로 보였습니다.

Phase 10.5에서는 기본 사용자 화면의 진행 단계를 아래 6개로 묶었습니다.

- 요청 확인
- 지역 해석
- 관광 데이터 확인
- 보강 정보 확인
- 상품 초안 생성
- 검수 및 승인

상세 agent step은 `Developer > Detailed agent progress`에서 계속 확인할 수 있습니다.

### Data Coverage 표시 개선

Data Coverage는 내부 필드 중심이 아니라 운영자가 이해할 수 있는 상태 중심으로 정리했습니다.

표시 항목:

- 상세정보
- 이미지
- 운영시간
- 요금
- 예약정보
- 운영자 확인

각 항목은 `충분`, `일부 부족`, `부족`, `정보 없음`, `확인 필요`처럼 사람이 읽을 수 있는 상태로 표시합니다.

### Recommended Data Calls 표시 개선

Recommended Data Calls는 `source_family`, `operation`, `tool_name` 같은 내부 값이 기본 문구의 중심이 되지 않도록 정리했습니다.

표시 기준:

- 호출됨
- 보류됨
- 향후 연결 예정
- 실패함

또한 각 row에 “왜 호출했는지”, “왜 보류됐는지”, “상품화 판단에 어떤 도움이 되는지”를 문장으로 표시합니다. 실제 호출되지 않은 future/unsupported API는 호출된 것처럼 보이지 않게 `향후 연결 예정` 또는 `보류됨`으로 표시합니다.

### Evidence 표시 개선

Evidence table은 raw geo/lcls code를 계속 숨깁니다.

사용자에게 표시하는 항목:

- 근거 제목
- 출처
- 지역
- 유형
- 보강 여부
- 이미지 후보 수
- 운영자 확인 여부
- 요약

Evidence 상세 drawer에서도 raw metadata는 기본 노출하지 않고 `Developer metadata` accordion 안으로 이동했습니다.

### Result Review와 Evidence + QA 역할 정리

Result Review:

- 상품 결과
- QA 요약
- Avoid 기준

Evidence + QA:

- 근거 문서
- 데이터 보강 상태
- QA 상세 이슈
- 승인 이력
- 승인/수정 요청/반려 action

### Placeholder 문구 정리

대상 파일:

- `frontend/src/pages/Dashboard.tsx`

Data Sources, Evaluation, Costs, Poster Studio, Settings placeholder 문구를 후속 Phase 기준으로 정리했습니다.

- Data Sources: Phase 12
- Evaluation: Phase 11 이후
- Costs: Phase 13 또는 운영 단계
- Poster Studio: Phase 13 이후 또는 별도 후속 단계
- Settings: Phase 13 운영 설정

## 하지 않은 것

Phase 10.5는 UI 정리 단계입니다. 아래는 구현하지 않았습니다.

- backend workflow 변경
- ProductAgent evidence 기반 생성 고도화
- Gemini prompt 변경
- TourAPI 또는 추가 KTO API 실제 연결
- RAG 검색 로직 변경
- DB schema 변경
- prompt debug log 파일을 UI에서 직접 읽는 기능

## 검증

검증 명령:

```bash
PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build
```

결과:

- TypeScript check 통과
- Vite production build 통과

backend는 변경하지 않았으므로 backend test는 생략했습니다.

## 다음 단계

다음 구현은 Phase 11입니다.

Phase 11에서는 ProductAgent를 실제 evidence 기반 생성으로 전환합니다. `evidence_profile`, `productization_advice`, `unresolved_gaps`를 상품 생성에 강하게 반영하고, 근거 없는 claim 제한과 QA risk 판단을 강화합니다.
