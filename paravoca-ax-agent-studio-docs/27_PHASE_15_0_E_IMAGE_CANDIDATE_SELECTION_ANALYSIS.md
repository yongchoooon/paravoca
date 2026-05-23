# Phase 15.0-E Image Candidate Selection Analysis

Scope: this section analyzes image candidate generation, storage, and product association for the same nine Phase 15.0 runs. Revision runs and poster data are excluded. No product code was changed.

Based on 15.0-D: source documents are global item-id records, RAG is strongly geography-filtered but weakly product/theme-filtered, EvidenceFusion builds a run-level shared evidence pool, and ProductAgent source ID fallback can attach generic evidence to products. 15.0-E checks whether the same structure contaminates image candidates.

Initial answer: yes. Image assets are usually correctly attached to source items, but products often receive fallback or weakly relevant source IDs first. The images then follow those source IDs, so the product can display a direct image for the attached evidence while still being semantically wrong for the product concept.

Runs with unavailable product-level image analysis:
- `run_ac68dfed2d5345e3 status=failed, final_output is not an object`

### Current Image Candidate Flow

```text
TourAPI detail enrichment
  -> kto_tour_detail_image / detailImage2 per content_id
  -> tourism_visual_assets upsert
     - source_family=kto_tourapi_kor
     - source_item_id=tourapi:content:{content_id}
     - entity_id=entity:tourapi:content:{content_id}
  -> source_documents metadata
     - image_url, detail_image_count, visual_asset_count, image_candidates
  -> EvidenceFusion candidate_evidence_cards
     - visual_candidates copied from assets for each source item
  -> ProductAgent
     - chooses source_ids from retrieved_documents, then server validates/fallbacks
  -> UI
     - image candidates can be shown from product source_ids/source document metadata/evidence cards
```

Other visual APIs (`kto_tourism_photo`, `kto_photo_contest`) are implemented in code and store assets in the same `tourism_visual_assets` table with `needs_license_review`, but the target runs were dominated by `kto_tour_detail_image` calls. No target run showed a product-level image bundle generated independently of source IDs.

### Run-level Image Candidate Table

| run_id | image-related API/tool calls | image asset count | source document image count | product count | product-image direct match count | likely mismatch count | source_id fallback impact | primary mismatch type |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- | --- |
| `run_0f3679c894d84215` | kto_tour_detail_image x12 (12 calls) | 79 | 34 candidates in 9 docs | 3 | 1 | 2 | 2 product(s) | fallback contamination |
| `run_331348e02b064d28` | kto_tour_detail_image x12 (12 calls) | 54 | 36 candidates in 10 docs | 3 | 1 | 2 | 2 product(s) | fallback contamination |
| `run_ac68dfed2d5345e3` | kto_tour_detail_image x16 (16 calls) | 125 | 0 | 0 | 0 | 0 | not analyzable | final_output unavailable |
| `run_1241212633404670` | kto_tour_detail_image x12 (12 calls) | 79 | 34 candidates in 9 docs | 3 | 1 | 2 | 2 product(s) | fallback contamination |
| `run_01e6aa86a21f499f` | kto_tour_detail_image x12 (12 calls) | 54 | 36 candidates in 10 docs | 3 | 2 | 1 | 1 product(s) | direct match |
| `run_b25b5f6c9ec24e1b` | kto_tour_detail_image x3 (3 calls) | 6 | 6 candidates in 1 docs | 2 | 1 | 1 | 1 product(s) | fallback contamination |
| `run_f9182c6a30814cab` | kto_tour_detail_image x3 (3 calls) | 6 | 6 candidates in 1 docs | 2 | 1 | 1 | 1 product(s) | fallback contamination |
| `run_87d306e83f1549c3` | kto_tour_detail_image x20 (20 calls) | 56 | 33 candidates in 10 docs | 3 | 1 | 2 | 2 product(s) | fallback contamination |
| `run_bec1f1b99da44fe5` | kto_tour_detail_image x12 (12 calls) | 27 | 32 candidates in 10 docs | 3 | 0 | 3 | 3 product(s) | fallback contamination |

