# Phase 17 RAG and Evidence Pipeline Hardening

## 17.1 Source/RAG Structure Cleanup

Phase 17.1은 source document가 어디서 생겼고, 어떤 조건으로 검색됐고, 왜 검색 결과에 포함됐는지 추적 가능하게 만드는 단계다. 이번 범위에서는 product-level evidence bundle 재설계, image evidence UX 재설계, marketing prompt 고도화는 구현하지 않았다.

## 구현 기준

- Source document는 역할과 유입 경로를 metadata에 기록한다.
- RAG 검색은 지역뿐 아니라 theme, content type, target customer, narrow keyword를 query/context/filter에 반영한다.
- 검색 결과가 부족해도 상위 지역, 전국, generic evidence로 자동 확장하지 않는다.
- 조건을 만족하지 않는 문서를 성공처럼 섞지 않는다.
- 검색 부족, filter mismatch, collection empty 상태는 retrieval diagnostics에 남긴다.
- 사용자-facing Evidence UI는 크게 바꾸지 않고, Developer/debug에서 query, filters, result count, matching signals를 확인할 수 있게 했다.

## Source Document Role

Source document metadata의 `source_role`은 다음 값을 사용한다.

| role | 의미 |
|---|---|
| `runtime_run_evidence` | workflow run 중 TourAPI 검색/상세 보강으로 수집된 근거 |
| `existing_catalog` | 기존 DB나 catalog ingestion에서 들어온 근거 |
| `seed_catalog` | 사전 ingestion으로 쌓을 catalog 근거 |
| `manual_ingestion` | 사람이 Data Source API에서 직접 수집/보강한 근거 |
| `enrichment_result` | detail, visual, route/signal, theme 보강 결과 |
| `unknown` / `unclassified` | 기존 row처럼 역할 metadata가 없는 근거 |

역할이 없는 기존 문서는 `unknown`으로 취급한다. `unknown` 문서를 삭제하거나 임의로 runtime evidence로 승격하지 않는다. 검색 결과에는 포함될 수 있지만 relevance score에서 불리하게 처리하고, Developer/debug에서 역할을 확인할 수 있게 했다.

## Lifecycle Metadata

Source document metadata에는 다음 lifecycle 정보를 기록한다.

- `source_role`
- `source_family`
- `content_id`
- `source_item_id`
- `first_seen_run_id`
- `last_seen_run_id`
- `ingestion_method`
- `detail_enriched`
- `observed_at`
- `last_observed_at`
- `dedupe_key`
- `stale_status`
- `stale_reasons`

중복 기준은 `source_family + content_id/source_item_id`를 우선한다. 동일 TourAPI content는 같은 `doc:tourapi:content:{content_id}` id로 upsert되어 `first_seen_run_id`는 유지하고 `last_seen_run_id`만 갱신한다.

## RAG Query and Filter

Workflow의 RAG query는 다음 요소를 합쳐 만든다.

- resolved location
- target customer
- preferred themes
- retained narrow keywords
- original user request
- content type terms

Metadata filter는 값이 확인된 경우에만 명시적으로 넣는다.

- `source`
- `source_family`
- `ldong_regn_cd`
- `ldong_signgu_cd`
- `lcls_systm_1`
- `lcls_systm_2`
- `lcls_systm_3`
- `content_type`

조건이 없으면 추측하지 않는다. 결과가 0개여도 자동으로 지역 범위를 넓히지 않는다.

## Retrieval Diagnostics

`search_source_documents_with_diagnostics`는 검색 결과와 함께 다음 진단 정보를 반환한다.

- `query`
- `filters`
- `top_k`
- `candidate_count_before_filter`
- `requested_chroma_results`
- `result_count`
- `unknown_role_result_count`
- `matching_signal_summary`
- `fallback_applied`
- `scope_expansion_applied`
- `reason`

각 검색 결과에는 다음 정보가 포함된다.

- `score`
- `relevance_score`
- `source_role`
- `matching_signals`
- `metadata`

`matching_signals`는 “같은 시군구 코드와 일치”, “요청 theme와 문서 내용이 일치”, “narrow keyword가 문서에 포함” 같은 신호 목록이다. 이는 확정 설명이 아니라 검색 결과를 이해하기 위한 matching signal이다.

