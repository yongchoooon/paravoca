# Phase 15.1 AI Revision QA Regression Analysis

Scope: analyze why AI revision can produce more QA issues after selected QA issues were requested for correction. This section does not implement fixes. Poster data is excluded.

Primary comparison:

- Original run: `run_84e06f7609f544f1`
- Revision run: `run_5aaa2ec1f2a641fd`

Data read:

- `backend/data/paravoca.db`
  - `workflow_runs`
  - `agent_steps`
  - `tool_calls`
  - `llm_calls`
- `backend/app/agents/workflow.py`
  - `_run_llm_partial_revision`
  - `_base_revision_state`
  - `revision_patch_agent`
  - `_revision_patch_prompt`
  - `apply_revision_patch`
  - `qa_agent`
  - `_qa_prompt`
  - `validate_qa_report`
  - `_evidence_based_qa_issues`
  - `_qa_settings_from_state`

## Original vs Revision Run Metadata

| Field | Original | Revision |
| --- | --- | --- |
| run_id | `run_84e06f7609f544f1` | `run_5aaa2ec1f2a641fd` |
| status | `awaiting_approval` | `awaiting_approval` |
| parent_run_id | empty | `run_84e06f7609f544f1` |
| revision_number | `0` | `1` |
| revision_mode | empty | `llm_partial_rewrite` |
| created_at | `2026-05-11 21:37:19.791265` | `2026-05-11 22:17:54.480263` |
| latency_ms | `158195` | `13763` |
| user request | `부산에서 반려동물 동반 외국인 대상 관광 상품 3개 기획해줘. 반려동물 동반 조건은 근거가 있는 경우에만 써줘.` | same |
| avoid | `가격 단정 표현` | `가격 단정 표현` |
| qa_settings | derived from normalized input | explicit revision context: period `2026-05`, target `외국인`, preferences `야간 관광`, avoid `가격 단정 표현`, output `ko` |
| final_output availability | yes | yes |
| product count | 3 | 3 |
| marketing asset count | 3 | 3 |
| QA issue count | 3 | 8 |

Original QA summary:

- `상품 정보에 대한 검수 결과, 일부 상품에서 금지된 표현이 사용되었거나 근거가 부족한 주장이 포함되어 있어 수정이 필요합니다. 또한, 반려동물 동반 가능 여부와 같이 확인이 필요한 정보에 대한 근거가 부족하여 운영자 확인이 필요한 상황입니다.`

Revision QA summary:

- `상품 정보에 누락되거나 검토가 필요한 부분이 있습니다. 특히 반려동물 동반 가능 여부에 대한 정보 부족과 상품의 매력을 상세히 설명하는 정보가 부족하여 운영자 확인이 필요합니다.`

Important note: in this representative case, `missing_pet_policy` is not unrelated to the original request. The user explicitly requested pet companion products and said pet conditions should only be used when supported by evidence. The problem is that the pet-policy gap reappears as a new QA issue after revision, even though revision did not change source evidence.

## Revision Pipeline Comparison

| Pipeline element | Original run | Revision run |
| --- | --- | --- |
| agent steps | `workflow_created`, `planner`, `geo_resolution`, `baseline_data_collection`, `data_gap_profile`, `api_capability_routing`, `tourapi_detail_planning`, `theme_data_planning`, `data_enrichment`, `evidence_fusion`, `research`, `product_generation`, `marketing_generation`, `qa_review`, `human_approval` | `revision_created`, `revision_context`, `revision_patch`, `qa_review`, `human_approval` |
| LLM purposes | `planner`, `geo_resolution`, `data_gap_profile`, `api_capability_routing`, `tourapi_detail_planning`, `theme_data_planning`, `evidence_fusion`, `research_synthesis`, `product_generation`, `marketing_generation`, `marketing_generation_repair`, `qa_review` | `revision_patch`, `qa_review` |
| tool calls | TourAPI keyword/area/festival/stay, detailCommon, detailIntro, detailInfo, detailImage, pet keyword search, vector search | none |
| RAG / TourAPI rerun | yes | no |
| source document refresh | yes through original pipeline | no |
| evidence fusion rerun | yes | no |
| QA rerun | yes | yes |

Tool call difference:

- Original run used 88 tool calls:
  - `kto_pet_keyword_search`: 1
  - `kto_tour_detail_common`: 20
  - `kto_tour_detail_image`: 20
  - `kto_tour_detail_info`: 20
  - `kto_tour_detail_intro`: 20
  - `tourapi_area_based_list`: 2
  - `tourapi_search_festival`: 1
  - `tourapi_search_keyword`: 1
  - `tourapi_search_stay`: 1
  - `vector_search`: 1
  - `vector_search_post_enrichment`: 1