### Product-level Image Relevance Table

| run_id | product_id | product title | product source_ids | source_id correction/fallback | candidate image title/source_item_id/source_family | direct source match | product relevance judgment | mismatch category |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `run_0f3679c894d84215` | `product_001` | 부산진 별빛 산책: 밤의 낭만과 빛의 예술 | doc:tourapi:content:126119, doc:tourapi:content:2760809, doc:tourapi:content:3112467 | yes | 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (4) / tourapi:content:126119 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_0f3679c894d84215` | `product_002` | 백양산 자연 속 힐링: 도심 속 숨겨진 녹색 오아시스 | doc:tourapi:content:126119, doc:tourapi:content:2760809, doc:tourapi:content:3112467 | yes | 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (4) / tourapi:content:126119 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_0f3679c894d84215` | `product_003` | 송상현광장: 역사와 문화가 숨 쉬는 도심 속 휴식처 | doc:tourapi:content:2760809 | no | 부산_송상현광장 (10) / tourapi:content:2760809 / kto_tourapi_kor; 부산_송상현광장 (11) / tourapi:content:2760809 / kto_tourapi_kor; 부산_송상현광장 (2) / tourapi:content:2760809 / kto_tourapi_kor | yes | direct_or_partial_title_match: 송상현광장 | direct match |
| `run_331348e02b064d28` | `product_001` | 해운대 모래축제: 여름 시즌 가족 체험 | doc:tourapi:content:1878262, doc:tourapi:content:128828, doc:tourapi:content:3027738 | yes | 부산_부산 올림픽동산 (1) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (10) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (11) / tourapi:content:128828 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_331348e02b064d28` | `product_002` | 해운대 야경 크루즈: 더베이101 요트 투어 | doc:tourapi:content:1878262, doc:tourapi:content:128828, doc:tourapi:content:3027738 | yes | 부산_부산 올림픽동산 (1) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (10) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (11) / tourapi:content:128828 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_331348e02b064d28` | `product_003` | 해운대 해안 절경 트레킹: 부산 갈맷길 2코스 | doc:tourapi:content:1878262 | no | 부산_[부산 갈맷길] 2코스 2구간 (10) / tourapi:content:1878262 / kto_tourapi_kor; 부산_[부산 갈맷길] 2코스 2구간 (11) / tourapi:content:1878262 / kto_tourapi_kor; 부산_[부산 갈맷길] 2코스 2구간 (2) / tourapi:content:1878262 / kto_tourapi_kor | yes | direct_or_partial_title_match: 갈맷길 | direct match |
| `run_1241212633404670` | `product_001` | 부산진 별빛 야경 산책 | doc:tourapi:content:126119, doc:tourapi:content:2760809, doc:tourapi:content:3112467 | yes | 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (4) / tourapi:content:126119 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_1241212633404670` | `product_002` | 송상현광장, 도심 속 문화 산책 | doc:tourapi:content:2760809 | no | 부산_송상현광장 (10) / tourapi:content:2760809 / kto_tourapi_kor; 부산_송상현광장 (11) / tourapi:content:2760809 / kto_tourapi_kor; 부산_송상현광장 (2) / tourapi:content:2760809 / kto_tourapi_kor | yes | direct_or_partial_title_match: 송상현광장 | direct match |
| `run_1241212633404670` | `product_003` | 백양산, 부산 국가지질공원 트레킹 | doc:tourapi:content:126119, doc:tourapi:content:2760809, doc:tourapi:content:3112467 | yes | 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (4) / tourapi:content:126119 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_01e6aa86a21f499f` | `product_001` | 해운대 요트 투어: 마린시티와 광안대교 야경 감상 | doc:tourapi:content:1878262, doc:tourapi:content:128828, doc:tourapi:content:3027738 | yes | 부산_부산 올림픽동산 (1) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (10) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (11) / tourapi:content:128828 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_01e6aa86a21f499f` | `product_002` | 해운대 숨은 명소: 고흐의 길 산책과 미포항의 여유 | doc:tourapi:content:3027738, doc:tourapi:content:2784330 | no | 미포항 (2) / tourapi:content:2784330 / kto_tourapi_kor; 미포항 (3) / tourapi:content:2784330 / kto_tourapi_kor; 미포항 (4) / tourapi:content:2784330 / kto_tourapi_kor | yes | direct_or_partial_title_match: 고흐의 | direct match |
| `run_01e6aa86a21f499f` | `product_003` | 해운대 해안 트레킹: 부산 갈맷길 2코스 2구간 걷기 | doc:tourapi:content:1878262 | no | 부산_[부산 갈맷길] 2코스 2구간 (10) / tourapi:content:1878262 / kto_tourapi_kor; 부산_[부산 갈맷길] 2코스 2구간 (11) / tourapi:content:1878262 / kto_tourapi_kor; 부산_[부산 갈맷길] 2코스 2구간 (2) / tourapi:content:1878262 / kto_tourapi_kor | yes | direct_or_partial_title_match: 갈맷길, 구간 | direct match |
| `run_b25b5f6c9ec24e1b` | `daecheongdo-desert-photo-tour-001` | 대청도 옥죽동 모래사막 인생샷 투어 | doc:tourapi:content:128012, doc:tourapi:content:2664741 | yes | 농여해변과 미아해변_1_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_2_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_3_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_b25b5f6c9ec24e1b` | `daecheongdo-beach-fishing-healing-002` | 대청도 농여해변 힐링 & 낚시 체험 | doc:tourapi:content:2664741 | no | 농여해변과 미아해변_1_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_2_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_3_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor | yes | direct_or_partial_title_match: 농여해변 | direct match |
| `run_f9182c6a30814cab` | `daecheongdo-desert-photo-tour` | 대청도 옥죽동 모래사막 인생샷 투어 | doc:tourapi:content:128012, doc:tourapi:content:2664741 | yes | 농여해변과 미아해변_1_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_2_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_3_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_f9182c6a30814cab` | `daecheongdo-fishing-and-relaxation-tour` | 대청도 농여해변 힐링 낚시 투어 | doc:tourapi:content:2664741 | no | 농여해변과 미아해변_1_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_2_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_3_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor | yes | direct_or_partial_title_match: 농여해변 | direct match |
| `run_87d306e83f1549c3` | `product_001` | 부산 가족 축제: 5월의 밤, 특별한 추억 만들기 | doc:tourapi:content:3014435, doc:tourapi:content:126119, doc:tourapi:content:2760809 | yes | 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (4) / tourapi:content:126119 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_87d306e83f1549c3` | `product_002` | 부산진 별빛 산책길: 낭만적인 밤의 산책 | doc:tourapi:content:3014435, doc:tourapi:content:126119, doc:tourapi:content:2760809 | yes | 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (4) / tourapi:content:126119 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_87d306e83f1549c3` | `product_003` | 서면 1번가: 밤의 예술과 미식 탐험 | doc:tourapi:content:1046349, doc:tourapi:content:3014435 | no | 부산_서면1번가 (1) / tourapi:content:1046349 / kto_tourapi_kor; 부산_서면1번가 (10) / tourapi:content:1046349 / kto_tourapi_kor; 부산_서면1번가 (11) / tourapi:content:1046349 / kto_tourapi_kor | yes | direct_or_partial_title_match: 번가, 서면 | direct match |
| `run_bec1f1b99da44fe5` | `1` | 서울 밤의 문화 산책: 덕수궁 돌담길과 정동길 | doc:tourapi:content:127015, doc:tourapi:content:131901, doc:tourapi:content:292961 | yes | 서울_대한성공회 서울주교좌성당 (2) / tourapi:content:127015 / kto_tourapi_kor; 서울_대한성공회 서울주교좌성당 (3) / tourapi:content:127015 / kto_tourapi_kor; 서울_대한성공회 서울주교좌성당 (4) / tourapi:content:127015 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_bec1f1b99da44fe5` | `2` | 서울 세계 문화의 밤: 서울세계도시문화축제 | doc:tourapi:content:127015, doc:tourapi:content:131901, doc:tourapi:content:292961 | yes | 서울_대한성공회 서울주교좌성당 (2) / tourapi:content:127015 / kto_tourapi_kor; 서울_대한성공회 서울주교좌성당 (3) / tourapi:content:127015 / kto_tourapi_kor; 서울_대한성공회 서울주교좌성당 (4) / tourapi:content:127015 / kto_tourapi_kor | yes | weak_title_match | fallback contamination |
| `run_bec1f1b99da44fe5` | `3` | 조선 왕궁의 밤: 수문장 교대의식과 덕수궁 야경 | doc:tourapi:content:292961 | yes | 서울 왕궁수문장 교대의식 (1).jpg / tourapi:content:292961 / kto_tourapi_kor; 서울 왕궁수문장 교대의식 (2).jpg / tourapi:content:292961 / kto_tourapi_kor; 서울 왕궁수문장 교대의식 (3).jpg / tourapi:content:292961 / kto_tourapi_kor | yes | direct_or_partial_title_match: 왕궁수문장 | fallback contamination |

