# 비용, 결제, 사용량 설계

## 문서 범위

이 문서는 두 가지 비용/결제 문제를 다룹니다.

1. 프로젝트 운영 비용
   - LLM API, image generation API, embedding, vector DB, hosting 비용을 월 3만 원 내외로 통제하는 설계

2. SaaS 결제 설계
   - 나중에 이 시스템을 유료 SaaS처럼 확장할 경우의 플랜, 사용량 제한, Toss Payments/Stripe 연동 방식

MVP에서는 실제 고객 결제를 구현하지 않습니다. 대신 비용 추적과 과금 모델을 설계하고, 결제 provider 연동은 P2 범위로 둡니다.

## 운영 비용 원칙

핵심 원칙:

- 비싼 모델을 기본값으로 쓰지 않습니다.
- Agent마다 모델 tier를 나눕니다.
- eval은 작은 샘플로 먼저 실행합니다.
- 대량 eval은 batch API를 사용합니다.
- embedding은 저가 API 또는 로컬 CPU 모델을 우선 고려합니다.
- 모든 LLM 호출은 Gemini gateway를 통해 비용을 기록합니다.
- Poster Studio의 이미지 생성 호출은 별도 image generation usage log로 기록합니다.

## 가격 기준 메모

작성 기준일: 2026-05-06

가격은 변동 가능성이 높으므로 실제 구현 직전 공식 가격 페이지를 재확인해야 합니다. 문서 작성 시 확인한 공식 출처는 다음과 같습니다.

- Gemini pricing: https://ai.google.dev/pricing
- Google Cloud Gemini pricing: https://cloud.google.com/vertex-ai/generative-ai/pricing
- Grounding with Google Search: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search
- Grounding with your search API: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-your-search-api
- OpenAI Image generation: https://developers.openai.com/api/docs/guides/image-generation

확인한 방향성:

- Gemini Developer API는 Free/Paid tier를 나누고, 일부 저가 모델은 1M tokens 단위로 낮은 가격대를 제공합니다.
이 프로젝트의 현재 workflow LLM provider는 Gemini만 대상으로 합니다. OpenAI/GPT는 향후 비교 또는 확장 후보로만 남기고, 현재 구현과 운영 문서에서는 사용하지 않습니다.
- 후속 Poster Studio의 이미지 생성 provider 후보는 OpenAI Image API이며, 현재 공식 문서 기준 기본 후보 모델은 `gpt-image-2`입니다.
- Google Cloud 가격표 기준으로 Gemini 2.0 Flash, 2.5 Flash, 2.5 Flash-Lite 계열의 Google Search grounding은 combined 1,500 grounded prompts/day가 추가 비용 없이 제공되고, 초과분은 $35/1,000 grounded prompts로 안내됩니다.
- 같은 가격표에서 grounded prompt는 Gemini 요청 1회가 Google Search에 하나 이상의 query를 보내는 경우를 의미하며, 한 prompt 안에서 여러 Google Search query가 생성되어도 grounded prompt 비용은 1회로 계산된다고 설명합니다.
- Gemini 3 계열의 Grounding with Google Search는 billing이 Gemini가 생성해 Search로 보낸 각 search query 단위로 발생할 수 있으므로, Gemini 2.0/2.5 Flash 계열과 같은 비용 가정으로 계산하지 않습니다.
- 검색 grounding 추가 요금은 모델 token 비용과 별도입니다. 검색 결과가 프롬프트/context에 포함되면 입력 token 비용도 함께 증가할 수 있습니다.

정확한 모델명과 가격은 개발 시점에 `.env` 또는 설정 파일에 넣고, 하드코딩하지 않습니다.

## 모델 tier 설계

### cheap tier

용도:

- 날짜/지역 정규화
- 간단 분류
- tool argument 생성
- QA rule 후보 판정
- 간단 요약

후보:

- Gemini Flash-Lite 계열
- 로컬 모델 가능 시 로컬

### standard tier

용도:

- Research summary
- Product idea generation
- Marketing copy generation
- QA LLM judge

후보:

- Gemini Flash 계열

### premium tier

용도:

- 최종 데모용 고품질 생성
- 복잡한 compliance judge
- 포트폴리오 녹화용 run

후보:

- Gemini 고성능 계열 또는 향후 비교용 모델

