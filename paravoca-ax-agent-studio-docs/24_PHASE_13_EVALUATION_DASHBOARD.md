# Phase 13: Evaluation and Quality Dashboard

작성 기준일: 2026-05-18

## 문서 목적

이 문서는 PARAVOCA AX Agent Studio의 AI Agent workflow를 어떻게 평가할지 정의합니다. 단순히 "최종 문장이 좋아 보이는가"가 아니라, 자연어 요청을 해석하고, TourAPI/KTO 데이터를 수집하고, RAG와 enrichment를 거쳐, 근거 기반 여행상품을 생성하고, QA가 위험 claim을 제한하는 전체 agent workflow를 평가 대상으로 봅니다.

요약하면 PARAVOCA 평가는 아래 네 가지를 동시에 봅니다.

1. 사용자가 요청한 일을 끝냈는가
2. 그 과정에서 올바른 지역, 데이터, API, 도구를 사용했는가
3. 최종 상품과 마케팅 문구가 실제 근거에 묶여 있는가
4. 운영자가 실패 원인을 재현하고 개선할 수 있는가

웹 검색/공식 웹 근거 수집은 현재 제품 계획에서 제외했으므로 Phase 13 평가 대상에도 포함하지 않습니다.

## 최근 Agent 평가 방식에서 가져올 원칙

최근 AI Agent 평가는 일반 LLM 답변 평가와 다르게, 최종 답변만 보지 않고 trace, tool call, intermediate state, final state를 함께 평가하는 방향으로 정리되고 있습니다.

- OpenAI Agent Evals는 traces, graders, datasets, eval runs를 함께 사용하고, trace 안에 model call, tool call, guardrail, handoff 같은 전체 실행 기록을 포함합니다.
- OpenAI Trace Grading은 agent trace에 구조화된 점수나 label을 붙여, agent가 왜 성공하거나 실패했는지 workflow 수준에서 찾는 방식입니다.
- LangSmith 문서는 agent를 최종 결과만 보는 black-box 평가, 단일 step 평가, 전체 trajectory 평가로 나누고, trajectory 평가에서는 tool call sequence나 expected tool set을 검사할 수 있다고 설명합니다.
- Ragas는 RAG와 agent/tool-use 평가를 분리해 Context Precision/Recall, Response Relevancy, Faithfulness, Tool Call Accuracy, Tool Call F1, Agent Goal Accuracy 같은 metric을 제시합니다.
- tau-bench는 실제 도메인 정책과 API tool을 가진 agent-user 상호작용에서 최종 DB state가 목표 state와 맞는지 평가하고, 여러 번 실행했을 때의 일관성을 pass^k로 봅니다.
- WebArena는 실제처럼 재현 가능한 web 환경에서 최종 task completion correctness를 평가합니다. 핵심은 live web이 아니라 reproducible environment와 functional correctness입니다.
- AgentBench는 여러 interactive environment에서 reasoning, decision-making, instruction following을 평가하며, agent failure가 장기 추론과 의사결정 문제에서 자주 나온다고 봅니다.
- NIST AI RMF는 valid/reliable, safe, secure/resilient, accountable/transparent, explainable/interpretable, privacy-enhanced, fair 같은 신뢰성 관점을 제시합니다.

PARAVOCA에 그대로 적용하면 결론은 명확합니다.

- 최종 상품만 평가하면 부족합니다.
- agent step, LLM call, tool call, retrieval, enrichment, final output을 모두 연결해야 합니다.
- 단일 총점보다 metric별 pass/fail/partial score와 reason이 중요합니다.
- live API는 운영 현실을 반영하지만 변동성이 있으므로, smoke/live eval과 deterministic regression eval을 분리해야 합니다.
- 상품성처럼 자동화가 어려운 항목은 LLM-as-judge와 사람 평가를 별도로 둬야 합니다.

## 기존 두 문서에서 남길 것과 버릴 것

### 남길 것

기존 `24_PHASE_13_EVALUATION_DASHBOARD.md`에서 유지할 내용:

- 평가 대상이 지역 해석, 데이터 수집, KTO enrichment, RAG 검색, evidence 기반 상품 생성, QA claim 제한, 비용, latency까지 포함된다는 관점
- JSONL dataset과 CLI runner 구조
- Evaluation Dashboard에서 case별 pass/fail/skip, metric, run_id, cost, latency를 보여주는 구조
- 평가용 workflow run을 일반 Dashboard와 분리하는 정책
- `--no-live-api`, `--sleep-between-cases`, `--stop-on-first-failure`, `--reuse-run-id`, `--name` 같은 실행 옵션
- 실패를 숨기지 않고 reason과 Developer JSON을 남기는 방식

`ai_agent_travel_product_evaluation.md`에서 유지할 내용:

- 데이터/API 수집, tool use, 근거성, 여행상품 품질, 운영/안전성을 나누어 평가하는 구조
- 테스트셋 + 자동채점 + 사람평가 + 온라인 지표를 함께 쓰는 접근
- 최종 답변뿐 아니라 agent 실행 경로를 평가해야 한다는 관점
- 존재하지 않는 장소 생성률, 지역 불일치율, 제약 조건 충족률 같은 여행상품 특화 지표
- pairwise/human evaluation이 상품성 판단에 필요하다는 점
- 안전/보안 테스트를 별도 축으로 둬야 한다는 점

### 줄이거나 제거할 것

- 100점 평가표를 단일 대표 점수처럼 쓰는 방식은 줄입니다. 내부 진단에는 metric별 점수와 reason이 더 중요합니다. 100점 rubric은 사람 평가나 demo summary용으로만 사용합니다.
- "MVP는 50~100개면 충분" 같은 숫자는 고정 규칙이 아니라 권장 시작점으로만 둡니다. 실제 기준은 case coverage와 failure mode coverage로 봅니다.
- "API 실패 복구율 95%" 같은 수치는 제품 maturity가 올라간 뒤 SLA 목표로 다루고, 현재 Phase 13 문서에서는 baseline target으로만 둡니다.
- TourAPI 외부 데이터가 0개인 것을 무조건 실패로 보지 않습니다. API를 호출했고 `no_candidates`가 정상 응답이면 진단 결과로 기록합니다.
- 해외 목적지/지역 확인 필요처럼 조기 종료가 기대되는 케이스에서 retrieval count를 0점으로 감점하지 않습니다. 해당 metric은 `not_applicable`입니다.

## PARAVOCA 평가 레이어

### 1. Outcome Evaluation

질문: 사용자의 요청을 제품 관점에서 끝냈는가?

현재 metric:

- `workflow_success`
- `product_count_satisfaction`
- `unsupported_or_clarification_accuracy`

평가 방식:

- 정상 상품 생성은 `awaiting_approval`, `approved`, `changes_requested` 같은 reviewable 상태면 성공입니다.
- 해외 목적지, 애매한 지역, 데이터 부족은 내부 crash가 아니라 controlled exit이면 성공 또는 부분 성공으로 봅니다.
- 사용자가 3개를 요청했지만 근거가 부족해 1개만 생성했다면, 근거 부족이 명시되어 있어야 합니다.

보강 필요:

- `controlled_exit_reason`을 더 세분화합니다.
  - `unsupported_destination`
  - `needs_geo_clarification`
  - `insufficient_source_data`
  - `api_unavailable`
  - `user_cancelled`
- outcome metric은 단순 status가 아니라 "기대된 종료 형태와 실제 종료 형태가 맞는가"로 평가합니다.

### 2. Geo Resolution Evaluation

질문: 자연어 지역 의도를 제대로 해석했는가?

현재 metric:

- `geo_resolution_accuracy`
- `unsupported_or_clarification_accuracy`

평가 방식:

- `expected_geo.status`, `mode`, `ldong_regn_cd`, `ldong_signgu_cd`, `keyword_contains`를 비교합니다.
- "중구"처럼 애매한 요청은 확정하지 않고 clarification으로 종료해야 합니다.
- 해외 목적지는 PARAVOCA 국내 관광 데이터 지원 범위를 벗어난다고 안내해야 합니다.
- 대청도처럼 TourAPI ldong catalog에는 시군구까지만 있고 세부 섬/생활권은 keyword/sub-area로 남겨야 하는 케이스를 별도 테스트합니다.

보강 필요:

- 지역 후보 ranking과 confidence calibration을 평가합니다.
- `resolved_locations`, `clarification_candidates`, `unsupported_locations`를 metric detail에 사람이 읽기 쉽게 표시합니다.
- route형 또는 복수 지역 요청은 현재 지원하지 않으므로 expected controlled exit으로 둡니다.

