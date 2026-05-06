# RAG, Guardrails, Evaluation 명세

## 목표

이 프로젝트가 운영형 AX 시스템으로 설득력을 가지려면 평가가 반드시 필요합니다.

평가 목표:

- 검색된 문서가 정답 근거를 포함하는지 확인
- 생성 답변이 검색 문서에 근거하는지 확인
- Agent가 올바른 도구를 호출했는지 확인
- workflow가 끝까지 성공했는지 확인
- 업무 1건당 비용을 측정
- latency를 측정
- 사람이 수정한 비율을 추적

## RAG 설계

### Retrieval 대상

- TourAPI 관광지 상세
- TourAPI 행사정보
- TourAPI 숙박정보
- TourAPI 이미지 metadata/license note
- 관광 수요 API summary
- 자체 운영 정책 문서
- 기존 상품/FAQ template

### Vector DB 선택

MVP:

- Chroma

P1:

- Qdrant

### Retrieval pipeline

```text
User request
  → query normalization
  → metadata filter
  → vector search
  → keyword search
  → reranking
  → context pack
  → generation
```

### Query normalization

입력:

```text
이번 달 부산에서 외국인 대상 액티비티 상품 5개
```

검색 query:

```text
부산 외국인 액티비티 야간 관광 축제 전통시장 해변 요트 체험
```

metadata filter:

```json
{
  "region_code": "6",
  "content_type": ["attraction", "event", "accommodation"],
  "date_overlap": {
    "start": "2026-05-01",
    "end": "2026-05-31"
  }
}
```

### Context pack 형식

LLM에 전달할 context는 짧고 구조화합니다.

```text
[SOURCE doc_123]
title: 광안리해수욕장
type: attraction
source: TourAPI
content_id: 12345
region: 부산
summary: ...
license_note: 이미지 사용 전 공공누리 유형 확인 필요

[SOURCE doc_456]
title: 부산 바다축제
type: event
event_period: 2026-05-10~2026-05-14
summary: ...
```

### Source citation rule

생성된 product item은 반드시 `source_ids` 배열을 포함합니다.

허용:

```json
"source_ids": ["doc_123", "doc_456"]
```

금지:

```json
"source_ids": []
```

source 없이 필요한 내용은 `assumptions`로 분리합니다.

## Guardrails

Guardrails는 "모델 호출 전", "모델 출력 후", "승인/저장 전" 세 지점에 둡니다.

### Pre-call guardrails

목적:

- 비싼 모델 호출 전 차단
- 부적절하거나 너무 넓은 요청 제한
- 필수 입력 정규화

체크:

- product_count <= 10
- region 존재
- date range <= 90일
- estimated cost <= budget
- prompt length <= model limit

### Tool guardrails

목적:

- 잘못된 tool argument 방지

체크:

- TourAPI region_code 형식
- 날짜 `YYYY-MM-DD`
- top_k <= 50
- external save tool은 approval 필요

### Output guardrails

목적:

- structured output 검증
- 출처 누락 방지
- 위험 표현 감지

체크:

- Pydantic schema validation
- required fields
- source_ids non-empty
- prohibited phrases
- date consistency
- price certainty
- event status certainty

### Approval guardrails

목적:

- 승인 전 외부 저장 방지

체크:

- run.status == awaiting_approval
- QA high severity issue 처리
- reviewer comment optional
- approved 후 export 실행

### Poster Studio guardrails

후속 Poster Studio에는 이미지 생성 전후 guardrail을 둡니다.

Pre-generation:

- 사용자가 poster prompt와 옵션을 확인했는지 확인
- selected_content에 가격, 예약 가능 여부, 운영 시간 단정 표현이 없는지 확인
- `not_to_claim`, QA issue, requested changes를 prompt constraint로 반영
- TourAPI 이미지를 참고하거나 재사용할 때 license note 확인
- image generation budget과 run당 생성 횟수 확인

Post-generation:

- 생성 이미지는 `needs_review` 상태로 저장
- 이미지 안 텍스트가 선택 문구와 일치하는지 사람이 확인
- 문구가 흐리거나 잘못 렌더링되면 재생성 또는 수동 편집 필요 표시
- 과장 표현, 안전 보장 표현, 브랜드/상표/인물 리스크 확인
- 승인 전 export 기본 비활성화

## Compliance rule examples

### 금지 표현

```json
[
  "100% 만족",
  "무조건",
  "항상 운영",
  "최저가 보장",
  "완전 안전",
  "예약 즉시 확정",
  "공식 인증된 최고의"
]
```

### 가격 표현 규칙

금지:

```text
1인 30,000원에 이용할 수 있습니다.
```

허용:

```text
가격은 운영 조건과 공급사 협의에 따라 확정해야 합니다.
```

### 날짜 표현 규칙

출처에 날짜가 있으면:

```text
TourAPI 기준 행사 기간은 2026-05-10부터 2026-05-14까지입니다.
```

출처가 불명확하면:

```text
행사 운영일은 공식 채널에서 최종 확인이 필요합니다.
```

## 평가 지표

