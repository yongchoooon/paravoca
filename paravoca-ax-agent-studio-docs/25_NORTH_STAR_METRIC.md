# North Star Metric

작성 기준일: 2026-05-14

## 목적

이 문서는 PARAVOCA AX Agent Studio를 실제로 배포한 뒤 사용자의 사용 데이터를 바탕으로 제품 가치가 전달되고 있는지 측정하기 위한 North Star Metric과 입력 지표를 정의합니다.

기존 Phase 13 Evaluation Dashboard는 개발자가 workflow 품질, 지역 해석, 데이터 수집, RAG, claim 제한, 비용, latency를 진단하기 위한 내부 평가 레이어입니다. 이 문서의 지표는 그와 구분됩니다. 여기서 다루는 지표는 실제 여행사 직원, 상품 MD, 마케터, 콘텐츠 기획자가 PARAVOCA를 사용하면서 업무 결과물을 만들고 승인하는 행동을 기준으로 합니다.

## 제품 맥락

PARAVOCA AX Agent Studio는 공공 관광 데이터를 여행 상품 운영자의 업무 결과물로 바꾸는 AI workflow 시스템입니다.

사용자는 자연어로 지역, 기간, 타깃 고객, 선호 조건을 입력하고, 시스템은 다음 결과물을 하나의 workflow로 생성합니다.

- 관광 데이터 기반 상품 후보
- 상품 콘셉트와 코스
- 상세페이지 카피
- FAQ
- SNS/검색 키워드 등 마케팅 자산
- 운영 리스크와 QA 검수 결과
- 근거 문서와 확인 필요 항목

핵심 타깃은 여행사와 여행 플랫폼 운영자입니다. 확장 사용자는 여행상품 마케터, 상품 기획자, 지자체 관광 담당자, 직접 여행상품을 구성하려는 여행객입니다.

## Business Game

PARAVOCA는 **Productivity Game**에 해당합니다.

사용자의 체류 시간을 늘리는 Attention Game도 아니고, 예약/결제 거래 수를 직접 늘리는 Transaction Game도 아닙니다. PARAVOCA의 핵심 가치는 여행 상품 운영자가 리서치, 상품화, 카피 작성, FAQ 작성, 리스크 검수를 더 빠르고 일관되게 완료하도록 돕는 데 있습니다.

따라서 제품 성과는 사용자가 얼마나 오래 머물렀는지가 아니라, 사용자가 실제 업무에 사용할 수 있는 여행상품 초안을 얼마나 많이 만들고 승인했는지로 측정해야 합니다.

## North Star Metric

### 주간 승인 완료된 출시 준비 여행상품 수

**정의:** 1주 동안 사용자가 PARAVOCA로 생성한 결과 중, 근거 문서, 상품 콘셉트, 코스 또는 후보, 마케팅 셀링 포인트, FAQ, QA 검수 결과를 포함하고 사람이 `approve`한 여행상품 초안의 수입니다.

**계산식:**

```text
weekly_approved_launch_ready_products =
  count(products)
  where workflow_run.status = "approved"
    and product has source_ids
    and product has marketing_assets
    and product has qa_review
    and approved_at is within the target week
```

상품 단위로 세는 이유는 workflow run 하나가 여러 상품을 만들 수 있기 때문입니다. 예를 들어 사용자가 한 번의 요청으로 3개 상품을 만들고 그중 2개만 승인했다면 NSM에는 2가 반영됩니다.

## 왜 이 지표인가

이 지표는 단순 생성량이 아니라, 사용자가 실제 업무에 쓸 수 있다고 판단한 결과물의 수를 측정합니다.

PARAVOCA가 제공하는 핵심 가치는 다음 흐름 전체에 있습니다.

- 여행에서 고려해야 하는 지역, 기간, 타깃, 관광 자원, 운영 리스크를 한 번에 정리한다.
- 흩어진 공공 관광 데이터를 상품 후보와 코스로 묶는다.
- 여행사 직원이 판매에 활용할 수 있는 셀링 포인트와 마케팅 문구를 제공한다.
- 근거 문서와 확인 필요 항목을 함께 보여주어 AI 결과물을 바로 검토할 수 있게 한다.
- 사람이 최종 승인하는 Human-in-the-loop 흐름을 통해 실무 사용 가능성을 확인한다.

따라서 `주간 승인 완료된 출시 준비 여행상품 수`는 PARAVOCA가 공공 관광 데이터를 실제 상품 운영 결과물로 전환하고 있는지를 가장 직접적으로 보여줍니다.