### 3. Data Retrieval and RAG Evaluation

질문: 필요한 근거 문서를 충분히, 관련성 있게 가져왔는가?

현재 metric:

- `retrieval_result_count`
- `source_document_indexed_count`
- `evidence_document_validity`

평가 방식:

- 검색 결과 수는 운영 진단 metric입니다. 현재 기준은 retrieved document 3개 이상이면 1점입니다.
- 2개면 0.6667처럼 partial score를 부여하고, UI에는 왜 감점됐는지 reason과 count를 표시합니다.
- 해외/확인필요처럼 검색 단계가 실행되지 않는 것이 정상인 케이스는 `not_applicable`로 표시하고 평균 점수에서 제외합니다.
- source document는 `doc_id`가 있어야 하고, ProductAgent가 참조할 수 있어야 합니다.

보강 필요:

- RAGAS 계열 관점으로 다음 지표를 추가합니다.
  - context precision: 가져온 문서 중 실제 상품 생성에 유용한 비율
  - context recall: 기대 근거 조건을 충족하는 문서를 빠뜨리지 않았는지
  - faithfulness: 상품 문장이 source document에 의해 뒷받침되는지
- Chroma 검색에서 지역/keyword filter로 drop된 문서 수를 UI diagnostic에 표시합니다.
- live API 변동과 embedding/RAG 문제를 구분하기 위해 retrieval diagnostics를 더 구조화합니다.

### 4. Tool and Trajectory Evaluation

질문: Agent가 맞는 도구를 맞는 순서와 인자로 사용했는가?

현재 metric:

- `expected_source_family_coverage`
- `enrichment_call_success_rate`

평가 방식:

- dataset의 `expected_source_families`와 실제 `enrichment_tool_calls`, `retrieved_documents.metadata.source_family`를 비교합니다.
- `covered`, `no_candidates`, `skipped`, `disabled`, `missing`, `failed`를 구분합니다.
- `no_candidates`는 API가 정상 호출됐지만 결과가 없는 것이므로 실패가 아닙니다.
- `missing`은 기대 source family가 아예 관측되지 않은 상태입니다.
- `failed`는 실제 호출이 실패한 상태입니다.

보강 필요:

- Tool Call Accuracy를 source family 수준이 아니라 operation/argument 수준까지 확장합니다.
  - 예: `kto_tourapi_kor.detailCommon2`가 필요한 content_id에 호출됐는가
  - 예: visual 요청인데 photo API planner lane이 열렸는가
  - 예: wellness 요청인데 `kto_wellness` call이 계획 또는 호출됐는가
- trajectory exact match는 너무 엄격하므로 기본값으로 쓰지 않습니다. 대신 expected tool set과 forbidden tool set을 평가합니다.
- 불필요한 call budget 초과, feature flag off 상태의 호출 시도, 의료관광 flag 위반을 별도 issue로 잡습니다.

### 5. Evidence-based Product Evaluation

질문: 최종 상품이 실제 근거에 묶여 있고, 근거 없는 claim을 만들지 않았는가?

현재 metric:

- `product_source_id_validity`
- `claim_limit_compliance`
- `qa_issue_detection`

평가 방식:

- product `source_ids`는 실제 `retrieved_documents.doc_id`만 참조해야 합니다.
- 존재하지 않는 `source_id`는 blocking failure입니다.
- `expected_claim_limits`는 product `not_to_claim`, `claim_limits`, `needs_review`, `coverage_notes`, marketing `claim_limits`, QA issue, unresolved gaps 중 하나에 명시적으로 반영되어야 합니다.
- 가격, 예약, 운영시간, 안전, 외국어, 의료/웰니스 효능, 반려동물 동반 가능 여부는 근거가 없으면 단정하면 안 됩니다.

보강 필요:

- claim extraction을 추가합니다.
  - 상품/마케팅 문구에서 장소, 운영시간, 가격, 예약, 안전, 효능, 언어 지원 claim을 추출합니다.
  - 각 claim이 어떤 source document 또는 enrichment result에 의해 지지되는지 연결합니다.
  - 근거가 없으면 `unsupported_claim`으로 표시합니다.
- source evidence가 약한 경우 "거짓"으로 단정하지 않고 `needs_review` 또는 `low_confidence`로 분리합니다.
- LLM-as-judge는 최종 판정자가 아니라 보조 judge로 사용하고, 가능한 항목은 deterministic validator를 우선합니다.