## No Fallback Policy

이번 구현에서 명시적으로 유지한 정책은 다음과 같다.

- 검색 결과가 0개여도 상위 지역/전국 검색을 자동 실행하지 않는다.
- filter를 만족하지 않는 문서를 섞지 않는다.
- fake source document나 dummy evidence를 만들지 않는다.
- source role이 없는 문서를 runtime evidence처럼 우선하지 않는다.
- ProductAgent가 실제 근거 목록에 없는 `source_id`만 반환하거나 근거를 비워 반환해도, 서버가 다른 source document를 대신 붙이지 않는다.
- product에 연결된 근거가 없으면 `source_ids`를 빈 상태로 유지하고, QA/diagnostics에서 근거 연결 부족으로 드러낸다.
- 부족하면 `retrieval_diagnostics.reason`에 부족 상태를 남긴다.

이 정책은 특정 API에 한정하지 않는다. TourAPI 기본 관광지, 오디오/스토리/웰니스/반려동물/의료/코스/이미지 보강 등 어떤 source family에서 오더라도 product와 직접 연결되지 않은 근거를 product 대표 근거처럼 붙이지 않는다.

단, source id 정규화는 fallback으로 보지 않는다. 모델이 `doc:tourapi:content:2551424` 대신 `tourapi:content:2551424` 또는 `2551424`처럼 같은 원본 관광지를 가리키는 값을 반환하면, 서버는 해당 값이 하나의 primary TourAPI source document로 명확히 해석될 때만 실제 `doc_id`로 바꾼다. 또한 source id가 비어 있어도 상품 제목/일정에 근거 제목이 명확히 포함된 경우에만 같은 근거로 연결한다. 지역명만 같거나 애매한 문서는 연결하지 않는다.

상품이 primary TourAPI 근거와 연결되면, 같은 `source_item_id` 또는 `content_id`에 직접 연결된 보강 문서도 product evidence로 함께 묶는다. 예를 들어 `국립일제강제동원역사관` 상품이 primary TourAPI 문서를 사용하고, 같은 관광지에 대한 Odii 오디오 스토리 문서가 이번 run에서 수집되었다면, 오디오 문서도 상품의 근거 목록과 evidence summary에 포함된다. 이 동작은 오디오에 한정하지 않고, 같은 원본 관광지에 직접 연결된 theme/visual/route/enrichment 계열 근거에 동일하게 적용한다. 단, 다른 장소나 지역-only 문서는 붙이지 않는다.

Theme/enrichment API 결과도 같은 기준을 따른다. API가 특정 관광지에 연결된 후보처럼 반환하더라도, 후보의 title/script/overview/raw payload가 대상 관광지를 강하게 참조하지 않으면 source document와 image candidate로 저장하지 않는다. 주소나 같은 시군구처럼 약한 신호는 diagnostics에는 남길 수 있지만, 특히 오디오/스토리 소재에서는 accept 조건으로 쓰지 않는다. 예를 들어 대상이 `국립일제강제동원역사관`인데 오디오 script가 철원/종로 코스 설명이면, 주소가 부산 남구로 묶여 있어도 reject한다.

이미 DB/Chroma에 남아 있는 오래된 theme/enrichment 문서도 `theme_match_signals`가 없으면 ProductAgent 입력으로 넘기지 않는다. 즉 과거에 잘못 저장된 오디오/테마 후보가 새 run에서 다시 검색되더라도, 강한 연결 신호가 없는 문서는 product evidence로 재사용하지 않는다.

또한 visual, route/signal, theme 같은 non-core enrichment source family는 이번 run에서 직접 수집/보강된 문서만 post-enrichment evidence로 사용한다. 추가 API가 현재 run에서 관련 데이터를 찾지 못했다면, 예전에 DB/Chroma에 쌓인 같은 지역의 보강 문서를 RAG로 끌어와 빈자리를 채우지 않는다. 예를 들어 `영도 커피 페스티벌`에 대한 Odii 결과가 없으면 `영도다리`, `영도교` 같은 기존 오디오 문서를 대신 붙이지 않고, 오디오 근거가 없는 상태로 둔다.

