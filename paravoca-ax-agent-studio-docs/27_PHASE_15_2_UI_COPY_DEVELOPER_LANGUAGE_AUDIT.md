# Phase 15.2 UI Copy and Developer Language Cleanup Audit

Scope: audit user-facing UI copy and developer/internal terminology exposure. This section does not implement UI changes. Poster quality is excluded; Poster Studio is reviewed only for copy and metadata exposure.

Data read:

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/RunDetail.tsx`
- `frontend/src/pages/RunLogs.tsx`
- `frontend/src/pages/runDetailUtils.ts`
- `frontend/src/pages/EvaluationDashboard/EvaluationDashboard.tsx`
- `frontend/src/pages/PosterStudio.tsx`
- `frontend/src/pages/DataSourcesPanel.tsx`
- `frontend/src/services/postersApi.ts`
- `frontend/src/services/runsApi.ts`
- `frontend/src/services/evaluationsApi.ts`
- `paravoca-ax-agent-studio-docs/27_PHASE_15_0_A_RUN_OUTPUT_INVENTORY.md`
- `paravoca-ax-agent-studio-docs/27_PHASE_15_0_B_QA_QUALITY_ANALYSIS.md`
- `paravoca-ax-agent-studio-docs/27_PHASE_15_0_D_EVIDENCE_RAG_FLOW_ANALYSIS.md`
- `paravoca-ax-agent-studio-docs/27_PHASE_15_1_AI_REVISION_QA_REGRESSION_ANALYSIS.md`

## User-facing Developer Language Inventory

| Term / copy | Current surface | Example | Why problematic | Recommended action |
| --- | --- | --- | --- | --- |
| Agent names | Dashboard workflow, Run Detail stage view, Developer logs | `GeoResolver`, `BaselineDataAgent`, `EvidenceFusionAgent`, `QAComplianceAgent` | Useful to engineers, but operators need the business step, not class names. | Rename in normal UI; keep raw agent names in Developer. |
| `Gemini` in workflow labels | Dashboard workflow, Run Detail stage labels | `Gemini Planner`, `Gemini Research`, `Gemini Gap` | Provider name is implementation detail unless the user is inspecting model usage/cost. | Rename to task labels; keep provider in Developer/cost views. |
| `API Router`, `Detail Planner`, `Visual Planner`, `Route Planner`, `Theme Planner` | Dashboard workflow | Planner/router terms describe architecture, not user task outcome. | Rename to “추가 데이터 판단”, “상세정보 확인”, “사진 후보 확인”, etc. |
| `Data Gap`, `gap`, `gap_type` | Dashboard workflow, Evidence coverage, Data Sources, docs-derived QA | `Data Gap`, `missing_pet_policy`, `missing_detail_info` | “Gap” is internal classification. It should become user-facing “확인 필요 정보”. | Rename in normal UI; raw gap type only in Developer. |
| `source_id`, `source_ids`, `doc_id` | Product QA messages, Evidence/RAG diagnostics, Developer logs | `doc:tourapi:content:2760809` | Internal document ids are not meaningful to operators and can distract from actual evidence mismatch. | Hide by default; show source title instead; ids only in Developer. |
| Source-id correction/fallback messages | Product `needs_review`, QA issues | `모델이 실제 근거 목록에 없는 source id를 반환해 서버에서 제외했습니다.` | Directly exposes server repair behavior and model failure. It is diagnostic, not user guidance. | Move to Developer; show user copy as “상품과 근거 연결을 다시 확인하세요.” only if actionable. |
| `claim_limits` | Poster options, Product detail, evaluation/docs | `Claim 제한/주의사항` | “Claim” is semi-internal and mixes legal/evidence risk with marketing copy. | Rename to “표현 제한/주의사항” or “단정 금지 항목”. |
| `needs_review` | Product detail content, QA regression | `missing_pet_policy 근거가 부족해 운영자 확인이 필요합니다.` | The field is an internal holding bucket; contents can be raw diagnostics. | Keep only normalized Korean notes in user UI; raw entries move to Developer. |
| `not_to_claim` | Product detail Claims tab | `Do not claim` | English/internal schema term. | Rename to “단정하면 안 되는 내용”. |
| `Assumptions` | Product detail Claims tab | `Assumptions` | Internal generation field; can be useful but needs Korean label and explanation. | Rename to “운영 가정”. |
| `Coverage note` | Product detail evidence state | `Coverage note` | Internal coverage language. | Rename to “근거 범위 메모” or move low-value notes to Developer. |
| QA table headers | Run Detail QA section | `QA Review`, `Product`, `Severity`, `Type`, `Message`, `Suggested fix` | Mixed English/Korean and generic developer schema labels. | Rename to Korean operational labels. |
| Raw QA status | Run Detail QA summary | `pass`, `needs_review`, raw `overall_status` badge | Status values are backend enum values. | Map to Korean: “통과”, “확인 필요”, “실패”. |
| Raw QA type | QA issues | `general`, `source_missing`, `avoid_rule` | Some are mapped, but `general` collapses too much and hides the issue class. | Use product labels like “표현 점검”, “근거 연결”, “회피 조건”. |
| `field_path` / schema path | QA messages and revision request text | `sales_copy.sections[0].body`, `needs_review[2]` | Internal JSON path leaks into user text and makes the issue hard to understand. | Never show in normal UI; convert to “상세 설명”, “FAQ 답변”, etc. |
| “추천 보강 호출” | Run Detail Evidence section | Section title for enrichment call rows | “추천” implies optional recommendation, but it actually lists executed/skipped data enrichment calls. | Rename to “추가 데이터 확인 내역” or “데이터 보강 내역”. |
| `tool_name` / raw tool call | Developer logs, some tables through labels | `kto_tour_detail_enrichment`, `vector_search_post_enrichment` | Raw function names are not user concepts. | Developer only; use Korean source/action labels elsewhere. |
| Provider/model/purpose | RunLogs, Evaluation, cost/debug views | `gemini-2.5-flash-lite`, `qa_review`, `revision_patch` | Valuable for cost/debug, not for the main review flow. | Keep in Developer/cost areas; hide from product review. |
| `P / F / S`, passed/failed/skipped | Evaluation list | `P 1`, `F 0`, `S 0`, `passed` | Compact developer/test notation. | Rename to “통과/실패/제외”; raw status only in detail. |
| `Dataset`, `Case`, `Metric detail`, `Developer JSON` | Evaluation Dashboard | English test/report terms | Evaluation users still need operational meaning. | Rename to Korean labels; keep JSON behind Developer. |
| `source_family` | Evaluation coverage and Data Sources | `kto_tourapi_kor: covered` | Internal source taxonomy. | Map to Korean source names and state labels. |
| `failed` badge | Poster Studio and Run Detail poster cards | `failed` | English raw enum. | Rename to “생성 실패”. |
| `run_id` | Poster Studio cards, Evaluation case detail | `run_f...` | Useful for traceability, but should not be the primary label. | Show task title first; id secondary/copyable or Developer. |
| Poster provider error details | Poster failure cards / alerts | OpenAI billing/provider messages | Error cause is useful in development but can be too raw for normal UI. | User message summarized; raw provider details in Developer/error detail. |

## Screen-level Copy Audit

### Dashboard

Current issues:

- Header and table still use English product labels: `Dashboard`, `New run`, `Workflow runs`, `Awaiting approval`, `Templates`, `Task`, `Status`, `Geo`, `Products`, `Posters`, `Revisions`, `Created`, `Action`.
- Workflow Preview exposes architecture labels: `Gemini Planner`, `GeoResolver`, `Baseline Data`, `Data Gap`, `API Router`, `Evidence Fusion`, `Gemini Research`, `Product`, `Marketing`, `QA`, `Approval`.
- The workflow explanation says “agent 실행 흐름” and “조건부 데이터 보강 경로”, which is useful for engineering but too implementation-centered for normal operators.
- Settings placeholder includes `feature flag`, `Agent별 token budget`, and “사용자용/개발자용 workflow 표시 수준 설정”.

Recommended user copy:

- `Dashboard` -> `작업 현황`
- `New run` -> `새 상품 기획`
- `Workflow runs` -> `실행한 기획`
- `Awaiting approval` -> `검토 대기`
- `Templates` -> `작업 템플릿`
- `Workflow Preview` -> `작업 흐름`
- `Gemini Planner` -> `요청 정리`
- `GeoResolver` -> `지역 확인`
- `Baseline Data` -> `기본 관광 데이터 수집`
- `Data Gap` -> `부족한 정보 확인`
- `API Router` -> `추가 데이터 판단`
- `Evidence Fusion` -> `근거 정리`
- `Gemini Research` -> `상품 기획 근거 요약`
- `Product` -> `상품 초안`
- `Marketing` -> `홍보 문구`
- `QA` -> `검수`
- `Approval` -> `승인 검토`

### Run Detail

Current issues:

- Main empty/error copy includes English: `No generated product result`, `Workflow output`, `Developer 탭`.
- Evidence tab says `Selected product only`.
- Product metrics use `Target`, `Duration`, `Difficulty`.
- Product tabs use `Sales Copy`, `Claims`.
- Claims tab uses `Assumptions` and `Do not claim`.
- Evidence summary shows `claim 제한`, `Coverage note`, and `Visual API`.
- Product `needs_review` can include raw diagnostic text such as source-id fallback/correction.
- Poster cards show raw `failed`.

Recommended user copy:

- `No generated product result` -> `생성된 상품 결과가 없습니다`
- `Workflow output` -> `상품 결과`
- `Selected product only` -> `선택한 상품 근거만 보기`
- `Target` -> `대상 고객`
- `Duration` -> `소요 시간`
- `Difficulty` -> `운영 난이도`
- `Sales Copy` -> `판매 문구`
- `Claims` -> `표현 점검`
- `Assumptions` -> `운영 가정`
- `Do not claim` -> `단정하면 안 되는 내용`
- `Claim 제한` -> `표현 제한`
- `Coverage note` -> `근거 범위 메모`
- `Visual API` -> `이미지 출처`
- `failed` -> `생성 실패`

### Evidence + QA

Current issues:

- “추천 보강 호출” is ambiguous. It is not a recommendation list; it is an enrichment call history built from `enrichment.latest.tool_calls` or `result.enrichment_plan`.
- Evidence table generally uses good Korean labels, but source labels can still expose source families or raw fallback values if no mapping exists.
- Image candidate badges expose `candidate`, `detail_common`, and source strings if metadata lacks clean labels.
- QA table uses English headers and raw status badge.
- QA messages can still show issue content that comes from internal `needs_review`, e.g. server source-id correction.
- The fallback message “Developer 탭에서 qa_report를 확인하세요” is not appropriate for normal user flow.

Meaning of “추천 보강 호출”:

- It means: “the data enrichment calls that the system planned, executed, skipped, or failed after detecting missing information.”
- It is assembled from `enrichment.latest.tool_calls` when available; otherwise from `result.enrichment_plan.planned_calls` and `skipped_calls`.
- It includes fields such as `source_family`, `tool_name`, `status`, `reason`, and `skip_reason`, then maps some tool/source names to Korean labels.

Recommended replacement:

- Section title: `추가 데이터 확인 내역`
- Description: `부족한 정보를 확인하기 위해 실제로 조회했거나 이번 실행에서 보류한 데이터입니다.`
- Empty state: `이번 실행에서는 추가 데이터 확인이 필요하지 않았습니다.`
- Column names:
  - `처리 상태` -> keep
  - `데이터 종류` -> keep
  - `처리 내용` -> `확인한 정보`
  - `이유와 활용` -> `상품 기획에 쓰이는 방식`

### Product / Marketing / Claims

Current issues:

- Product and marketing content itself is user-facing, but the surrounding labels still use internal schema terms.
- `claim_limits`, `not_to_claim`, and `needs_review` are merged in poster prompt previews and product evidence states. This can surface internal diagnostics as if they were user guidance.
- Search keywords are displayed as badges without explaining whether they are user-facing tags or internal search inputs.

Recommended policy:

- Product/Marketing tab should show only sellable/user-facing copy.
- “표현 제한” should show only normalized claim guidance.
- “운영자 확인” should show only actionable business questions, not server/model repair messages.
- Search keywords should be under `검색/홍보 키워드` and treated as draft metadata, not final copy.

### Evaluation Dashboard

Current issues:

- Evaluation UI uses many English/testing labels: `Evaluation`, `Recent eval runs`, `Dataset`, `Case`, `Status`, `Score`, `Run`, `Cost`, `Reason`, `Metric detail`, `Developer JSON`.
- List badges use `P`, `F`, `S`.
- Case status displays raw `passed`, `failed`, `skipped`.
- `source_family_coverage` displays raw source family and raw `covered` status.
- Metric texts still include `workflow`, `source document`, `metadata`, `enrichment call`, `LLM Judge`, `claim risk`, `metric`.
- Developer JSON is correctly hidden in an accordion, but the label should clarify that it is technical detail.

Recommended user copy:

- `Evaluation` -> `품질 평가`
- `Recent eval runs` -> `최근 평가 실행`
- `Dataset` -> `평가 세트`
- `Case` -> `평가 케이스`
- `Status` -> `상태`
- `Score` -> `점수`
- `Run` -> `연결된 실행`
- `Cost` -> `비용`
- `Reason` -> `이유`
- `P/F/S` -> `통과/실패/제외`
- `passed/failed/skipped` -> `통과/실패/제외`
- `Metric detail` -> `평가 항목 상세`
- `Developer JSON` -> `기술 상세 JSON`

### Poster Studio

Current issues:

- Page title `Poster Studio` remains English. This may be acceptable as product branding, but it is inconsistent with the rest of the Korean operations UI.
- Cards show `Run Detail` and raw `run_id`.
- Failure badge shows raw `failed`.
- Included sections label uses `Claim 제한/주의사항`.
- Poster failure messages may pass provider errors directly to normal UI.
- Poster raw metadata is not shown by default, which is good.

Recommended user copy:

- `Poster Studio` -> `포스터 스튜디오` unless intentionally kept as a product tab name.
- `Run Detail` -> `실행 결과 보기`
- `failed` -> `생성 실패`
- `Claim 제한/주의사항` -> `표현 제한/주의사항`
- `옵션` -> `포함한 내용`
- `run_id` should be secondary; show task/run title first.
- Provider error details should be summarized in normal UI and raw details kept in Developer/error detail.

### Developer/debug

Current issues:

- RunLogs is appropriately a Developer-style view, but labels are still mixed English and raw fields:
  - `Errors`
  - `Agent Execution`
  - `Agent Steps`
  - `Tool Calls`
  - `LLM Calls`
  - `Provider`
  - `Purpose`
  - `View`
- The Developer tab is the right place for raw ids, provider/model/tool names, token/cost detail, raw JSON, and request/response summaries.

Recommended policy:

- Keep raw fields here, but rename tab labels to Korean:
  - `Errors` -> `오류`
  - `Agent Execution` -> `AI 실행 기록`
  - `Agent Steps` -> `단계 로그`
  - `Tool Calls` -> `데이터 호출 로그`
  - `LLM Calls` -> `모델 호출 로그`
  - `View` -> `상세 보기`
- Normal user tabs should link to Developer only when something is truly technical, e.g. “기술 상세는 Developer에서 확인”.

## Action Classification

### Remove from normal user UI

- Raw `source_id` / `doc_id` strings
- JSON field paths such as `sales_copy.sections[0].body`
- Raw issue types such as `general`, `source_missing`, `avoid_rule`
- Source-id correction/fallback diagnostic messages
- Raw `candidate`, `detail_common`, `covered`, `passed`, `failed`, `skipped` enum values
- Provider stack/error response details in normal poster failure UI

### Rename to Korean Product Label

- Agent/workflow labels
- Product table headers
- QA table headers
- Evaluation table headers and statuses
- Poster card action labels
- Claim/assumption/review labels
- Metric labels that still use English test terminology

### Move to Developer/debug

- Internal agent names and step types
- Tool names and raw tool arguments
- Provider/model/purpose
- Raw metadata and JSON
- Source-id correction details
- Raw run/eval/poster ids when not needed for primary navigation
- Full provider error details

### Keep in Normal UI

- Product title, one-liner, itinerary, marketing copy, FAQ, SNS
- Human-readable evidence title, source label, region, snippet, image preview
- Human-readable QA message and suggested fix
- Avoid rules as user-selected constraints
- Poster style label, included content labels, generation status, download/delete actions
- High-level cost/latency summaries when shown in costs/evaluation context

## Recommended Korean Display Labels

| Internal/current label | Recommended label |
| --- | --- |
| Dashboard | 작업 현황 |
| New run | 새 상품 기획 |
| Workflow Preview | 작업 흐름 |
| Workflow run | 실행 |
| Task | 요청 |
| Geo | 지역 |
| Products | 상품 |
| Posters | 포스터 |
| Revisions | 수정본 |
| Created | 생성일 |
| Action | 작업 |
| Agent | AI 단계 |
| Provider | 모델 제공자 |
| Model | 모델 |
| Purpose | 호출 목적 |
| Tool Calls | 데이터 호출 로그 |
| LLM Calls | 모델 호출 로그 |
| source_id / doc_id | 근거 문서 ID |
| source_family | 데이터 출처 |
| gap / gap_type | 확인 필요 정보 |
| missing_pet_policy | 반려동물 동반 조건 확인 |
| missing_detail_info | 상세정보 확인 |
| missing_operating_hours | 운영시간 확인 |
| missing_price_or_fee | 요금 확인 |
| missing_booking_info | 예약/문의 확인 |
| claim_limits | 표현 제한 |
| not_to_claim | 단정하면 안 되는 내용 |
| needs_review | 운영자 확인 |
| assumptions | 운영 가정 |
| sales_copy | 판매 문구 |
| SNS posts | SNS 문구 |
| search_keywords | 검색/홍보 키워드 |
| QA Review | 검수 결과 |
| Severity | 중요도 |
| Type | 분류 |
| Message | 문제 내용 |
| Suggested fix | 수정 제안 |
| pass | 통과 |
| needs_review | 확인 필요 |
| failed | 실패 |
| succeeded | 완료 |
| pending | 대기 |
| running | 진행 중 |
| Poster Studio | 포스터 스튜디오 |
| Run Detail | 실행 결과 보기 |
| Developer JSON | 기술 상세 JSON |

## QA Message Format Criteria

User-facing QA message must:

- Quote the exact problematic customer-facing phrase when possible.
- Say where the phrase appears using human labels, e.g. `상세 설명`, `FAQ 답변`, `판매 문구`.
- Explain the risk in one sentence.
- Avoid raw fields such as `field_path`, `source_id`, `needs_review`, `sales_copy`, or `claim_limits`.
- Avoid raw issue types such as `general` or `source_missing`.
- Distinguish issue lane:
  - `회피 조건 위반`
  - `근거 없는 단정`
  - `운영자 확인 필요`
  - `문구 품질 개선`
  - `내부 진단`
- Keep `suggested_fix` as an executable instruction, not a repeat of the problem.

Recommended format:

- Message: `상세 설명의 "상시 운영"은 운영시간을 단정하고 있습니다.`
- Suggested fix: `운영시간은 공식 확인 후 게시한다고 안내하세요.`

Bad formats:

- `sales_copy.sections[0].body에 문제가 있습니다.`
- `missing_pet_policy 근거가 부족해 운영자 확인이 필요합니다.`
- `상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다.`
- `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.`

## Internal Metadata Exposure Policy

### Show in normal user UI

- Human-readable product and marketing outputs
- Human-readable source title, source type, region, and evidence snippet
- Evidence confidence as a coarse label, e.g. `충분`, `일부 부족`, `부족`
- Actionable operational gaps, e.g. `반려동물 동반 가능 여부는 운영 전 확인하세요.`
- Poster generation status and basic failure summary

### Move to collapsed Developer/debug area

- Agent class names
- Step types
- Tool names
- Provider/model/purpose
- Raw `run_id`, `eval_id`, `poster_id` when not primary navigation
- Raw source ids and content ids
- Raw metadata
- Raw request/response summaries
- Raw provider errors
- Cost token breakdowns unless in a dedicated cost view

### Hide completely from user-facing surfaces

- Server repair notes phrased as model/system internals
- Feature flag explanations
- “future_provider_not_implemented” and equivalent raw skip reasons
- Raw JSON paths
- Duplicate/internal classification if a better Korean label exists

### Show only in error/debug detail

- Provider billing/HTTP errors
- Raw OpenAI/Gemini response details
- Failed tool arguments
- Stack-like diagnostic payloads
- Full case/evaluation JSON

## Phase 16+ UI Cleanup Backlog

### P0: User-facing cleanup that directly affects comprehension

| Target | Change type | Work |
| --- | --- | --- |
| Run Detail QA table | copy-only + formatter | Rename headers to Korean and hide raw status/type/path. |
| Product evidence state | data filtering + copy | Filter source-id correction/model repair messages out of normal `needs_review`. |
| Product Claims tab | copy-only | Rename `Assumptions`, `Do not claim`, `Claims`, `Claim 제한`, `Coverage note`. |
| “추천 보강 호출” section | copy-only | Rename to `추가 데이터 확인 내역` and update description/empty state. |
| Poster cards | copy-only | Rename `failed`, `Run Detail`, `옵션`, `Claim 제한/주의사항`. |

### P1: Evaluation and workflow polish

| Target | Change type | Work |
| --- | --- | --- |
| Dashboard workflow graph | copy-only | Replace agent/provider labels with business step names. |
| Dashboard table | copy-only | Koreanize table headers and summary cards. |
| Evaluation Dashboard | copy-only + formatter | Replace English test labels/statuses and raw source family coverage labels. |
| Run Detail empty/error states | copy-only | Remove “Workflow output” and “Developer 탭” from normal user fallback messages. |

### P2: Metadata exposure boundaries

| Target | Change type | Work |
| --- | --- | --- |
| RunLogs / Developer | copy-only | Keep raw data but Koreanize Developer tab labels. |
| Evidence image badges | formatter | Map `candidate`, `detail_common`, raw source strings to Korean labels. |
| Poster provider errors | data shaping + copy | Return user summary and developer details separately. |
| QA issue lifecycle | data structure | Add issue lane/lifecycle so internal diagnostics do not appear as new user QA failures. |

## Summary

The largest issue is not a single string. The UI currently mixes product-operator language with implementation language. Normal review screens should answer “what should the operator decide next?” Developer/debug screens should answer “what did the system do internally?”

Most serious user-facing terms to fix first:

1. Source-id correction/fallback messages in product/QA surfaces.
2. `needs_review` contents leaking raw operational/system diagnostics.
3. QA table and messages exposing schema concepts such as type/path/message/fix.
4. “추천 보강 호출”, because it hides a data-call history behind ambiguous wording.
5. Evaluation raw test labels/statuses, especially `P/F/S`, raw case status, `source_family`, and `Developer JSON`.

---

Back to index: [27_PHASE_15_QUALITY_AUDIT.md](27_PHASE_15_QUALITY_AUDIT.md)