### Image Mismatch Cases

Mismatch category counts:
- fallback contamination: 14
- direct match: 8

Representative cases:
- `run_0f3679c894d84215` / `product_001` / 부산진 별빛 산책: 밤의 낭만과 빛의 예술: fallback contamination. Product sources: 부산 어린이대공원, 송상현광장, 부산정중앙공원. Image sample: 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_0f3679c894d84215` / `product_002` / 백양산 자연 속 힐링: 도심 속 숨겨진 녹색 오아시스: fallback contamination. Product sources: 부산 어린이대공원, 송상현광장, 부산정중앙공원. Image sample: 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_331348e02b064d28` / `product_001` / 해운대 모래축제: 여름 시즌 가족 체험: fallback contamination. Product sources: 부산 올림픽동산, [부산 갈맷길] 2코스 2구간, 고흐의 길. Image sample: 부산_부산 올림픽동산 (1) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (10) / tourapi:content:128828 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_331348e02b064d28` / `product_002` / 해운대 야경 크루즈: 더베이101 요트 투어: fallback contamination. Product sources: 부산 올림픽동산, [부산 갈맷길] 2코스 2구간, 고흐의 길. Image sample: 부산_부산 올림픽동산 (1) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (10) / tourapi:content:128828 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_1241212633404670` / `product_001` / 부산진 별빛 야경 산책: fallback contamination. Product sources: 부산 어린이대공원, 송상현광장, 부산정중앙공원. Image sample: 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_1241212633404670` / `product_003` / 백양산, 부산 국가지질공원 트레킹: fallback contamination. Product sources: 부산 어린이대공원, 송상현광장, 부산정중앙공원. Image sample: 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_01e6aa86a21f499f` / `product_001` / 해운대 요트 투어: 마린시티와 광안대교 야경 감상: fallback contamination. Product sources: 부산 올림픽동산, [부산 갈맷길] 2코스 2구간, 고흐의 길. Image sample: 부산_부산 올림픽동산 (1) / tourapi:content:128828 / kto_tourapi_kor; 부산_부산 올림픽동산 (10) / tourapi:content:128828 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_b25b5f6c9ec24e1b` / `daecheongdo-desert-photo-tour-001` / 대청도 옥죽동 모래사막 인생샷 투어: fallback contamination. Product sources: 대청도, 대청도 농여해변. Image sample: 농여해변과 미아해변_1_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_2_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_f9182c6a30814cab` / `daecheongdo-desert-photo-tour` / 대청도 옥죽동 모래사막 인생샷 투어: fallback contamination. Product sources: 대청도, 대청도 농여해변. Image sample: 농여해변과 미아해변_1_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor; 농여해변과 미아해변_2_국가지질공원 / tourapi:content:2664741 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_87d306e83f1549c3` / `product_001` / 부산 가족 축제: 5월의 밤, 특별한 추억 만들기: fallback contamination. Product sources: 부산 어린이대공원, 송상현광장, 서면먹자골목. Image sample: 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_87d306e83f1549c3` / `product_002` / 부산진 별빛 산책길: 낭만적인 밤의 산책: fallback contamination. Product sources: 부산 어린이대공원, 송상현광장, 서면먹자골목. Image sample: 부산_부산 어린이대공원 (1) / tourapi:content:126119 / kto_tourapi_kor; 부산_부산 어린이대공원 (3) / tourapi:content:126119 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.
- `run_bec1f1b99da44fe5` / `1` / 서울 밤의 문화 산책: 덕수궁 돌담길과 정동길: fallback contamination. Product sources: 대한성공회 서울주교좌성당, 명동사격장, 서울 왕궁수문장 교대의식. Image sample: 서울_대한성공회 서울주교좌성당 (2) / tourapi:content:127015 / kto_tourapi_kor; 서울_대한성공회 서울주교좌성당 (3) / tourapi:content:127015 / kto_tourapi_kor. Judgment: image exists on fallback/generic source but title relevance is weak.