Target item이 있는 theme/enrichment API 호출은 보강 종류만 담긴 넓은 검색어를 그대로 쓰지 않는다. 예를 들어 planner가 `kto_audio` 호출을 `오디오`로 계획했더라도 대상 관광지가 `국립일제강제동원역사관`이면 실제 Odii 검색어는 대상 관광지명으로 좁힌다. 이 규칙은 특정 장소명 하드코딩이 아니라, 오디오/스토리/웰니스/반려동물/의료 같은 보강 API에서 source family만 가리키는 generic query가 들어왔을 때 target item title을 우선하는 정책이다. 관련 데이터가 API에 있으면 이번 run의 보강 근거로 저장하고, 없으면 없는 상태로 남긴다.

EvidenceFusion 입력은 post-enrichment RAG 결과만으로 교체하지 않는다. Baseline TourAPI 수집 후 선택된 `source_items`의 source documents, baseline RAG 결과, 이번 run에서 직접 수집된 enrichment documents를 병합한다. 따라서 RAG top-k가 2개만 반환되어도 TourAPI shortlist 근거가 Evidence 화면과 ProductAgent 입력에서 사라지지 않는다.

## Seed / Pre-index Strategy

대량 seed ingestion은 이번 범위에 포함하지 않았다. 단, 향후 seed ingestion은 `seed_catalog` role을 사용하고 다음 metadata를 반드시 채워야 한다.

- source family
- content id 또는 stable source item id
- 지역 code
- content type
- title/address/summary
- observed_at 또는 data_updated_at
- license/trust note

Seed가 없는 지역에서는 runtime 검색 결과가 부족할 수 있다. 이 경우 workflow는 generic fallback을 붙이지 않고 근거 부족 상태와 사용한 query/filter를 보여준다.

## API / UI 영향

- `POST /api/rag/search` 응답에 `retrieval_diagnostics`가 포함된다.
- Run Detail Developer debug에서 RAG query/filter details와 returned document matching signals를 확인할 수 있다.
- Data Sources 문서 상세에는 source role과 lifecycle summary가 표시된다.
- Result Review의 product image candidates는 product에 연결된 source document 기준으로 표시한다. product source가 비어 있으면 run-level generic image를 대신 보여주지 않는다.
- 사용자-facing Evidence UX 재설계는 Phase 18에서 진행한다.

## Tests

추가/수정한 테스트 기준:

- source document lifecycle metadata가 유지되는지
- 기존 role 없는 문서가 `unknown`으로 처리되는지
- 같은 TourAPI content가 upsert될 때 first/last seen이 유지되는지
- RAG query/filter가 지역/theme/content type/narrow keyword를 반영하는지
- 검색 결과 부족 시 fallback/scope expansion이 발생하지 않는지
- retrieval diagnostics와 matching signals가 남는지
- `unknown` role 문서가 분류된 문서보다 우선되지 않는지

실행한 검증:

- `conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests`
- `PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build`

## 완료된 사용자 확인 케이스

이번 17.1에서는 아래 실제 문제 케이스를 기준으로 동작을 확인했다.

