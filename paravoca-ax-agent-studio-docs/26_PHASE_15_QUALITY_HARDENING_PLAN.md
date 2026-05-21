# Phase 15 Quality Hardening Plan

작성 기준일: 2026-05-21

Phase 14 Poster Studio 이후의 우선순위는 비용 탭이나 배포 안정화가 아니라, 생성 품질과 사용자 화면 품질을 먼저 끌어올리는 것이다. Costs Dashboard는 Phase 21, Deployment / Demo Hardening은 Phase 22로 이동한다.

## 문제 인식

현재 제품은 workflow 전체 흐름과 Poster Studio까지 연결되었지만, 실제 사용자가 보는 결과의 품질에는 아직 큰 공백이 있다.

- QA issue가 너무 추상적이다. 예: “운영시간이나 상시 운영 여부를 단정하고 있습니다.”만으로는 어느 문구가 문제인지 알기 어렵다.
- Sales copy, FAQ, SNS, Claims가 여행 상품을 잘 팔기 위한 마케팅 문구로 충분하지 않다.
- evaluation dataset 결과를 보면 지역, claim, evidence, marketing 품질에서 세부 실패가 남아 있다.
- RAG가 어떤 문서를 근거로 삼는지, 문서가 언제 쌓이고 어떻게 검색되는지 사용자와 개발자가 모두 명확히 이해하기 어렵다.
- run 실행 때 얻은 데이터만 축적하는 구조라면 한 번도 실행하지 않은 지역의 기본 근거 품질이 제한된다.
- 이미지 evidence가 상품과 직접 맞지 않는 경우가 있다.
- Evidence 화면이 사용자에게 어떤 인사이트를 주는지, selection이 어떤 원리로 되는지 부족하다.
- QA 재검수와 AI 수정 후 기존 이슈가 줄어드는 대신 새 이슈가 더 많이 생기는 경우가 있다.
- “추천 보강 호출”처럼 내부 구현 중심 문구가 사용자 화면에 노출된다.
- 전체 UI가 기능은 많지만 경직되어 있고, 개발자용 변수/상태/필드명이 아직 남아 있다.

## Phase 15 목표

Phase 15는 바로 대규모 구현에 들어가기 전에, 실패 유형을 관찰 가능한 단위로 분해하고 후속 Phase의 품질 기준을 확정하는 audit 단계다.

완료 시점에는 다음 질문에 답할 수 있어야 한다.

- QA가 나쁜 이유는 prompt 문제인지, schema 문제인지, deterministic 보정 문제인지, UI 표시 문제인지
- Marketing 문구가 나쁜 이유는 product context 부족인지, prompt 구조 문제인지, evidence 제약이 과한지
- RAG가 실제로 어떤 source document를 만들고, DB/Chroma에 어떤 metadata로 저장하며, 어떤 query/filter로 검색하는지
- Evidence card와 이미지 후보가 왜 선택됐는지 사용자에게 어떻게 설명해야 하는지
- AI 수정 후 QA 재검수에서 기존 이슈와 신규 이슈를 어떻게 비교해야 하는지
- 사용자 화면에서 어떤 내부 용어를 숨기고 어떤 정보만 남겨야 하는지

## Audit 범위

### 1. QA 품질

확인할 것:

- QA issue message가 실제 문제 문구를 인용하는지
- `field_path`가 사용자 친화적 위치명으로 변환되는지
- false positive가 많은 표현
- 누락되는 위험 claim
- deterministic QA와 LLM QA의 역할 분리
- QA issue 삭제, QA only revision, AI partial rewrite 이후 issue 변화

산출물:

- QA issue type/severity 기준표
- 좋은 QA message / 나쁜 QA message 예시
- 기존 이슈 해소 여부를 비교하기 위한 status 모델 초안: `resolved`, `still_open`, `new_issue`

### 2. Marketing Output 품질

확인할 것:

- Sales copy가 상품의 매력과 차별점을 실제로 전달하는지
- FAQ가 단순 운영 리스크 안내에 치우쳐 구매 전환을 돕지 못하는지
- SNS 문구가 generic하거나 서로 비슷한지
- Claims가 너무 방어적이어서 사용할 수 있는 셀링 포인트까지 죽이는지
- evidence 제약과 마케팅 설득력의 균형

산출물:

- Sales copy / FAQ / SNS / Claims별 품질 rubric
- prompt 개선 방향
- evaluation quality dataset에 추가할 marketing 실패 케이스 후보