Findings by required category:
- API data gap: present in the wider data model, but not the dominant target-run problem. Most mismatched products did have image assets on their selected source IDs.
- query problem: all target runs had keyword search result `0` in 15.0-D, so image enrichment followed broad area/festival/stay candidate pools rather than precise product-intent search results.
- selection problem: relevant images can exist for source items, but product-level selection is only as good as the product source_ids. There is no separate image relevance ranking against product title/core_value/itinerary.
- product-evidence mismatch: visible in products where selected source docs are locally valid but weakly related to the generated product concept.
- fallback contamination: the dominant issue. When source_id fallback attaches generic evidence, images from that generic evidence can appear product-relevant because they are direct images for the fallback source, not for the intended product.
- metadata gap: `tourism_visual_assets` has useful source_item_id/source_family/title fields, but compact prompt/UI objects do not retain a product-level relevance score or whether the image is direct, same-family, or fallback.
- UI presentation issue: if UI shows these candidates simply as product images, users cannot distinguish direct product images from fallback/source-pool candidates.

### Image Relevance Criteria

- First priority: direct match between product source_id -> source_documents.source_item_id -> tourism_visual_assets.source_item_id.
- Second priority: same content_id/source_family match when the source document and image are derived from the same TourAPI/KTO item.
- Third priority: semantic match between product title/one_liner/core_value/itinerary and image/source title, including named place/event/activity overlap.
- Region-only fallback should be allowed only when the product explicitly lacks direct images and the UI labels it as a regional reference image, not a product image.
- Images attached to fallback-corrected source_ids should not be treated as representative until product-source relevance is revalidated.
- If a product source_id correction occurred, the image selector should require stronger title/activity overlap before showing the image as a primary candidate.