| case | 기존 문제 | 현재 동작 |
|---|---|---|
| 부산 역사/문화 상품에서 Odii 오디오 보강 | `국립일제강제동원역사관` 상품에 철원/종로 오디오 스크립트가 근거처럼 붙음 | target 관광지명으로 보강 API query를 좁히고, 후보 내용이 target을 강하게 참조하지 않으면 저장/노출하지 않음 |
| 영도 커피 페스티벌과 오디오 자료 | `영도` 지역 오디오가 있다는 이유로 영도교/영도다리 같은 무관 오디오가 후보로 붙음 | 관련 Odii 결과가 없으면 오디오 근거 없이 진행함. 같은 지역만으로 보강 근거를 붙이지 않음 |
| RAG top-k 결과가 적은 run | post-enrichment RAG 결과 2개만 남아 TourAPI shortlist 근거가 ProductAgent/Evidence 화면에서 사라짐 | baseline source item documents, baseline RAG, current-run enrichment docs를 병합해 shortlist 근거가 유지됨 |
| 요청 상품 개수 | 연결 근거가 부족하면 3개 요청에도 상품이 2개만 생성됨 | 직접 연결 근거가 부족해도 요청한 상품 수를 임의로 줄이지 않고, 부족한 근거는 빈 source_ids와 review note로 드러냄 |
| ProductAgent source_id 오류 | 모델이 `2551424` 같은 축약 id를 반환하면 서버가 generic evidence를 붙이거나 source가 사라짐 | 하나의 primary source로 명확히 해석될 때만 실제 source document id로 정규화함. 애매하면 붙이지 않음 |
| 상품별 보강 근거 | primary TourAPI 근거와 같은 관광지의 오디오/테마/이미지 보강 근거가 ProductAgent 입력에서 누락됨 | 같은 source item 또는 content id에 직접 연결된 보강 문서를 product evidence와 summary에 함께 포함함 |
| Result Review 근거 이미지 | product와 직접 연결되지 않은 run-level 이미지를 대표 이미지처럼 보여줌 | product source_ids와 연결된 image candidates만 보여줌. 없으면 generic image로 채우지 않음 |
| Evidence selected filter | selected product 하나의 근거만 보여서 전체 run에서 선택된 근거 흐름을 보기 어려움 | 선택된 상품들의 source_ids 합집합 기준으로 selected evidence를 보여줌 |

## 현재 동작 요약

1. Workflow가 TourAPI/KTO에서 후보를 수집하면 source document가 생성되고, 각 문서는 role/origin/lifecycle metadata를 가진다.
2. RAG 검색은 지역, content type, theme, target customer, narrow keyword를 함께 사용한다.
3. RAG 검색이 부족해도 검색 범위를 몰래 넓히지 않는다.
4. 보강 API는 target item이 있으면 target item 이름으로 query를 좁힌다.
5. 보강 API 결과는 같은 지역이라는 이유만으로 accept하지 않는다.
6. ProductAgent가 근거 id를 잘못 쓰면 서버는 확실한 alias만 정규화하고, 애매한 경우에는 근거 부족으로 남긴다.
7. EvidenceFusion은 source item 근거, RAG 근거, 이번 run에서 수집된 보강 근거를 병합한다.
8. 상품에 직접 연결된 근거와 그 근거의 보강 문서만 상품 근거/이미지 후보로 보여준다.

## 17.2 Product-level Evidence Bundle

17.2는 취소한다.

취소 이유:

- 17.1에서 run-level shared evidence pool contamination, generic fallback, 무관 enrichment 재사용 문제가 이미 크게 줄었다.
- Product-level bundle을 지금 추가하면 구조 복잡도만 늘고, 17.1에서 안정화한 source linking 흐름을 다시 흔들 가능성이 있다.
- 상품별 근거 설명/시각화가 부족해지는 문제는 Phase 18 Evidence UX에서 UI 관점으로 다시 다룬다.

## 17.3 Revision Source Stability and Source ID Guardrails

17.3은 source_id 문제를 새로 크게 고치는 단계가 아니라, revision 과정에서 17.1의 no-fallback/source_id 안정성을 깨지 않게 잠그는 단계다.

### ProductAgent Source ID Guardrail

ProductAgent prompt에는 다음 제약을 명확히 둔다.

- `source_ids`는 `retrieved_documents` 안에 있는 `doc_id`만 사용한다.
- `content_id`, 관광지 id, API item id, 추측한 id를 쓰지 않는다.
- 확실한 근거가 없으면 `source_ids`는 빈 배열로 두고, 근거 부족을 `needs_review`/`coverage_notes`에 남긴다.
- 근거 문서 수가 요청 상품 수보다 적어도 상품 수를 줄이지 않는다.

서버 validator는 다음 기준으로 source id를 처리한다.

| case | action |
|---|---|
| 제공된 `doc_id`가 실제 retrieved document에 있음 | accepted |
| `content_id`/`source_item_id` alias가 하나의 primary source document로 명확히 해석됨 | normalized |
| alias가 애매하거나 실제 document에 없음 | excluded |
| source id가 비어 있지만 상품 title/itinerary가 근거 title과 명확히 일치함 | normalized |
| 어떤 근거도 직접 연결할 수 없음 | empty source_ids 유지, 근거 부족 note 추가 |