- Revision run used 0 tool calls.

LLM call difference:

- Original run had 12 LLM calls.
- Revision run had 2 LLM calls:
  - `revision_patch`
  - `qa_review`

The revision path is therefore a patch-and-recheck workflow, not a full regeneration workflow.

## Revision Input Difference Analysis

The revision input is not the same shape as the original generation input. It contains the original user request plus a `revision_context` object.

Revision context contains:

- `source_run_id`: `run_84e06f7609f544f1`
- `root_run_id`: `run_84e06f7609f544f1`
- `revision_mode`: `llm_partial_rewrite`
- `revision_number`: `1`
- `source_final_output`: full original final output
- `qa_issues`: 3 selected original QA issues
- `requested_changes`: 9 text lines derived from the 3 selected QA issues
- `qa_settings`: period, target customer, preferences, avoid, output language
- `approval_history`, `manual_products`, `manual_marketing_assets`

Selected QA issues in revision input:

| product_id | severity | type | field_path | message |
| --- | --- | --- | --- | --- |
| `prod_001` | medium | general | `sales_copy.sections[0].body` | `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.` |
| `prod_002` | medium | general | `sales_copy.sections[0].body` | `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.` |
| `prod_003` | medium | general | `sales_copy.sections[0].body` | `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.` |

Revision prompt/context coverage:

- `_revision_patch_prompt` passes full `현재_상품`, full `현재_마케팅_자산`, selected QA issues, requested changes, review comment, and QA settings.
- It explicitly says not to regenerate the whole product or whole marketing asset.
- It explicitly says to include only minimum patches needed to solve selected QA issues.
- It says unchanged values are kept by the server.
- It does not pass retrieved documents or evidence context directly to the revision patch prompt, but `_base_revision_state` copies those branches from the original final output into revision state for QA.

Patch field scope:

- `apply_revision_patch` can patch product fields:
  - `title`
  - `one_liner`
  - `estimated_duration`
  - `operation_difficulty`
  - `core_value`
  - `assumptions`
  - `not_to_claim`
- It cannot patch product fields:
  - `source_ids`
  - `claim_limits`
  - `needs_review`
- It can patch marketing fields:
  - sales copy headline/subheadline/disclaimer/sections
  - FAQ
  - SNS posts
  - search keywords

Evidence/context stability:

| Branch | Same after revision? | Notes |
| --- | --- | --- |
| `source_items` | yes | copied from original |
| `retrieved_documents` | yes | copied from original |
| `evidence_profile` | yes | copied from original |
| `productization_advice` | yes | copied from original |
| `data_coverage` | yes | copied from original |
| `unresolved_gaps` | yes | copied from original |
| `source_confidence` | yes | copied from original |
| `ui_highlights` | yes | copied from original |
| `research_summary` | yes | copied from original |
| `products` | yes | no effective product field changed |
| `marketing_assets` | no | first sales copy section body changed for each product |
| `qa_report` | no | QA rerun produced 8 issues |
| `normalized_request` | no | revision context added |

Conclusion: the new QA issues were not caused by changed source evidence, changed RAG output, changed source_ids, or changed avoid settings. They were exposed during the revision QA rerun.

## Product / Marketing Diff Table

| product_id | product title | changed product fields | changed marketing fields | source_ids changed | claim_limits changed | not_to_claim changed | needs_review changed | outside selected scope changed | risk assessment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `prod_001` | 부산 야경 요트 투어 | none | `sales_copy.sections[0].body` | no | no | no | no | no | Stale `needs_review` still contains the selected copy-quality issue and pet-policy gap. |
| `prod_002` | 영도 커피 & 문화 페스티벌 | none | `sales_copy.sections[0].body` | no | no | no | no | no | Stale `needs_review` still contains source-id fallback, selected copy-quality issue, and pet-policy gap. |
| `prod_003` | 부산 시민 축제 & 로컬 미식 탐방 | none | `sales_copy.sections[0].body` | no | no | no | no | no | Stale `needs_review` still contains source-id fallback, selected copy-quality issue, and pet-policy gap. |

Marketing body changes:

| product_id | Original body | Revision body |
| --- | --- | --- |
| `prod_001` | `해운대의 눈부신 야경을 배경으로 펼쳐지는 럭셔리 요트 체험. 잊지 못할 특별한 순간을 선사합니다.` | `해운대의 눈부신 야경을 배경으로 펼쳐지는 럭셔리 요트 체험. 부산의 아름다운 스카이라인을 감상하며 잊지 못할 특별한 순간을 선사합니다.` |
| `prod_002` | `커피와 함께 영도의 다채로운 문화와 예술을 만끽하는 특별한 경험을 선사합니다.` | `커피와 함께 영도의 다채로운 문화와 예술을 만끽하는 특별한 경험을 선사합니다. 영도의 매력을 깊이 있게 탐방하세요.` |
| `prod_003` | `택시기사 추천 로컬 맛집과 다채로운 축제를 경험하며 부산의 진정한 매력을 발견하세요.` | `택시기사 추천 로컬 맛집과 다채로운 축제를 경험하며 부산의 진정한 매력을 발견하세요. 부산의 숨겨진 맛집과 함께 특별한 미식 여행을 떠나보세요.` |