### Phase 16+ Improvement Backlog

- Build product-source-image hard linking: ProductAgent should receive or return product evidence bundles that include source_ids and image candidate ids together.
- Add image candidate scoring with source match, content_id match, title/activity overlap, source confidence, image availability, and license status.
- Limit image candidates for products that required source_id fallback; require regeneration or mark them as fallback references.
- Split run-level visual pool from product-level image candidates in the API/UI response.
- UI should label image provenance: direct product evidence, same-source candidate, or regional fallback.
- Narrow image/API query planning around specific candidate cards rather than broad regional pools when possible.
- Preserve richer image metadata in compact structures: source_item_id, source_family, content_id, source title, relevance reason, and fallback flag.
- Improve EvidenceFusion so product evidence bundles and image bundles are created before ProductAgent generation, not inferred after source_id fallback.

### 15.0-E Summary

- Product-level rows analyzed: 22.
- Runs with product-level image analysis unavailable: `run_ac68dfed2d5345e3 status=failed, final_output is not an object`.
- Biggest mismatch drivers:
  - fallback contamination: 14 product(s)
  - direct match: 8 product(s)
- Conclusion on 15.0-D source_id fallback: connected. Image assets are item-linked correctly, but fallback source_ids cause item-linked images from generic or weakly related evidence to become product candidates. The image selector needs product-level source relevance validation, not just source_item_id existence.

---

Back to index: [27_PHASE_15_QUALITY_AUDIT.md](27_PHASE_15_QUALITY_AUDIT.md)
