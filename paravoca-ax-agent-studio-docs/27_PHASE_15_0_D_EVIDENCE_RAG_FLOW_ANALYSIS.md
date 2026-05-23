# Phase 15.0-D Evidence / RAG Flow Analysis

### Scope and Data Sources

- Target runs are fixed to the same 9 runs used in `15.0-A/B/C`.
- Revision runs and poster-related data were excluded.
- This analysis reads existing DB rows, Chroma metadata/files, source document rows, tool calls, agent steps, LLM calls, and code paths only. No product code was changed.
- Primary files inspected:
  - `backend/data/paravoca.db`
  - `backend/data/chroma/chroma.sqlite3`
  - `backend/data/chroma/*/`
  - `backend/app/agents/workflow.py`
  - `backend/app/rag/source_documents.py`
  - `backend/app/rag/chroma_store.py`
  - `backend/app/rag/embeddings.py`
  - `backend/app/core/config.py`

### Current Evidence / RAG Data Flow

```text
User request
  -> BaselineDataAgent
     -> TourAPI keyword query generation
     -> TourAPI area/festival/stay list collection
     -> TourAPI detail_common/detail_intro/detail_info/detail_image enrichment
     -> source_documents upsert
     -> Chroma source_documents index upsert
     -> initial vector search
     -> post-enrichment vector search
  -> EvidenceFusion
     -> source_items + source_documents + retrieved_documents fusion
     -> evidence_profile / productization_advice / unresolved_gaps
  -> ProductAgent
     -> products generated from retrieved_documents + evidence_context
     -> server validates source_ids against retrieved_documents
  -> QAAgent
     -> QA prompt receives products + retrieved_documents + evidence_context + claim limits
     -> deterministic evidence checks append source/claim issues
```

1. **TourAPI 검색 query 생성**
   - `BaselineDataAgent` builds a Korean keyword query from normalized region, audience, themes, and constraints.
   - In all 9 target runs, `tourapi_search_keyword` returned `0` items. The actual candidate pool came from area-based, festival, and stay list calls.
   - Example tool anchors:
     - `run_0f3679c894d84215`: `tool_e143172461e94c4e`, query `부산광역시 부산진구 외국인 야간 관광 사진 후보 감성 관광 액티비티`, count `0`
     - `run_b25b5f6c9ec24e1b`: keyword query for `인천 옹진군 대청도...`, count `0`

2. **TourAPI item 수집**
   - Area/festival/stay calls populate raw `TourAPIItem` candidates.
   - Region geo-filtering then removes items whose `ldong_regn_cd` / `ldong_signgu_cd` do not match the normalized location.
   - This is why Daecheongdo runs collected `50` raw items but only `3` geo-matched items.

3. **상세 정보 보강**
   - Geo-matched source items are enriched through `detail_common`, `detail_intro`, `detail_info`, and `detail_image`.
   - Enrichment updates each source item before source document generation. The document content includes title, type, region codes, address, event period, overview, homepage, detail intro/info lines, image candidate count, license, and data quality flags.

4. **source document 생성**
   - `build_source_document()` creates stable IDs shaped like `doc:tourapi:content:{contentid}`.
   - Metadata includes source, source family, content id/type, `region_code`, `sigungu_code`, `ldong_regn_cd`, `ldong_signgu_cd`, address, homepage, image URLs, detail availability, retrieved timestamp, trust level, and quality flags.
   - `source_documents` has no `run_id`, so documents are not run-scoped.

5. **Chroma indexing**
   - `index_source_documents()` upserts the same document IDs into Chroma collection `source_documents`.
   - Configured path is `./data/chroma` from the backend working directory, with the actual inspected files under `backend/data/chroma/`.
   - Collection metadata:
     - provider: `local`
     - model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
     - dimension: `384`
     - space: `cosine`

6. **RAG search**
   - Initial and post-enrichment vector searches query the global Chroma collection.
   - Filters are mostly geography and source:
     - `source=tourapi`
     - `ldong_regn_cd`
     - `ldong_signgu_cd` when the request has a district
     - post-enrichment also filters by a source id allow-list from the current candidate set.
   - Search is not product-scoped. The query text carries user intent, but the metadata filter primarily enforces region, not product/theme.

7. **EvidenceFusion**
   - EvidenceFusion receives `source_items`, `source_documents`, and `retrieved_documents`.
   - It produces `evidence_profile`, `productization_advice`, `data_coverage`, `unresolved_gaps`, `source_confidence`, and `ui_highlights`.
   - It does not create a separate evidence bundle per future product. The same fused candidate pool is later available to every product.