## North Star Metric 검증

| 기준 | 검증 |
| --- | --- |
| Easy to Understand | 승인된 출시 준비 상품 수는 팀과 심사위원이 직관적으로 이해할 수 있습니다. |
| Customer-Centric | 사용자가 실제로 업무에 쓸 만하다고 승인한 결과물만 반영합니다. |
| Sustainable Value | 반복적으로 상품을 기획하고 승인할수록 제품의 업무 활용도가 높다는 뜻입니다. |
| Vision Alignment | 공공 관광 데이터를 여행사의 상품 운영 결과물로 전환한다는 제품 방향과 직접 연결됩니다. |
| Quantitative | 주간 단위로 상품 수를 명확히 집계할 수 있습니다. |
| Actionable | 데이터 품질, Agent 품질, UI, QA, 승인 UX 개선으로 직접 높일 수 있습니다. |
| Leading Indicator | 승인 상품이 늘어나면 향후 유료 전환, 조직 내 확산, 판매 연계 가능성이 커집니다. |

## Input Metrics

### 1. 상품 생성 성공률

**정의:** 전체 workflow run 중 사용자가 검토 가능한 `awaiting_approval` 상태까지 도달한 비율입니다.

```text
product_generation_success_rate =
  workflow_runs reaching "awaiting_approval"
  / workflow_runs started
```

**의미:** 지역 해석, TourAPI 수집, RAG 검색, Agent 실행, Product/Marketing/QA 생성이 안정적으로 이어지는지를 보여줍니다.

**개선 방향:** GeoResolver 실패율 감소, insufficient source data 안내 개선, Gemini JSON retry 안정화, TourAPI 호출 실패 대응, fallback이 아닌 명확한 사용자 안내 개선.

### 2. 승인 전환율

**정의:** `awaiting_approval` 상태에 도달한 run 또는 상품 중 사용자가 `approve`한 비율입니다.

```text
approval_conversion_rate =
  approved_products
  / products_presented_for_approval
```

**의미:** 생성된 결과물이 실제 업무에 사용할 만큼 충분한 품질인지 보여줍니다.

**개선 방향:** 상품 콘셉트 품질 개선, 마케팅 자산의 실무성 강화, QA issue 설명 개선, revision workflow 사용성 개선.

### 3. 상품당 근거 충족도

**정의:** 승인 후보 상품 1개가 충분한 근거 문서와 데이터 coverage를 갖추었는지 측정하는 지표입니다.

권장 구성:

```text
evidence_completeness_score =
  weighted score of:
    source_id_count
    required_source_family_coverage
    data_coverage.status
    unresolved_gap_count
    needs_review_count
```

**의미:** PARAVOCA가 공공 관광 데이터를 단순 참고 자료가 아니라 상품 생성의 근거로 잘 사용하고 있는지 보여줍니다.

**개선 방향:** KTO/TourAPI source family 확대, 상세 보강 호출 품질 개선, candidate evidence card 개선, source document 재색인 품질 개선.

### 4. 상품당 셀링 포인트 채택률

**정의:** 생성된 셀링 포인트, 상세페이지 카피, SNS 문구, 검색 키워드 중 사용자가 삭제하거나 크게 수정하지 않고 승인한 항목의 비율입니다.

```text
selling_point_adoption_rate =
  marketing_items_kept_until_approval
  / marketing_items_generated
```

**의미:** 여행사 직원이 이 상품을 어떻게 팔 수 있을지에 대한 인사이트를 PARAVOCA가 충분히 제공하는지 보여줍니다.

**개선 방향:** 타깃 고객별 소구점 개선, 지역/시즌성 반영 강화, 상품 유형별 카피 템플릿 개선, Marketing Agent prompt 개선.

### 5. 승인까지 걸린 평균 시간

**정의:** workflow run 생성 시점부터 승인 완료까지 걸린 평균 시간입니다.

```text
average_time_to_approval =
  avg(approved_at - workflow_run.created_at)
```

**의미:** PARAVOCA가 실제로 여행상품 기획 업무 시간을 줄이고 있는지 보여주는 생산성 지표입니다.

**개선 방향:** workflow latency 감소, 검토 UI 개선, evidence/QA 요약 개선, revision 횟수 감소, 승인 액션 동선 개선.

## 지표 관계

North Star Metric은 다음 입력 지표의 영향을 받습니다.

```text
주간 승인 완료된 출시 준비 여행상품 수
  = 생성 요청 수
  x 상품 생성 성공률
  x 검토 가능한 상품 수
  x 승인 전환율
  x 상품당 실무 채택 품질
```