| 평가 항목 | 측정 방법 | 보여주는 역량 |
|---|---|---|
| Retrieval Recall | 정답 문서가 top-k 검색 결과에 들어오는지 | Vector DB / IR 최적화 |
| Faithfulness | 답변이 검색된 문서에 근거하는지 | RAG 품질 관리 |
| Tool Call Accuracy | Agent가 맞는 API/tool을 호출했는지 | Agentic AI 통제 |
| Task Success Rate | 상품 기획/FAQ/검수 workflow가 끝까지 성공했는지 | 비즈니스 자동화 |
| Cost per Task | workflow 1건당 LLM 비용 | 운영 비용 감각 |
| Latency | workflow 완료 시간 | 프로덕션 고려 |
| Human Revision Rate | 사람이 고친 비율 | 실제 임팩트 측정 |
| Poster Prompt Acceptance | AI 추천 poster prompt를 사람이 얼마나 수정했는지 | 홍보 소재 자동화 품질 |
| Poster QA Pass Rate | 생성 포스터가 QA 검수를 통과한 비율 | 이미지 생성 결과 운영 가능성 |
| Poster Cost per Asset | 포스터 1장 생성 비용 | 이미지 생성 비용 관리 |

## Retrieval Recall

### Input

Eval case에 expected source ids를 넣습니다.

```json
{
  "case_id": "busan_night_market_001",
  "input": "부산 외국인 야간 푸드투어",
  "expected_source_ids": ["tourapi:content:12345", "tourapi:content:45678"]
}
```

### Calculation

```python
recall = len(set(retrieved_ids[:k]) & set(expected_ids)) / len(expected_ids)
```

기본:

- `k=10`
- pass threshold: `>= 0.7`

## Faithfulness

Ragas metric 또는 LLM judge를 사용합니다.

입력:

- question/request
- generated answer
- retrieved contexts

Pass 기준:

- MVP: `>= 0.75`
- P1: 상품별 field-level faithfulness

## Tool Call Accuracy

### Expected tools

Eval case마다 최소 호출되어야 하는 tool을 정의합니다.

```json
{
  "expected_tools": [
    "tourapi_area_code",
    "tourapi_area_based_list",
    "tourapi_search_festival"
  ]
}
```

### Calculation

```python
accuracy = matched_expected_tools / len(expected_tools)
```

추가로 잘못 호출한 tool에 penalty를 줄 수 있습니다.

예:

- 부산 요청인데 서울 region_code로 조회: fail
- 행사 우선 요청인데 festival search 누락: fail

## Task Success Rate

Workflow가 성공했다고 보는 조건:

- status가 `awaiting_approval` 또는 `approved`
- 요청한 product_count 충족
- product마다 title/source_ids/FAQ/QA status 존재
- fatal error 없음

```python
success = (
    run.status in ["awaiting_approval", "approved"]
    and len(products) == expected_count
    and all(product.source_ids for product in products)
    and all(product.faq for product in products)
)
```

## Cost per Task

LLM call logs를 합산합니다.

```python
cost_per_task = sum(llm_call.cost_usd for llm_call in run.llm_calls)
```

KRW 변환은 고정 환율 env를 사용합니다.

```env
USD_KRW_RATE=1400
```

Eval report에는 USD와 KRW를 모두 표시합니다.

## Latency

측정:

- workflow start to awaiting_approval
- agent step별 latency
- tool call latency
- LLM latency

목표:

- real TourAPI provider + low-cost LLM: 90초 이내

## Human Revision Rate

승인 전 사람이 수정한 field 비율입니다.

MVP에서는 간단히 사용자가 `request_changes` 또는 수동 편집을 했는지로 계산합니다.

P1에서는 diff 기반 계산:

```python
revision_rate = edited_fields / total_generated_fields
```

## Eval dataset 형식

JSONL:

```json
{"case_id":"busan_foreigner_001","input":{"message":"이번 달 부산에서 외국인 대상 액티비티 상품 5개","region":"부산","period":"2026-05","target_customer":"외국인","product_count":5},"expected_tools":["tourapi_area_code","tourapi_area_based_list","tourapi_search_festival"],"expected_source_keywords":["부산","야경","축제"],"expected_product_count":5}
```

## Eval report 형식

Markdown:

```markdown
# Eval Report 2026-05-05

## Summary
- Cases: 20
- Pass rate: 85%
- Avg retrieval recall: 0.78
- Avg faithfulness: 0.81
- Avg tool call accuracy: 0.90
- Avg cost per task: $0.012
- Avg latency: 43.2s

## Failures
...
```

JSON:

```json
{
  "eval_run_id": "eval_001",
  "summary": {
    "pass_rate": 0.85,
    "retrieval_recall": 0.78,
    "faithfulness": 0.81,
    "tool_call_accuracy": 0.9,
    "avg_cost_usd": 0.012,
    "avg_latency_ms": 43200
  },
  "cases": []
}
```

## CI 연동

MVP:

```bash
pytest backend/app/tests
python -m app.evals.run_eval --dataset app/evals/datasets/smoke.jsonl --sample-size 3
```

P1:

- pull request마다 smoke eval
- main branch nightly eval
- full eval은 수동 실행

## 실패 분석 taxonomy

Eval 실패는 다음 type으로 분류합니다.

- `retrieval_miss`
- `unsupported_claim`
- `wrong_tool`
- `schema_invalid`
- `budget_exceeded`
- `timeout`
- `approval_gate_failed`
- `qa_missed_risk`
- `product_count_mismatch`

## 평가 구현 우선순위

1. Deterministic 자체 지표 구현
   - tool call accuracy
   - task success
   - cost
   - latency

2. Retrieval recall 구현
   - expected source ids/keywords 기반

3. Ragas faithfulness/context recall 연동

4. DeepEval end-to-end/component eval 연동

5. Dashboard 표시