8. **ProductAgent 입력**
   - ProductAgent receives:
     - `retrieved_documents`: compact document cards with `doc_id`, title, content/snippet, score, and metadata
     - `source_items_shortlist`
     - `evidence_based_generation_context`: candidate product cards, claims, gaps, avoid rules, source confidence, and coverage
     - QA settings and normalized request
   - Server-side `validate_products()` accepts only source IDs present in `retrieved_documents`. Invalid IDs are removed. If no valid IDs remain, it falls back to the first available retrieved documents.

9. **QA 입력**
   - QAAgent receives:
     - generated products
     - visual assets
     - `retrieved_documents`
     - evidence context from EvidenceFusion
     - QA settings
   - The QA prompt includes allowed source IDs and source summaries. Deterministic QA then checks nonexistent source IDs, unsupported claims, unresolved gap leakage, and claim-limit violations.

### Source Document Accumulation Model

- Source documents are created or refreshed during a run from collected TourAPI items and enrichment results.
- The persistence model is global, not run-scoped:
  - `source_documents.id` is based on source item identity, not run id.
  - `source_documents` has no `run_id` column.
  - Chroma uses the same global document IDs.
- Existing run data can affect later runs when the later run uses matching location/source filters.
- A repeated run for the same place updates existing source documents and re-upserts them into Chroma rather than creating run-local copies.
- A region that has never been run has no local source documents unless a seed/pre-index process has already inserted them. During its first run, live TourAPI collection can create the initial documents, but pre-run RAG knowledge is absent.

Observed accumulation evidence:

- Current `source_documents` table contains `727` documents: `722` TourAPI and `5` KTO audio/theme documents.
- All product-selected source IDs in successful target runs existed in `source_documents`.
- Selected source documents were created before the target run in the checked cases, then refreshed during or after repeated runs. For example, `doc:tourapi:content:126119`, `doc:tourapi:content:2760809`, and `doc:tourapi:content:3112467` were created before `run_0f3679c894d84215` and later updated around that run window.

### Run-level RAG / Evidence Trace Table