invalid source id가 있어도 서버는 다른 generic evidence를 대신 붙이지 않는다.

### Invalid Source ID Diagnostics

invalid source id 처리 결과는 product의 `internal_diagnostics`와 revision metadata의 `source_stability.invalid_source_id_diagnostics`에 구조화해 남긴다.

필드:

- `category`: `source_id_guardrail`
- `product_id`
- `invalid_source_id`
- `reason`
- `action`: `excluded` / `normalized`
- `normalized_to`

이 정보는 사용자-facing QA issue로 만들지 않는다. Developer/debug에서 원인 추적용으로만 확인한다.

### Revision Source Stability

AI 수정, 직접 수정, QA-only revision은 source/evidence 수정 기능이 아니다. 따라서 revision 최종 merge 단계에서 부모 run의 source/evidence 관련 값을 보존한다.

보존하는 항목:

- `products[].source_ids`
- `products[].evidence_summary`
- `products[].itinerary[].source_id`
- `retrieved_documents`
- `evidence_profile`
- `productization_advice`
- `data_coverage`
- `unresolved_gaps`
- `source_confidence`
- `ui_highlights`

모드별 동작:

| revision mode | source stability mode | 동작 |
|---|---|---|
| `llm_partial_rewrite` | `preserve_parent_sources_after_ai_patch` | LLM patch 후 source/evidence 필드는 부모 run 기준으로 되돌림 |
| `manual_edit` | `preserve_parent_sources_after_manual_edit` | 사용자가 텍스트를 직접 수정해도 source/evidence 필드는 부모 run 기준 유지 |
| `manual_save` | `preserve_parent_sources_after_manual_save` | QA 없이 저장하더라도 source/evidence 필드는 부모 run 기준 유지 |
| `qa_only` | `preserve_parent_sources_for_qa_only` | content/source 변경 없이 QA만 다시 실행 |

revision metadata에는 다음을 남긴다.

- `source_stability_mode`
- `source_fields_preserved`
- `source_fields_changed`
- `evidence_recomputed`
- `reason`
- `product_source_preservation`
- `invalid_source_id_diagnostics`

### 17.3 Tests

추가/수정한 테스트 기준:

- invalid source id가 final product `source_ids`에 섞이지 않는다.
- invalid source id가 generic fallback evidence로 대체되지 않는다.
- invalid source id diagnostic이 internal metadata에 남는다.
- invalid source id diagnostic이 사용자-facing QA issue로 노출되지 않는다.
- primary source 없는 product도 상품 수가 줄지 않는다.
- AI partial rewrite revision 후 source fields가 유지된다.
- 직접 수정 revision 후 source fields가 유지된다.
- QA-only revision에서 products/source/evidence가 재생성되지 않는다.
- revision metadata에 `source_stability` 정보가 남는다.

## 남은 범위

17.1과 17.3은 RAG/source 구조와 revision source stability를 안정화하는 단계다. 다음 작업은 별도로 진행한다.

- Phase 18: Evidence/Visual Evidence UI 재설계
- Phase 19: Marketing Output Hardening

## 구현 파일

주요 변경 파일:

- `backend/app/rag/source_documents.py`
- `backend/app/rag/chroma_store.py`
- `backend/app/agents/workflow.py`
- `backend/app/agents/data_enrichment.py`
- `backend/app/tools/themes.py`
- `backend/app/tools/visuals.py`
- `backend/app/tools/route_signals.py`
- `backend/app/api/routes_rag.py`
- `backend/app/api/routes_data_sources.py`
- `frontend/src/pages/DataSourcesPanel.tsx`
- `frontend/src/pages/RunDetail.tsx`

관련 문서:

- `README.md`
- `paravoca-ax-agent-studio-docs/03_SYSTEM_ARCHITECTURE.md`
- `paravoca-ax-agent-studio-docs/05_DATA_SOURCES_AND_INGESTION.md`
- `paravoca-ax-agent-studio-docs/09_RAG_GUARDRAILS_EVALUATION.md`