### 3. RAG / Source Document 흐름

확인할 것:

- Baseline TourAPI 결과가 어떤 source document로 저장되는지
- detail/enrichment 결과가 기존 document를 어떻게 보강하는지
- Chroma index가 어떤 embedding provider와 metadata filter를 사용하는지
- run 실행으로 쌓인 문서와 사전 ingestion 문서가 구분되는지
- 한 번도 실행하지 않은 지역에서 검색 품질이 어떻게 되는지
- duplicate/stale source document 처리 방식

산출물:

- source document lifecycle 다이어그램
- DB table / Chroma collection / metadata mapping 정리
- run 기반 축적과 pre-indexed knowledge base 분리안

### 4. Evidence Selection과 사용자 가치

확인할 것:

- Evidence card가 어떤 근거를 선택했는지
- selection reason이 사용자에게 설명 가능한지
- `usable_claims`, `restricted_claims`, `needs_review`, `unresolved_gaps`가 UI에서 어떤 의미인지
- Evidence 화면이 “근거 원문 보기”인지 “상품화 가능성 판단”인지
- “추천 보강 호출” 같은 문구가 사용자 관점에서 의미가 있는지

산출물:

- Evidence 화면 정보 구조 초안
- 사용자에게 보여줄 claim/evidence 상태 라벨
- 제거하거나 Developer 영역으로 옮길 항목 목록

### 5. Visual Evidence 관련성

확인할 것:

- 상품과 직접 연결된 이미지인지
- 같은 `content_id` 또는 source document로 연결되는지
- 지역만 같고 상품과 무관한 이미지가 상위에 뜨는지
- Poster Studio 참조 이미지 후보와 Evidence 이미지 후보의 정렬 기준이 일관적인지

산출물:

- 이미지 relevance scoring 초안
- 제외/낮은 우선순위 처리 기준
- UI에서 이미지 후보를 설명하는 label 기준

### 6. UI Copy와 제품 표면

확인할 것:

- source_id, raw field path, provider/tool/internal status 노출
- 개발자용 문구가 사용자 화면에 남아 있는 위치
- Dashboard, Run Detail, Evidence + QA, Poster Studio의 visual density
- empty/error/loading state의 문구와 디자인 일관성

산출물:

- 사용자 화면 copy cleanup 목록
- Developer 탭으로 이동할 정보 목록
- Phase 20 UI polish 우선순위

## 후속 Phase 재정의

### Phase 16: QA Quality Hardening

- QA prompt/schema 개선
- issue message에 문제 위치와 문제 문구 인용 강제
- severity/type 기준 정리
- false positive 축소
- AI 수정 후 QA 재검수 비교 모델 도입

### Phase 17: Marketing Output Hardening

- Product -> Marketing prompt 개선
- Sales copy, FAQ, SNS, Claims 품질 rubric 반영
- 근거 기반 claim 제한을 유지하면서 셀링 포인트를 살리는 구조로 개선

### Phase 18: RAG and Evidence Pipeline Hardening

- source document lifecycle 정리
- run 기반 축적과 사전 ingestion 전략 분리
- RAG relevance와 metadata filter 개선
- Evidence selection scoring 개선

### Phase 19: Evidence and Visual Evidence UX Redesign

- Evidence 화면을 상품 신뢰/공백/claim 판단 중심으로 재설계
- 이미지 evidence relevance 개선
- 내부 구현 중심 문구 제거

### Phase 20: UI Copy and Product Surface Polish

- 사용자 화면의 내부 변수/필드/상태 제거
- 한국어 label 체계 정리
- Run Detail, Evidence + QA, Poster Studio 디자인 polish

### Phase 21: Costs Dashboard

- 기존 Phase 15였던 비용 탭 구현
- LLM/image/workflow 비용과 latency 가시화

### Phase 22: Deployment / Demo Hardening

- 기존 Phase 16였던 배포/데모 안정화
- env, CI, production build, demo scenario, 로그 운영 정리

## Phase 15 완료 기준

- 품질 audit 결과가 문서로 남는다.
- 개선 작업이 Phase 16~20으로 나뉘어 있고, 각 Phase의 우선순위와 테스트 기준이 명확하다.
- 바로 구현에 들어갈 수 있는 Phase 16 실행 명령어 초안이 준비된다.
- Costs와 Deployment가 후순위로 이동했다는 사실이 roadmap과 README에 반영된다.