| run_id | TourAPI search query | collected items | source docs | RAG query/filter/result | EvidenceFusion | ProductAgent selected source_ids | correction / fallback |
|---|---|---:|---:|---|---|---|---|
| `run_0f3679c894d84215` | `tool_e143172461e94c4e` keyword `부산광역시 부산진구 외국인 야간 관광 사진 후보 감성 관광 액티비티` -> `0`; area `21`, festival `2`, stay `10` | raw `33`, geo `33` | upsert/index `33` | initial `tool_8db3a600ccac445c`: `source=tourapi`, `ldong=26/230`, result `10`; post `tool_02564b32a1804762`, result `10` | `step_724c11ff834e48a0`: source_items `20`, docs `10`, source_doc_count `22`, confidence `0.896`, gaps `1` | `product_001`: `126119,2760809,3112467`; `product_002`: same; `product_003`: `2760809` | `product_001/002` had invalid IDs removed and fallback IDs assigned |
| `run_331348e02b064d28` | `tool_bc86e1c86e944d00` keyword `부산광역시 해운대구 외국인 혼잡 회피 수요 신호 액티비티` -> `0`; area `33`, festival `1`, stay `10` | raw `44`, geo `44` | upsert/index `44` | initial `tool_5998d30828614f16`: `source=tourapi`, `ldong=26/350`, result `10`; post `tool_40b2773f505d4cf0`, result `10` | `step_ceb57eee446447b0`: source_items `20`, docs `10`, source_doc_count `23`, confidence `0.883`, gaps `5` | `product_001`: `1878262,128828,3027738`; `product_002`: same; `product_003`: `1878262` | `product_001/002` had invalid IDs removed and fallback IDs assigned |
| `run_ac68dfed2d5345e3` | `tool_a4b0b1ddadd04e83` keyword `부산광역시 외국인 오디오 해설 역사·문화 스토리텔링 액티비티` -> `0`; area `40`, festival `9`, stay `10` | raw `59`, geo `59` | upsert/index `59` | initial `tool_1d4b373292d7419e`: `source=tourapi`, `ldong=26`, result `10`; post `tool_4ea3e242c14346d7`, result `10` | `step_32081b43fd5f492d`: source_items `20`, docs `10`, source_doc_count `30`, confidence `0.890`, gaps `3` | Product step `step_697ed80a21b44f6f`: all products use `theme:kto_audio:7c229...`, `128828`, `126119` | Product step corrected invalid IDs and fell back; final run failed at QA, so final_output is unavailable |
| `run_1241212633404670` | `tool_bac950b7ef504dee` keyword `부산광역시 부산진구 외국인 야간 관광 사진 후보 감성 관광 액티비티` -> `0`; area `21`, festival `2`, stay `10` | raw `33`, geo `33` | upsert/index `33` | initial `tool_5808d32a3ad34ef7`: `source=tourapi`, `ldong=26/230`, result `10`; post `tool_9ad10ae252704665`, result `10` | `step_76a20d72ea4840a0`: source_items `20`, docs `10`, source_doc_count `22`, confidence `0.896`, gaps `1` | `product_001`: `126119,2760809,3112467`; `product_002`: `2760809`; `product_003`: `126119,2760809,3112467` | `product_001/003` had invalid IDs removed and fallback IDs assigned |
| `run_01e6aa86a21f499f` | `tool_5baf4b6105764be9` keyword `부산광역시 해운대구 외국인 혼잡 회피 수요 신호 액티비티` -> `0`; area `33`, festival `1`, stay `10` | raw `44`, geo `44` | upsert/index `44` | initial `tool_8a5557fb9709483c`: `source=tourapi`, `ldong=26/350`, result `10`; post `tool_15343cdc5d374fc2`, result `10` | `step_acb82a90e38b4756`: source_items `20`, docs `10`, source_doc_count `23`, confidence `0.879`, gaps `6` | `product_001`: `1878262,128828,3027738`; `product_002`: `3027738,2784330`; `product_003`: `1878262` | `product_001` had invalid IDs removed and fallback IDs assigned |
| `run_b25b5f6c9ec24e1b` | `tool_6d9ca6730fc04e24` keyword `인천광역시 옹진군 대청도 일대 외국인 대청도 대청도 액티비티 섬 액티비티` -> `0`; area `40`, festival `0`, stay `10` | raw `50`, geo `3` | upsert/index `3` | initial `tool_379c64c256144d0a`: `source=tourapi`, `ldong=28/720`, Chroma result `10` but post-filter `2`; post `tool_76080d27f9e84028`, effective result `2` | `step_d5c9d1ba083145dd`: source_items `3`, docs `2`, source_doc_count `3`, confidence `0.713`, gaps `8` | `daecheongdo-beach...`: `2664741`; `daecheongdo-desert...`: `128012,2664741` | desert product had invalid IDs removed and fallback IDs assigned; only 2 products generated because evidence was thin |
| `run_f9182c6a30814cab` | `tool_bcc6e063bd594b1a` keyword `인천광역시 옹진군 대청도 일대 외국인 대청도 대청도 액티비티 섬 액티비티` -> `0`; area `40`, festival `0`, stay `10` | raw `50`, geo `3` | upsert/index `3` | initial `tool_f5623eae78304c70`: `source=tourapi`, `ldong=28/720`, Chroma result `10` but post-filter `2`; post `tool_8c9b986ce69e4cf2`, effective result `2` | `step_626a594924d84c13`: source_items `3`, docs `2`, source_doc_count `3`, confidence `0.713`, gaps `8` | `daecheongdo-desert...`: `128012,2664741`; `daecheongdo-fishing...`: `2664741` | desert product had invalid IDs removed and fallback IDs assigned; only 2 products generated because evidence was thin |
| `run_87d306e83f1549c3` | `tool_fb3dc6317ee24593` keyword `부산광역시 부산진구 외국인 야간 관광 감성 관광 대중교통 액티비티` -> `0`; area `21`, festival `2`, stay `10` | raw `33`, geo `33` | upsert/index `33` | initial `tool_339c61648ee54cde`: `source=tourapi`, `ldong=26/230`, result `10`; post `tool_20c16aec25134378`, result `10` | `step_c2ea13654d2a484a`: source_items `20`, docs `10`, source_doc_count `20`, confidence `0.893`, gaps `2` | `product_001`: `3014435,126119,2760809`; `product_002`: same; `product_003`: `1046349,3014435` | `product_001/002` had invalid IDs removed and fallback IDs assigned |
| `run_bec1f1b99da44fe5` | `tool_76e49926850e4f90` keyword `서울특별시 중구 외국인 야간 관광 액티비티` -> `0`; area `26`, festival `11`, stay `10` | raw `47`, geo `47` | upsert/index `47` | initial `tool_d38f536d679348a0`: `source=tourapi`, `ldong=11/140`, result `10`; post `tool_7ac5fb2575dd4e6a`, result `10` | `step_4ad4b15595bc46af`: source_items `20`, docs `10`, source_doc_count `23`, confidence `0.876`, gaps `7` | `product_001`: `127015,131901,292961`; `product_002`: same; `product_003`: `292961` | all products had invalid IDs removed; `product_001/002` also received fallback IDs |