### 6. Product Quality and Human Evaluation

질문: 상품으로서 실제로 쓸 만한가?

자동 평가만으로는 상품성, 매력도, 동선 현실성, 외국인 대상 적합성을 충분히 판단하기 어렵습니다. 따라서 아래는 LLM-as-judge와 사람 평가를 별도로 둡니다.

평가 항목:

- 사용자 조건 충족
- 지역/테마 일관성
- 동선 현실성
- 일정 과밀도
- 상품명/콘셉트/판매 포인트 완성도
- 외국인 대상 설명 적합성
- 운영자 확인 항목의 명확성

권장 방식:

- 초기에는 매주 10~20개 run을 사람이 리뷰합니다.
- 상품 A/B를 비교하는 pairwise evaluation을 둡니다.
- LLM-as-judge는 5점 rubric과 근거 설명을 출력하게 하고, 사람 평가와의 상관을 주기적으로 확인합니다.

주의:

- 사람 평가 점수와 자동 평가 점수는 같은 것이 아닙니다.
- 자동 평가는 회귀 탐지와 위험 감지에 강하고, 사람 평가는 상품성 판단에 강합니다.

### 7. Reliability, Cost, Latency Evaluation

질문: 같은 요청을 여러 번 실행해도 안정적인가, 비용과 시간이 통제되는가?

현재 metric:

- `latency_ms`
- `llm_cost_usd`
- `llm_cost_krw`

평가 방식:

- latency와 cost는 pass/fail보다 trend를 봅니다.
- Gemini timeout, 503, TourAPI timeout은 실제 운영 리스크로 기록합니다.
- live smoke eval은 외부 API와 모델 상태 영향을 받으므로, 실패 원인을 `model_provider_unavailable`, `kto_api_timeout`, `schema_validation_error`, `retrieval_empty`처럼 나눠야 합니다.

보강 필요:

- tau-bench의 pass^k 관점처럼 중요한 smoke case는 같은 입력을 여러 번 실행해 consistency를 봅니다.
- 예: `pass@1`, `pass@3`, `stable_geo_resolution_rate`, `stable_product_count_rate`.
- 평균뿐 아니라 p50/p95 latency와 cost를 분리합니다.
- token truncation, JSON schema retry, compact retry count를 metric에 포함합니다.

### 8. Safety, Security, Policy Evaluation

질문: 안전하지 않은 요청, 민감정보, prompt injection, 과도한 tool use를 막는가?

평가 항목:

- 국내 관광상품 범위 밖 요청 차단
- prompt injection 거부
- API key/system prompt 노출 거부
- 의료/웰니스 효능 단정 금지
- 위험하거나 불가능한 여행상품 기획 거부 또는 확인 필요 처리
- 개인정보/결제정보/민감정보 미노출
- feature flag 정책 준수

보강 필요:

- `safety_policy_compliance` metric을 추가합니다.
- OWASP LLM Top 10 스타일의 adversarial prompt dataset을 별도 파일로 둡니다.
- NIST AI RMF 관점에서 reliable/safe/secure/accountable/transparent/privacy를 운영 체크리스트로 둡니다.

## Dataset 설계

현재 dataset은 `backend/app/evals/datasets/*.jsonl`에 둡니다.

현재 schema:

```json
{
  "case_id": "smoke_busan_busanjin_night",
  "name": "부산 부산진구 야간 관광",
  "input": {
    "message": "부산 부산진구에서 외국인 대상 감성 야간 관광 상품 3개 기획해줘.",
    "period": "2026-05",
    "target_customer": "외국인",
    "product_count": 3,
    "preferences": ["야간 관광"],
    "avoid": ["가격 단정 표현"],
    "output_language": "ko"
  },
  "expected_geo": {
    "status": "resolved",
    "mode": "single_region",
    "ldong_regn_cd": "26",
    "ldong_signgu_cd": "230"
  },
  "expected_source_families": ["kto_tourapi_kor"],
  "expected_min_products": 2,
  "expected_claim_limits": ["가격 단정 표현"],
  "expected_evidence_requirements": ["source_ids", "coverage_notes"],
  "requires_live_api": true,
  "tags": ["geo", "tourapi"]
}
```

권장 확장 schema:

```json
{
  "case_id": "theme_wellness_busan_001",
  "name": "부산 웰니스 근거 기반 상품",
  "tier": "regression",
  "input": {},
  "expected_outcome": {
    "type": "reviewable_output",
    "min_products": 2,
    "max_products": 3
  },
  "expected_geo": {},
  "expected_tool_behavior": {
    "required_source_families": ["kto_tourapi_kor", "kto_wellness"],
    "allowed_no_candidates": ["kto_wellness"],
    "forbidden_source_families": ["kto_medical"]
  },
  "expected_claim_policy": {
    "must_reflect": ["건강 효능 단정 금지"],
    "forbidden_public_claims": ["치료", "효능 보장", "반려동물 동반 가능 단정"]
  },
  "rubric": {
    "product_quality": ["테마 일관성", "외국인 대상 적합성", "운영자 확인 항목 명확성"]
  },
  "requires_live_api": true,
  "severity": "blocking",
  "tags": ["theme", "wellness", "claim_policy"]
}
```

## Dataset tier

| Tier | 목적 | 실행 시점 | Live API |
|---|---|---|---|
| `smoke` | 핵심 workflow가 살아 있는지 빠르게 확인 | 로컬/수동 | 선택 |
| `regression` | 과거에 깨졌던 문제 재발 방지 | PR/릴리즈 전 | 기본 off |
| `golden` | 데모/핵심 상품 시나리오 품질 확인 | 릴리즈 전 | on 가능 |
| `adversarial` | prompt injection, 정책 위반, 엣지 케이스 | 정기 실행 | off 가능 |
| `live_kto` | 실제 KTO API와 Gemini 외부 상태 확인 | 수동/야간 | on |
| `human_review` | 상품성/현실성/매력도 평가 | 주기적 샘플링 | on 가능 |

## 현재 구현 범위

현재 구현된 항목:

- `backend/app/evals/datasets/smoke.jsonl`
- `backend/app/evals/datasets/regression.jsonl`
- `backend/app/evals/datasets/quality.jsonl`
- `python -m app.evals.run_eval --dataset smoke --limit 5`
- `--name`, `--case-id`, `--no-live-api`, `--reuse-run-id`, `--output-json`, `--output-md`
- `--sleep-between-cases`, `--stop-on-first-failure`
- 파일 기반 evaluation report 저장
- `GET /api/evaluations`
- `GET /api/evaluations/{eval_id}`
- `GET /api/evaluations/{eval_id}/cases`
- AppShell `Evaluation` 화면
- Evaluation report 삭제 시 해당 report가 소유한 workflow run 함께 삭제
- Evaluation 실행이 생성한 workflow run을 일반 Dashboard에서 숨김
- score 1 미만 metric을 Evaluation UI의 진단 카드에 표시
- 해외/확인필요 같은 controlled exit에서 retrieval/indexing metric을 `not_applicable`로 처리
- metric별 `evaluator_type`, `principle`, `expected`, `actual`, `penalty_reason`, `next_check`, `not_applicable_reason`
- Evaluation UI에서 코드 검사/LLM 평가/사람 평가 예정 주체 구분
- `-` 점수는 0점이 아니라 평가 제외 또는 점수화하지 않는 관찰값으로 표시
- `--enable-llm-judge`가 켜진 경우에만 LLM-as-a-Judge 품질 metric 실행

## Phase 13.1: Metric Explainability

Phase 13.1의 핵심은 "점수는 나왔는데 왜 그런지 모르는 문제"를 줄이는 것입니다. 평가 결과는 운영자가 다음 행동을 결정할 수 있어야 하므로, 각 metric은 아래 구조를 갖습니다.

```json
{
  "name": "retrieval_result_count",
  "evaluator_type": "code",
  "score": 0.6667,
  "principle": "상품 생성에 사용할 retrieved document가 운영 기준 이상 확보됐는지 확인합니다.",
  "expected": "정상 상품 생성 케이스에서는 사용 가능한 근거 문서가 3개 이상이면 1점입니다.",
  "actual": "사용 가능한 retrieved document가 2개입니다. Vector 검색 결과는 4개, 지역 필터 후 결과는 2개입니다.",
  "penalty_reason": "근거 문서가 3개 미만이라 상품 생성에 사용할 근거 풀이 약합니다.",
  "next_check": "TourAPI raw count, Chroma where filter, post geo filter count, retrieved_documents를 확인하세요.",
  "not_applicable_reason": null
}
```