입력 지표별 역할은 다음과 같습니다.

| Input Metric | 주로 설명하는 병목 |
| --- | --- |
| 상품 생성 성공률 | 시스템 실행 안정성과 데이터 수집 성공 여부 |
| 승인 전환율 | 생성 결과의 실무 품질 |
| 상품당 근거 충족도 | 공공 관광 데이터 활용성과 신뢰도 |
| 상품당 셀링 포인트 채택률 | 여행사/마케터가 느끼는 판매 인사이트 가치 |
| 승인까지 걸린 평균 시간 | 업무 생산성 개선 효과 |

## 수집해야 할 이벤트

배포 후 지표 측정을 위해 최소한 다음 이벤트를 수집합니다.

| Event | 발생 시점 | 주요 속성 |
| --- | --- | --- |
| `workflow_started` | 사용자가 상품 기획 실행 | `run_id`, `user_id`, `message`, `target_customer`, `product_count`, `period` |
| `workflow_completed_for_review` | run이 `awaiting_approval` 도달 | `run_id`, `product_count_generated`, `latency_ms`, `source_document_count` |
| `product_presented` | 사용자가 상품 초안 확인 | `run_id`, `product_id`, `source_id_count`, `marketing_item_count`, `qa_issue_count` |
| `product_edited` | 사용자가 상품/마케팅 문구 수정 | `run_id`, `product_id`, `edited_fields`, `edit_count` |
| `revision_requested` | 사용자가 수정 요청 | `run_id`, `revision_mode`, `requested_change_count`, `qa_issue_count` |
| `product_approved` | 사용자가 상품 승인 | `run_id`, `product_id`, `approved_at`, `kept_marketing_item_count` |
| `workflow_rejected` | 사용자가 결과 반려 | `run_id`, `reason`, `qa_issue_count`, `unresolved_gap_count` |

초기 버전에서는 별도 analytics 도구 없이도 DB의 `workflow_runs`, `approvals`, `revisions`, `tool_calls`, `llm_calls`, final output JSON을 기반으로 계산할 수 있습니다. 이후 실제 운영에서는 PostHog, Amplitude, Mixpanel 같은 product analytics 도구로 이벤트를 분리해도 됩니다.

## 공모전 발표용 해석

공모전에서는 이 지표 체계를 다음처럼 설명할 수 있습니다.

PARAVOCA의 핵심 성과 지표는 `주간 승인 완료된 출시 준비 여행상품 수`입니다. 이는 AI가 단순히 많은 문장을 생성했는지가 아니라, 공공 관광 데이터를 기반으로 만든 상품 초안이 여행사 직원에게 실제 업무 산출물로 승인되었는지를 측정합니다.

입력 지표는 생성 성공률, 승인 전환율, 근거 충족도, 셀링 포인트 채택률, 승인까지 걸린 시간으로 구성됩니다. 이 지표들은 각각 시스템 안정성, 결과 품질, 공공데이터 활용성, 마케팅 인사이트 가치, 업무 생산성 개선 효과를 보여줍니다.

즉 PARAVOCA는 배포 이후에도 단순 사용량이 아니라, "공공 관광 데이터가 얼마나 많은 실무형 여행상품으로 전환되었는가"를 기준으로 제품 가치를 평가할 수 있습니다.

## Phase 13 Evaluation과의 차이

| 구분 | Phase 13 Evaluation | North Star Metric |
| --- | --- | --- |
| 목적 | 개발/운영자가 workflow 품질을 진단 | 실제 사용자가 얻는 제품 가치를 측정 |
| 대상 | 테스트 케이스, eval dataset, run 결과 | 실제 사용자 행동, 승인, 수정, 채택 |
| 주요 지표 | geo accuracy, retrieval count, claim compliance, latency, cost | 승인 상품 수, 승인 전환율, 셀링 포인트 채택률, 승인 시간 |
| 사용 시점 | 배포 전후 품질 점검, regression 확인 | 배포 후 제품 성장과 고객 가치 확인 |
| 의사결정 | 버그 수정, Agent 개선, 데이터 보강 | 제품 방향, 고객 세그먼트, 유료화, 기능 우선순위 |

두 지표 체계는 경쟁 관계가 아니라 상호 보완 관계입니다. Phase 13 Evaluation이 시스템이 올바르게 동작하는지를 확인한다면, North Star Metric은 그 시스템이 실제 사용자에게 반복적으로 가치 있는 결과물을 만들고 있는지를 확인합니다.
