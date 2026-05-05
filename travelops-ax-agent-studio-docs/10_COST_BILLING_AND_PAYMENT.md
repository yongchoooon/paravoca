# 비용, 결제, 사용량 설계

## 문서 범위

이 문서는 두 가지 비용/결제 문제를 다룹니다.

1. 프로젝트 운영 비용
   - LLM API, embedding, vector DB, hosting 비용을 월 3만 원 내외로 통제하는 설계

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
- 모든 LLM 호출은 LiteLLM을 통해 비용을 기록합니다.

## 가격 기준 메모

작성 기준일: 2026-05-05

가격은 변동 가능성이 높으므로 실제 구현 직전 공식 가격 페이지를 재확인해야 합니다. 문서 작성 시 확인한 공식 출처는 다음과 같습니다.

- OpenAI pricing: https://openai.com/api/pricing/
- Gemini pricing: https://ai.google.dev/pricing
- Claude pricing: https://platform.claude.com/docs/en/about-claude/pricing

확인한 방향성:

- OpenAI API 가격 페이지는 Batch processing mode에서 비용 절감 옵션을 제공합니다.
- Gemini Developer API는 Free/Paid tier를 나누고, 일부 저가 모델은 1M tokens 단위로 낮은 가격대를 제공합니다.
- Claude pricing은 Haiku/Sonnet/Opus 계열의 input/output MTok 단가를 공개합니다.

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
- OpenAI mini/nano 계열
- Claude Haiku 계열
- 로컬 모델 가능 시 로컬

### standard tier

용도:

- Research summary
- Product idea generation
- Marketing copy generation
- QA LLM judge

후보:

- Gemini Flash 계열
- OpenAI mini급/일반급
- Claude Haiku/Sonnet 소량

### premium tier

용도:

- 최종 데모용 고품질 생성
- 복잡한 compliance judge
- 포트폴리오 녹화용 run

후보:

- Claude Sonnet 계열
- GPT 고성능 계열

정책:

- premium tier는 기본 비활성화
- 사용자 설정에서 "high quality mode"일 때만 사용
- daily/monthly budget 초과 시 자동 차단

## Agent별 비용 정책

| 단계 | 모델 tier | 비용 최적화 |
|---|---|---|
| Planner | cheap | structured JSON, 짧은 prompt |
| Data Agent | cheap/no LLM | 가능한 deterministic tool call |
| Research | standard | context top_k 제한 |
| Product | standard | 상품 수 최대 10 제한 |
| Marketing | standard | 상품별 병렬 대신 batch prompt 고려 |
| QA rule | no LLM | 정규식/규칙 먼저 |
| QA judge | cheap/standard | rule에서 의심된 항목만 judge |
| Eval | cheap/batch | sample 10→50→100 단계적 확대 |

## 비용 추적 스키마

LLM call마다 저장:

```json
{
  "run_id": "run_001",
  "step_id": "step_product",
  "provider": "openai",
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
  "latency_ms": 52100
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
    provider: openai
    model: openai-standard-placeholder
    input_per_1m_usd: 0.75
    output_per_1m_usd: 4.50
```

주의:

- 실제 모델명과 단가는 공식 가격 페이지 재확인 후 수정합니다.
- LiteLLM이 제공하는 비용 계산 기능을 우선 사용하고, 누락 모델은 local price table을 보완합니다.

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

### 6. Mock provider eval

개발 중에는 TourAPI와 LLM 일부를 mock으로 대체해 workflow logic을 테스트합니다.

## 예산 guard 구현

환경변수:

```env
DAILY_BUDGET_KRW=1000
MONTHLY_BUDGET_KRW=30000
WORKFLOW_BUDGET_KRW=300
EVAL_RUN_BUDGET_KRW=3000
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
| Demo | 무료 | mock workflow 20회, export 제한 | 포트폴리오/체험 |
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

MVP에서는 Stripe/Toss 모두 mock billing으로 대체합니다.

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
- mock plan limit이 적용됩니다.

P2:

- Toss 또는 Stripe test mode 결제가 동작합니다.
- webhook으로 subscription status가 갱신됩니다.
- plan limit과 payment status가 권한에 반영됩니다.