평가 주체는 세 가지로 구분합니다.

| 주체 | 의미 | 현재 상태 |
|---|---|---|
| `code` | DB, workflow output, tool call, LLM call log를 규칙으로 검사 | 구현 |
| `llm` | 상품성, 자연스러움, 복합 claim 판단처럼 규칙만으로 어려운 항목을 LLM judge로 평가 | `--enable-llm-judge`에서 구현 |
| `human_planned` | 운영자/기획자가 직접 상품 품질을 평가 | 후속 P3 |

현재 구현된 대부분의 metric은 `code` 검사입니다. 이는 LLM 품질 평가가 불필요하다는 뜻이 아니라, 자동 회귀 검사는 먼저 deterministic하게 가능한 부분부터 잡는다는 뜻입니다.

`score: null`은 항상 0점이 아닙니다.

- 조기 종료가 기대되는 해외/지역 확인 케이스의 검색 결과 수는 평가 대상이 아닙니다.
- latency/cost는 현재 pass/fail 점수가 아니라 관찰값입니다.
- UI에서는 이 둘을 빨간 실패로 보이지 않게 회색 badge로 표시합니다.

감점 설명은 내부 용어가 아니라 아래 순서로 보여야 합니다.

1. 기준: 원래 무엇을 기대했는지
2. 실제 결과: 이번 run에서 무엇이 나왔는지
3. 감점 이유: 왜 1점이 아닌지
4. 다음 확인: 운영자가 어디를 보면 되는지

예를 들어 `claim_limit_compliance`가 0.5라면 "Claim 제한 준수 실패"만 보여주지 않고, 어떤 제한은 반영됐고 어떤 제한은 미반영됐는지, 공개 상품/마케팅 문구에 어떤 단정 표현 후보가 남았는지를 함께 보여줍니다.

## Phase 13.2: LLM-as-a-Judge Quality Evaluation

Phase 13.2는 코드 검사만으로 판단하기 어려운 품질 항목을 LLM judge로 보조 평가합니다. 기본 실행에서는 꺼져 있고, 비용이 발생하므로 `--enable-llm-judge`를 명시한 경우에만 실행합니다.

현재 judge 모델은 `GEMINI_GENERATION_MODEL` 설정을 그대로 사용합니다. 기본값은 `gemini-2.5-flash-lite`입니다. Judge 호출 purpose는 workflow agent와 구분되도록 `eval_product_quality_judge`, `eval_evidence_usefulness_judge`, `eval_marketing_quality_judge`, `eval_claim_risk_judge`로 기록됩니다.

추가된 LLM judge metric:

| Metric | 평가 대상 | 주의 |
|---|---|---|
| `product_quality_judge` | 상품이 사용자 요청에 맞고 외국인 대상 상품으로 자연스러운지 | source_id 존재 여부 자체는 코드 metric이 이미 검사 |
| `evidence_usefulness_judge` | 근거가 상품화 포인트로 잘 전환됐는지 | 근거를 단순히 많이 썼는지가 아니라 적절히 썼는지 평가 |
| `marketing_quality_judge` | 마케팅/FAQ/SNS/검색 키워드가 상품과 일관되고 과장되지 않았는지 | claim 제한 반영 여부도 함께 확인 |
| `claim_risk_llm_judge` | 암시적 단정 표현과 자연어 뉘앙스의 claim 위험 | 코드 기반 claim 검사와 중복하지 않고 애매한 표현을 보조 판단 |

LLM judge는 최종 진실 판정자가 아닙니다. 상품성, 자연스러움, 암시적 claim 위험처럼 deterministic rule로만 판단하기 어려운 항목을 보조로 진단합니다. 따라서 metric에는 `evaluator_type: llm`이 붙고, UI에서도 `LLM 평가` badge로 표시합니다.

LLM judge metric도 동일하게 아래 설명 구조를 갖습니다.

- 기준: 어떤 품질 상태를 기대하는지
- 결과: judge가 본 실제 상태
- 감점 이유: 왜 1점이 아닌지
- Judge 요약: 짧은 판단 요약
- 참고 근거: judge가 참고한 source id 또는 짧은 근거

Judge prompt는 하나의 자연어 문장만 보내는 방식이 아니라, 아래 정보를 JSON으로 구성해 보냅니다.