정책:

- premium tier는 기본 비활성화
- 사용자 설정에서 "high quality mode"일 때만 사용
- daily/monthly budget 초과 시 자동 차단

### image generation tier

용도:

- Poster Studio 포스터 이미지 생성
- 포스터 variant 재생성
- approved poster asset 저장 전 preview 생성

후보:

- `gpt-image-2`
- `gpt-image-1.5`
- `gpt-image-1`
- `gpt-image-1-mini`

정책:

- 기본 비활성화
- 사용자가 문구와 옵션을 확인한 뒤에만 호출
- run당 poster generation 횟수 제한
- daily/monthly image budget 별도 관리
- 생성 실패나 재생성도 비용이 발생할 수 있으므로 preview 단계에서 경고 표시

## Agent별 비용 정책

| 단계 | 모델 tier | 비용 최적화 |
|---|---|---|
| Planner | cheap | structured JSON, 짧은 prompt |
| Data Agent | cheap/no LLM | 가능한 deterministic tool call |
| Data Agent web enrichment | no LLM/search tool | 기본 비활성화, run당 query 제한 |
| Research | standard | context top_k 제한 |
| Product | standard | 상품 수 최대 10 제한 |
| Marketing | standard | 상품별 병렬 대신 batch prompt 고려 |
| QA rule | no LLM | 정규식/규칙 먼저 |
| QA judge | cheap/standard | rule에서 의심된 항목만 judge |
| Poster Prompt | standard | run 결과 요약만 사용, source 원문 전체 제외 |
| Poster Image | image generation | 사용자 확인 뒤 호출, run당 생성 수 제한 |
| Poster QA | cheap/standard | 이미지 문구와 리스크만 검수 |
| Eval | cheap/batch | sample 10→50→100 단계적 확대 |

## 비용 추적 스키마

LLM call마다 저장:

```json
{
  "run_id": "run_001",
  "step_id": "step_product",
  "provider": "gemini",
  "model": "model-name",
  "purpose": "product_generation",
  "input_tokens": 12000,
  "output_tokens": 3500,
  "cost_usd": 0.015,
  "latency_ms": 8200
}
```

Workflow run 집계:

```json
{
  "run_id": "run_001",
  "total_cost_usd": 0.043,
  "total_cost_krw": 60.2,
  "llm_calls": 8,
  "tool_calls": 12,
  "grounded_prompts": 1,
  "web_search_queries": 3,
  "latency_ms": 52100
}
```

P2 이후 검색 tool 비용도 저장합니다.

```json
{
  "run_id": "run_001",
  "tool_name": "google_search_grounding",
  "provider": "gemini",
  "grounded_prompts": 1,
  "search_queries_generated": 3,
  "estimated_overage_cost_usd": 0.035,
  "pricing_note": "Gemini 2.0/2.5 Flash 계열은 grounded prompt 기준, Gemini 3 계열은 query 단위 과금 가능"
}
```

Poster Studio image generation call마다 저장:

```json
{
  "poster_id": "poster_001",
  "run_id": "run_001",
  "product_id": "product_1",
  "provider": "openai",
  "model": "gpt-image-2",
  "purpose": "poster_generation",
  "size": "auto",
  "quality": "medium",
  "format": "png",
  "estimated_output_tokens": 0,
  "cost_usd": 0.0,
  "latency_ms": 45000,
  "pricing_note": "OpenAI 공식 가격과 image output token 계산 기준을 구현 직전에 재확인"
}
```

## 비용 계산 방식

가격 설정 파일:

```yaml
models:
  cheap_default:
    provider: gemini
    model: gemini-cheap-placeholder
    input_per_1m_usd: 0.10
    output_per_1m_usd: 0.40
  standard_default:
    provider: gemini
    model: gemini-standard-placeholder
    input_per_1m_usd: 0.75
    output_per_1m_usd: 4.50
  poster_image_default:
    provider: openai
    model: gpt-image-2
    pricing_mode: image_output_tokens
    quality: medium
    size: auto
```

주의:

- 실제 모델명과 단가는 공식 가격 페이지 재확인 후 수정합니다.
- 현재 구현은 Gemini 2.5 Flash-Lite paid tier 기준 local price table로 예상 비용을 계산합니다.

직접 계산:

```python
cost = (input_tokens / 1_000_000) * input_per_1m_usd
cost += (output_tokens / 1_000_000) * output_per_1m_usd
```

## 월 3만 원 내외 운영 시나리오

가정:

- 환율: 1 USD = 1,400 KRW
- 월 예산: 30,000 KRW = 약 21.4 USD
- 일반 workflow 1회 평균 비용 목표: 50~150 KRW
- eval은 작은 샘플 위주

예산 배분:

| 항목 | 월 예산 |
|---|---:|
| 개발/테스트 LLM 호출 | 10,000 KRW |
| 데모용 고품질 run | 5,000 KRW |
| 평가 자동화 | 8,000 KRW |
| embedding/API 여유분 | 3,000 KRW |
| 예비 | 4,000 KRW |

운영 규칙:

- 하루 budget soft limit: 1,000 KRW
- 하루 budget hard limit: 2,000 KRW
- workflow 1회 hard limit: 300 KRW
- eval run 1회 hard limit: 3,000 KRW
- premium model daily call limit: 10회
- poster image generation daily soft limit: 5회
- poster image generation run당 hard limit: 3회

## 비용 절감 전략

### 1. Prompt 압축

- TourAPI raw JSON 전체를 LLM에 넣지 않습니다.
- 필요한 field만 source context로 전달합니다.
- image URL, raw metadata는 LLM에 불필요하면 제외합니다.

### 2. Context top_k 제한

기본:

- Data retrieval top_k: 20
- LLM context top_k: 8
- 상품별 source max: 5

### 3. Rule-first QA

금지 표현, source_ids 누락, 날짜 format 오류는 LLM 없이 검사합니다.

### 4. Cache

- 같은 input hash에 대한 LLM 결과 cache optional
- API response cache
- embedding cache

### 5. Batch eval

대량 평가를 동기 API로 돌리지 않습니다. provider가 batch API를 지원하면 batch를 사용합니다.

### 6. Low-cost eval

개발 중에도 관광 데이터는 실제 TourAPI를 호출합니다. 평가 데이터셋은 작은 sample로 제한하고, LLM은 저가 모델 또는 비활성 모드로 비용을 통제합니다.

### 7. 웹 검색/grounding 제한

웹 검색 보강은 TourAPI 데이터만으로 상품화/검증 근거가 부족할 때만 실행합니다.

- 기본값: `WEB_SEARCH_ENABLED=false`
- workflow run당 기본 query budget: 0
- 운영자 요청 또는 P2 설정에서만 `max_web_queries_per_run` 허용
- 같은 query/region/period 조합은 cache 우선 사용
- 공식 출처 URL이 없거나 snippet만 있는 결과는 확정 근거로 사용하지 않음
- 검색 결과를 그대로 긴 context로 넣지 않고, 필요한 필드와 링크만 요약해 전달

Gemini Google Search grounding을 사용할 경우 비용 추정 단위:

```text
Gemini 2.0/2.5 Flash 계열:
  grounded_prompt_count = Google Search grounding을 사용해 웹 결과 URL이 반환된 Gemini 요청 수

Gemini 3 계열:
  billable_search_query_count = Gemini가 생성해 Search로 보낸 query 수
```

비용 예시:

```text
Data Agent에서 workflow run 1회당 grounding 호출 1번
→ Gemini 2.0/2.5 Flash 계열 기준 grounded_prompts = 1

Product/Marketing/QA 각각 grounding 호출
→ grounded_prompts = 3
```

운영 정책상 초기 구현은 Data Agent에서만 웹 보강을 수행하고, downstream Agent는 저장된 `source=web` 문서를 읽도록 설계합니다. 이렇게 하면 workflow run당 검색 grounding 횟수를 1회 내외로 제한할 수 있습니다.

## 예산 guard 구현

환경변수:

```env
DAILY_BUDGET_KRW=1000
MONTHLY_BUDGET_KRW=30000
WORKFLOW_BUDGET_KRW=300
EVAL_RUN_BUDGET_KRW=3000
WEB_SEARCH_ENABLED=false
MAX_WEB_QUERIES_PER_RUN=0
MAX_GROUNDED_PROMPTS_PER_RUN=0
USD_KRW_RATE=1400
PREMIUM_MODEL_ENABLED=false
```