Step anchors:

| run_id | BaselineDataAgent | EvidenceFusion | ProductAgent | QAAgent |
|---|---|---|---|---|
| `run_0f3679c894d84215` | `step_79fa3b5ab8bb4a76` | `step_724c11ff834e48a0` | `step_38a805a0090e45bf` | `step_df8d6cb23e4148fc` |
| `run_331348e02b064d28` | `step_ec8b98c62e9c43fd` | `step_ceb57eee446447b0` | `step_1cea8f3f209b49fe` | `step_aef2bca154a04018` |
| `run_ac68dfed2d5345e3` | `step_67e687c31ddf4792` | `step_32081b43fd5f492d` | `step_697ed80a21b44f6f` | `step_bae55f4a53204faa` failed |
| `run_1241212633404670` | `step_6a786cd233974c58` | `step_76a20d72ea4840a0` | `step_c272dda8f5954d2f` | `step_79c1befdd91f426e` |
| `run_01e6aa86a21f499f` | `step_26d0bde6f19147f6` | `step_acb82a90e38b4756` | `step_2c47b45ee7834d9f` | `step_09f5618a5c23467e` |
| `run_b25b5f6c9ec24e1b` | `step_5500531ff7ba4587` | `step_d5c9d1ba083145dd` | `step_7bae1008f4664dba` | `step_65b2662f10d14e73` |
| `run_f9182c6a30814cab` | `step_6156c8c64b834758` | `step_626a594924d84c13` | `step_fc403ec3d474415b` | `step_172d63bc6ed142c9` |
| `run_87d306e83f1549c3` | `step_f7c6e6f91c744c0a` | `step_c2ea13654d2a484a` | `step_ac813a0bd83f4b70` | `step_313133d4e8d24160` |
| `run_bec1f1b99da44fe5` | `step_080afe8f58824f01` | `step_4ad4b15595bc46af` | `step_12d67f93ca084e04` | `step_9b5fb0f04611450f` |

### RAG Failure / Mismatch Cases

#### 1. source_id correction and fallback

- ProductAgent is prompted to use only retrieved `doc_id` values, but it still returns nonexistent source IDs in many products.
- Server-side `validate_products()` removes invalid IDs, then assigns fallback IDs from the retrieved document list if a product has no valid source IDs.
- This correction appears in `needs_review` as:
  - model returned source ids not present in the evidence list, so the server excluded them
  - product had too few usable evidence ids, so the server filled with available evidence
- Affected runs/products:
  - `run_0f3679c894d84215`: `product_001`, `product_002`
  - `run_331348e02b064d28`: `product_001`, `product_002`
  - `run_ac68dfed2d5345e3`: `product_001`, `product_002`, `product_003`
  - `run_1241212633404670`: `product_001`, `product_003`
  - `run_01e6aa86a21f499f`: `product_001`
  - `run_b25b5f6c9ec24e1b`: `daecheongdo-desert-photo-tour-001`
  - `run_f9182c6a30814cab`: `daecheongdo-desert-photo-tour`
  - `run_87d306e83f1549c3`: `product_001`, `product_002`
  - `run_bec1f1b99da44fe5`: `product_001`, `product_002`, `product_003`

#### 2. Products and evidence are loosely connected

- The final source IDs are valid document IDs, but validity only means the IDs exist in retrieved documents. It does not mean they are the best evidence for the product.
- Examples:
  - `run_331348e02b064d28` generated `해운대 야경 크루즈: 더베이101 요트 투어`, but selected sources include `부산 갈맷길 2코스`, `부산 올림픽동산`, and `고흐의 길`.
  - `run_0f3679c894d84215` generated `백양산 자연 속 힐링`, but fallback evidence includes broad 부산진구 documents such as `부산 어린이대공원`, `송상현광장`, and `부산정중앙공원`.
  - `run_bec1f1b99da44fe5` generated `서울 세계 문화의 밤: 서울세계도시문화축제`, but selected evidence is `대한성공회 서울주교좌성당`, `명동사격장`, and `서울 왕궁수문장 교대의식`.

#### 3. Region filtering is stronger than theme/product filtering

- Search filters by source and location, but product/theme fit is mostly left to semantic query ranking and the LLM.
- The keyword search returned `0` for all target runs, so the pipeline relies on broad area/festival/stay lists.
- If the region contains many generic attractions, RAG retrieves locally valid but product-weak evidence.
- `run_ac68dfed2d5345e3` uses only `ldong_regn_cd=26` without a district filter, so 부산-wide KTO audio/theme documents entered the retrieved document set.