The patch improved text length only slightly. It did not remove or resolve the stale `needs_review` items that contain the same selected issue text.

## QA Issue Diff Table

| product_id | Original issue | Revision issue | Diff status | Likely cause |
| --- | --- | --- | --- | --- |
| `prod_001` | `sales_copy.sections[0].body`: `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.` | `needs_review[1]`: same message | still_open / changed_field_path | Revision changed sales copy but did not clear the same message from `products[].needs_review`. |
| `prod_002` | `sales_copy.sections[0].body`: `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.` | `needs_review[2]`: same message | still_open / changed_field_path | Revision changed sales copy but stale `needs_review` still carries the issue text. |
| `prod_003` | `sales_copy.sections[0].body`: `상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.` | `needs_review[2]`: same message | still_open / changed_field_path | Revision changed sales copy but stale `needs_review` still carries the issue text. |
| `prod_001` | none | `needs_review[2]`: `missing_pet_policy 근거가 부족해 운영자 확인이 필요합니다.` | new_issue | Existing product `needs_review` was surfaced by revision QA. Evidence did not change. |
| `prod_002` | none | `needs_review[1]`: `상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다.` | new_issue | Existing product `needs_review` was surfaced by revision QA. This is a source-id fallback diagnostic, not caused by revision. |
| `prod_002` | none | `needs_review[3]`: `missing_pet_policy 근거가 부족해 운영자 확인이 필요합니다.` | new_issue | Existing product `needs_review` was surfaced by revision QA. |
| `prod_003` | none | `needs_review[1]`: `상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다.` | new_issue | Existing product `needs_review` was surfaced by revision QA. |
| `prod_003` | none | `needs_review[3]`: `missing_pet_policy 근거가 부족해 운영자 확인이 필요합니다.` | new_issue | Existing product `needs_review` was surfaced by revision QA. |

Resolved issues:

- None.

Still open:

- The original copy-quality issue remains for all 3 products, but the field path moved from `sales_copy.sections[0].body` to `needs_review[...]`.

New issues:

- 5 issues appear only in revision QA.
- They correspond to pre-existing `products[].needs_review` entries, not newly changed product or evidence data.

Message quality problem:

- `_qa_prompt` says issue messages must quote the exact problematic customer-facing phrase and must not create an issue if it cannot quote one.
- The revision QA messages do not quote a customer-facing phrase. They repeat internal `needs_review` notes.
- `validate_qa_report` normalizes messages and merges deterministic evidence checks, but it does not enforce the quote requirement.

## New QA Issue Root Cause Analysis

Most likely root causes:

1. Stale `needs_review` survives revision unchanged.
   - `apply_revision_patch` cannot patch `needs_review`.
   - The selected issue text already exists inside `products[].needs_review`.
   - After revision, QA sees the same note and reports it again.

2. Revision QA treats internal review notes as issue material.
   - `_qa_prompt` passes full `상품_목록`, including `needs_review`.
   - The prompt explicitly exempts `not_to_claim` and `assumptions` as internal references, but it does not explicitly exempt `needs_review`.
   - That allows LLM QA to convert `needs_review` notes into user-facing QA issues.

3. QA issue lifecycle is not modeled.
   - Revision QA is a fresh QA run, not a diff against original QA.
   - There is no lifecycle state such as `resolved`, `still_open`, `new_issue`, or `pre_existing_unselected_gap`.
   - Pre-existing gaps that were not selected for revision can appear as new issues.

4. The selected issue is copy quality, not a pure evidence-risk issue.
   - The original selected issue says the product lacks enough attractive explanation.
   - The patch only appends one short sentence per product.
   - Even if this is an improvement, there is no explicit acceptance threshold that tells QA the selected issue is resolved.

5. Source-id fallback diagnostics are mixed into customer QA.
   - `prod_002` and `prod_003` already had `needs_review` notes about server source-id correction.
   - Revision did not cause those notes.
   - QA later reports them as product issues, making the revision look worse.

`missing_pet_policy` conclusion:

- In this comparison pair, pet policy is in scope because the original request explicitly requested pet companion products.
- The regression problem is not that pet policy appeared from nowhere.
- The problem is that a pre-existing pet-policy evidence gap was not selected for revision, did not change, and still appeared as a new revision QA issue.