Budget guard:

```python
class BudgetGuard:
    def assert_can_call(self, estimated_cost_usd: Decimal, scope: BudgetScope) -> None:
        ...
```

차단 시:

```json
{
  "status": "blocked_by_budget",
  "message": "Estimated workflow cost exceeds budget. Use cheap mode or reduce product_count."
}
```

## SaaS 플랜 설계

MVP에서는 구현하지 않지만, 포트폴리오 문서에는 비즈니스 모델을 보여주기 위해 포함합니다.

### 플랜 예시

| Plan | 월 가격 | 포함량 | 대상 |
|---|---:|---|---|
| Demo | 무료 | rule-based workflow 20회, export 제한 | 포트폴리오/체험 |
| Starter | 29,000 KRW | workflow 100회, eval 10회 | 소규모 운영자 |
| Pro | 99,000 KRW | workflow 500회, eval 50회, Google Sheets export | 여행사/플랫폼 팀 |
| Team | 299,000 KRW | workflow 2,000회, 팀 권한, audit log | 운영 조직 |

주의:

- 실제 원가와 provider 가격을 반영해 조정해야 합니다.
- LLM 사용량이 큰 고객은 overage를 별도 부과해야 합니다.

### 사용량 단위

과금/제한 단위:

- workflow run
- generated product count
- eval case count
- premium model call
- vector document count
- export call
- team seat

## Toss Payments 연동 옵션

한국 내 SaaS 결제라면 Toss Payments를 고려할 수 있습니다.

공식 문서 기준 주요 선택지:

- 결제위젯
- 결제창
- 자동결제(빌링)

자동결제(빌링)는 최초 카드 등록 후 빌링키로 정기 결제를 수행하는 구조입니다. 문서상 추가 리스크 검토 및 계약이 필요할 수 있으므로, MVP에서는 실제 자동결제를 넣지 않습니다.

연동 흐름 P2:

1. Pricing page에서 plan 선택
2. Backend가 order/subscription intent 생성
3. Frontend가 Toss Payments 결제위젯 또는 billing auth 호출
4. successUrl/failUrl 처리
5. Backend가 결제 승인 또는 billing key 저장
6. webhook으로 결제 상태 동기화
7. subscription entitlement 업데이트

저장 필드:

```text
subscriptions
  id
  user_id
  plan_id
  provider = toss
  provider_customer_key
  billing_key_encrypted
  status
  current_period_start
  current_period_end
```

보안:

- billing key는 암호화 저장
- secret key는 backend env에만 저장
- webhook signature 검증
- 결제 실패/취소/환불 상태 처리

## Stripe 연동 옵션

글로벌 SaaS 또는 외국인 운영자 대상이면 Stripe Billing을 고려합니다.

Stripe Checkout + Billing 흐름:

1. Stripe Dashboard에서 Product/Price 생성
2. Backend `POST /billing/create-checkout-session`
3. Frontend redirect to Checkout
4. `checkout.session.completed` webhook 수신
5. subscription status 저장
6. Customer Portal로 구독 변경/카드 변경 제공

필수 webhook:

- `checkout.session.completed`
- `invoice.paid`
- `invoice.payment_failed`
- `customer.subscription.updated`
- `customer.subscription.deleted`

MVP에서는 Stripe/Toss 모두 billing simulation으로 대체합니다.

## MVP Billing 구현

실결제 없이 다음만 구현합니다.

### Plan model

```json
{
  "plan": "demo",
  "monthly_workflow_limit": 100,
  "monthly_eval_limit": 10,
  "premium_model_enabled": false
}
```

### Usage limit check

workflow 실행 전:

- 월 workflow limit 확인
- budget 확인
- premium model 권한 확인

### Billing dashboard

표시:

- current plan
- monthly runs used
- eval cases used
- estimated cost
- reset date

## Cost/Billing acceptance 기준

MVP:

- workflow run마다 total cost가 계산됩니다.
- cost dashboard에서 run별/model별 비용이 보입니다.
- budget 초과 시 expensive model 호출이 차단됩니다.
- local plan limit이 적용됩니다.

P2:

- Toss 또는 Stripe test mode 결제가 동작합니다.
- webhook으로 subscription status가 갱신됩니다.
- plan limit과 payment status가 권한에 반영됩니다.