#### 4. Evidence scarcity directly lowers product quality

- Daecheongdo runs are the clearest low-evidence case:
  - raw collection: `50`
  - geo-matched source items: `3`
  - effective RAG docs: `2`
  - EvidenceFusion confidence: `0.713`
  - unresolved gaps: `8`
  - ProductAgent generated only `2` products instead of the requested `3`
- QA and product `needs_review` then become dominated by missing operating hours, booking, price, nearby places, and image/visual completeness.

### Answers to Required Questions

1. **source document는 run 실행 때만 생기는지**
   - Source documents are created or refreshed during runs from collected source items. There is also existing global data already present, so a run can reuse documents created by earlier runs.

2. **기존 run의 source document가 다음 run에도 검색되는지**
   - Yes. `source_documents` and Chroma are global. Later runs can retrieve earlier documents when metadata filters match.

3. **한 번도 실행하지 않은 지역은 근거가 없는 구조인지**
   - Before the first live collection or seed ingestion, yes. The first run can create documents from TourAPI, but there is no run-local preloaded knowledge unless the global DB/Chroma already has seeded data for that region.

4. **RAG search가 지역/상품 의도에 맞게 필터링되는지**
   - Region filtering is explicit and generally effective. Product intent filtering is weaker because filters are not product-scoped and keyword search returned no direct results in these samples.

5. **EvidenceFusion이 상품별 근거를 제대로 분리하는지**
   - No. EvidenceFusion produces one fused pool and productization context for the run. Product-level isolation happens later, loosely, through ProductAgent source ID selection and server validation.

6. **source_id 보정이 왜 발생하는지**
   - ProductAgent returns IDs outside the allowed `retrieved_documents` list. `validate_products()` removes invalid IDs and falls back to available retrieved docs when needed.

7. **상품과 근거가 느슨하게 연결되는지**
   - Yes. Fallback and shared evidence pools cause valid-but-generic source IDs to attach to products whose specific claims are not strongly supported by those documents.

8. **ProductAgent 입력에 evidence가 어떤 형태로 들어가는지**
   - ProductAgent receives retrieved document cards, source item shortlist, and a compact evidence context containing candidate product cards, claims, gaps, coverage, source confidence, and avoid rules.

9. **QA 입력에 product/evidence/claim limits가 어떤 형태로 들어가는지**
   - QA receives generated product JSON, retrieved document summaries, evidence context, QA settings, and product claim limits. The deterministic QA layer checks allowed source IDs, unresolved gaps, and unsupported/unsafe claim patterns.

### Evidence Selection Improvement Candidates

- **Source relevance scoring**
  - Add explicit product-intent relevance scores after retrieval. Score each candidate by place name overlap, activity/theme match, required audience/context, evidence freshness, and detail completeness.

- **Product별 evidence isolation**
  - Split EvidenceFusion output into product candidate bundles before ProductAgent generation. Each bundle should have its own required, optional, and rejected source IDs.

- **source_id validation**
  - Keep current server-side validation, but surface correction as a hard quality signal. A product that required fallback should be downgraded or regenerated instead of silently receiving generic evidence.

- **run-scoped vs global knowledge strategy**
  - Decide whether RAG should use only current-run documents, global documents, or a hybrid. A practical hybrid is:
    - current-run documents as primary
    - global documents as secondary only when region/source/date filters and relevance score pass stricter thresholds
    - provenance metadata showing which run last refreshed each document

- **pre-index / seed ingestion**
  - For first-run regions, pre-indexing would reduce the cold-start gap. Seed ingestion should include region coverage metadata and source freshness so RAG can tell seeded evidence from live run evidence.

### 15.0-D Summary

- Source documents are global, item-id keyed records. Runs create or refresh them, but they are not isolated by run.
- RAG is geographically filtered but only weakly product/theme filtered. This causes locally valid evidence to attach to products with loose relevance.
- EvidenceFusion does not yet enforce per-product evidence isolation. ProductAgent often returns invalid source IDs, and server fallback then attaches generic available documents.
- The largest quality risks are:
  - source ID correction/fallback hides weak evidence selection
  - product-specific evidence is not isolated before generation
  - sparse or first-run regions depend on live TourAPI coverage and can produce too few strong evidence documents

---

Back to index: [27_PHASE_15_QUALITY_AUDIT.md](27_PHASE_15_QUALITY_AUDIT.md)