`상품 매력 부족` conclusion:

- The issue was selected for revision and the marketing body changed.
- The same issue text remains in `products[].needs_review`.
- Because `needs_review` was not cleared or updated, QA can continue to report the issue even after the targeted field was patched.

## Revision Scope Control Criteria

Revision should preserve by default:

- `source_ids`
- `retrieved_documents`
- `source_items`
- `evidence_profile`
- `productization_advice`
- `data_coverage`
- `unresolved_gaps`
- `source_confidence`
- `ui_highlights`
- `claim_limits`
- `not_to_claim`, unless selected issue explicitly targets it

Revision may patch only when selected:

- Product title
- One-liner
- Core value
- Assumptions
- Sales copy headline/subheadline/sections/disclaimer
- FAQ
- SNS posts
- Search keywords

Revision needs explicit lifecycle handling for:

- `needs_review`
- QA issue status
- Source-id fallback diagnostics
- Evidence gaps that were not selected for revision

Recommended scope rules for Phase 16+:

- Keep `needs_review` structured, with fields such as `id`, `origin`, `linked_qa_issue_id`, `status`, and `visible_to_user`.
- When a selected QA issue is patched, allow the revision pipeline to mark the matching `needs_review` item as `resolved` or `stale`, instead of leaving the same text active.
- Do not allow revision to silently change source evidence unless the revision mode explicitly requests evidence refresh.
- Separate internal diagnostics from user-facing QA. Source-id correction messages should not be reported as marketing/product QA issues.
- Keep unselected existing evidence gaps as `known_gap`, not `new_issue`, unless the changed text makes a stronger unsupported claim.

## QA Regression Prevention Criteria

QA recheck should produce a diff, not only a fresh QA report:

- `resolved`: original selected issue is gone or marked resolved.
- `still_open`: selected issue remains on the same product and same field.
- `changed_wording`: same underlying issue appears with different wording or field path.
- `new_issue`: issue appears only after revision and is linked to changed text.
- `pre_existing_unselected_gap`: issue existed in product/evidence state before revision but was not in original QA report.
- `needs_followup`: matching is uncertain.

Revision QA input should include:

- Original QA report
- Selected QA issues
- Revision patch summary
- Changed field list
- Unchanged field list
- Previous `needs_review`
- Current `needs_review`

QA recheck should be constrained as follows:

- Do not report unselected pre-existing `needs_review` notes as new revision issues unless the revised text made them newly risky.
- Do not judge copy attractiveness in the same QA lane as evidence risk unless the user explicitly requested copy quality review.
- If a message cannot quote an actual changed customer-facing phrase, do not classify it as a new regression.
- If QA reports an issue from `needs_review`, label it as an existing operational gap, not as a new content failure.
- If source evidence did not change, source-id fallback diagnostics should keep their previous status.

Prompt/schema/validator implications:

- `_qa_prompt` should explicitly state whether `needs_review` is internal or customer-facing.
- `validate_qa_report` should enforce the exact-phrase requirement instead of relying only on prompt instructions.
- Revision QA should accept and return issue lifecycle categories.
- QA schema should distinguish evidence risk, avoid violation, copy quality, internal diagnostic, and known operational gap.

## Final Conclusions

Top input/context differences:

1. Revision input includes `revision_context`, selected QA issues, requested changes, QA settings, and full source final output. Original input does not.
2. Revision pipeline skips Planner, GeoResolver, TourAPI, RAG search, EvidenceFusion, Research, Product, and Marketing generation. It runs only revision patch and QA.
3. Revision QA runs over patched marketing plus unchanged product/evidence state. The unchanged product state still contains old `needs_review` notes.

Top likely causes of new QA issues:

1. `needs_review` entries persisted unchanged and were surfaced by revision QA.
2. QA recheck is a fresh report, not a diff-aware recheck against original QA and selected issues.
3. Internal diagnostics and known evidence gaps are mixed into user-facing QA output.

Source/context change conclusion:

- `source_ids`: unchanged.
- `evidence_context`: unchanged.
- `retrieved_documents`: unchanged.
- `avoid`: unchanged.
- `qa_settings`: semantically unchanged for avoid/period/target/preferences/output; revision context stores an explicit object, but it resolves to the same QA scope.
- `claim_limits`: unchanged.
- `not_to_claim`: unchanged.
- `needs_review`: unchanged.

Therefore, this regression is primarily QA lifecycle and internal-state exposure, not evidence drift or source-id drift caused by the revision.

---

Back to index: [27_PHASE_15_QUALITY_AUDIT.md](27_PHASE_15_QUALITY_AUDIT.md)