- `judge_task`: 평가 metric 이름, 평가 지시문, 1.0/0.5/0.0 점수 기준, 중복 평가 금지 규칙
- `case`: dataset의 사용자 입력, 기대 claim 제한, 기대 근거 요구사항, 기대 품질, judge rubric, tags
- `workflow_result`: workflow final output에서 평가에 필요한 상품, 마케팅, QA, geo, retrieved documents, candidate evidence cards만 compact하게 추린 값

Judge response는 strict JSON schema를 따릅니다.

```json
{
  "score": 0.0,
  "passed": false,
  "actual": "judge가 본 실제 상태",
  "penalty_reason": "감점 이유",
  "judge_reasoning_summary": "짧은 판단 요약",
  "evidence_quotes_or_refs": ["doc:...", "product:..."]
}
```

Judge 호출은 workflow agent step을 새로 만들지 않습니다. 같은 workflow run의 `llm_calls`에는 `eval_product_quality_judge` 같은 별도 purpose로 기록되지만, 사용자용 실행 단계와 Workflow Preview에는 섞이지 않습니다. Evaluation report에는 judge metric과 요약만 저장합니다.

### Quality dataset

`quality` dataset은 초안이 아니라 LLM-as-a-Judge를 실제로 돌려 품질 회귀를 확인하기 위한 실행용 데이터셋입니다. smoke/regression이 "시스템이 깨졌는지"를 빠르게 잡는 데 가깝다면, quality는 "결과물이 상품으로 검토 가능한지, 근거를 잘 썼는지, 위험한 claim을 자연어 수준에서 피했는지"를 봅니다.

현재 포함하는 유형:

- 일반 관광 상품 품질
- 부산 야간 상품 차별성
- 웰니스 효능 claim 위험
- 반려동물 동반 claim 위험
- 이미지 사용권 claim 위험
- 혼잡/수요 signal claim 위험
- 오디오/스토리텔링 활용 품질
- 근거 부족 시 정직한 상품화

이 dataset은 대부분 live KTO API와 Gemini가 필요합니다. 따라서 정기 자동 실행보다는 릴리즈 전 수동 smoke 또는 nightly quality eval에 적합합니다.

## 실행 방법

```bash
conda activate paravoca-ax-agent-studio
cd backend
python -m app.evals.run_eval --dataset smoke --limit 5
python -m app.evals.run_eval --dataset smoke --name "Phase 13 live smoke 5 cases" --limit 5 --sleep-between-cases 5 --stop-on-first-failure
python -m app.evals.run_eval --dataset smoke --case-id smoke_daecheongdo_keyword --output-json
python -m app.evals.run_eval --dataset smoke --limit 3 --no-live-api
python -m app.evals.run_eval --dataset regression --case-id reg_geo_daecheongdo_not_cheongdo --sleep-between-cases 5
python -m app.evals.run_eval --dataset regression --name "Regression live" --sleep-between-cases 5
python -m app.evals.run_eval --dataset quality --name "Quality judge live" --enable-llm-judge --sleep-between-cases 5
python -m app.evals.run_eval --dataset quality --case-id quality_wellness_claim_risk --enable-llm-judge --sleep-between-cases 5 --output-json
```

`--name`은 Evaluation 화면에 표시할 실행명입니다. 지정하지 않으면 dataset 이름이 표시됩니다.

`--no-live-api`이거나 `TOURAPI_SERVICE_KEY`가 없으면 live API가 필요한 case는 `skipped`로 기록합니다. 실제 데이터를 꾸며내지 않습니다.

Runner는 case를 병렬 실행하지 않습니다. 각 case는 별도 DB session에서 하나의 workflow run을 실행하고 평가한 뒤 다음 case로 넘어갑니다. TourAPI/Gemini 호출 실패는 실제 run과 동일하게 tool call/agent step/run error에 남기며, 평가 metric은 그 실패를 성공처럼 보정하지 않습니다.

`--enable-llm-judge`는 workflow가 끝난 뒤 평가 단계에서만 judge를 실행합니다. workflow 실행 품질과 judge 실행 품질을 혼동하지 않기 위해 기본값은 `false`입니다.

## UI 원칙

Evaluation Dashboard는 AppShell의 `Evaluation` 메뉴에서 접근합니다.

표시 항목:

- 최근 eval runs
- pass/fail/skip summary
- 평균 score
- case별 결과 table
- 실패 reason
- score 1 미만 metric 진단 reason
- 연결된 workflow `run_id`
- latency/cost
- source family coverage
- case별 metric detail
- Developer JSON 접힌 영역

UI 정책:

- 실패 metric은 빨간색으로 표시합니다.
- score가 1 미만인 partial metric은 노란색으로 표시합니다.
- `not_applicable` metric은 `평가 제외` 또는 `-`를 회색으로 표시합니다.
- 각 metric에는 평가 주체 badge를 표시합니다.
  - 코드 검사
  - LLM 평가
  - 사람 평가 예정
- metric detail에는 기준, 실제 결과, 감점 이유, 다음 확인 항목을 표시합니다.
- LLM judge metric은 judge 요약과 참고 근거를 함께 표시합니다.
- Workflow Preview는 상품 생성 workflow의 실제 Agent와 의사결정 흐름만 표시합니다. Evaluation runner와 code metric은 Agent가 아니므로 Evaluation Dashboard에서만 다룹니다.
- 긴 reason 때문에 score badge가 밀리지 않도록 score 영역은 오른쪽에 고정합니다.
- raw JSON은 기본 정보보다 뒤에 둡니다.

## Roadmap

### P0: 현재 Phase 13에서 반드시 유지

- smoke dataset
- regression dataset
- controlled exit not_applicable 처리
- score 1 미만 진단 표시
- claim limit별 반영/미반영 표시
- metric별 평가 주체와 설명 필드
- LLM judge metric과 실행용 `quality` dataset
- Evaluation run과 일반 Dashboard run 분리
- linked workflow run 삭제 정책

### P1: 가까운 보강

- expected tool operation/argument 검사
- retrieval context precision/faithfulness 검사
- unsupported claim extraction
- region mismatch rate
- hallucinated place rate
- dropped off-region document count UI 표시
- LLM retry/timeout/truncation count metric

### P2: 품질 평가 확장

- LLM-as-judge 기반 product quality rubric 고도화
- 사람 평가 입력 화면
- pairwise evaluation
- pass@k/pass^k style 반복 실행 평가
- p50/p95 latency/cost trend

### P3: 운영 평가

P3는 실제 배포 후 사용자와 운영자가 시스템을 쓰기 시작해야 의미가 있습니다. 지금은 구현 대상이 아니라 운영 이후 계획으로 둡니다.

- online metric 연결
  - 저장률
  - 재생성률
  - 수정 요청률
  - 승인률
  - operator edit distance
  - 불만/신고율
- evaluation trend dashboard
- CI/nightly eval 분리

## 참고 자료

- OpenAI, Agent Evals: traces, graders, datasets, eval runs를 agent workflow 평가 surface로 제시합니다. https://developers.openai.com/api/docs/guides/agent-evals
- OpenAI, Trace Grading: agent trace에 structured score/label을 붙여 workflow-level issue를 찾는 방식입니다. https://developers.openai.com/api/docs/guides/trace-grading
- LangSmith, Application-specific evaluation approaches: agent overall task, single step, trajectory evaluation을 구분합니다. https://docs.langchain.com/langsmith/evaluation-approaches
- Ragas, Available Metrics: RAG 및 agent/tool-use metric 목록을 제공합니다. https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/
- tau-bench, A Benchmark for Tool-Agent-User Interaction in Real-World Domains: final database state와 goal state 비교, pass^k reliability 관점을 제시합니다. https://arxiv.org/abs/2406.12045
- WebArena, A Realistic Web Environment for Building Autonomous Agents: 재현 가능한 환경과 functional correctness 중심 평가를 제시합니다. https://arxiv.org/abs/2307.13854
- AgentBench, Evaluating LLMs as Agents: interactive environment에서 reasoning, decision-making, instruction following을 평가합니다. https://arxiv.org/abs/2308.03688
- NIST AI RMF / AI Research: trustworthy AI의 reliability, safety, security, transparency, privacy 관점을 제시합니다. https://www.nist.gov/ai-research
- 공공데이터포털, 한국관광공사 국문 관광정보 서비스: TourAPI 데이터 범위와 국내 관광정보 API 성격을 확인할 수 있습니다. https://www.data.go.kr/data/15101578/openapi.do
