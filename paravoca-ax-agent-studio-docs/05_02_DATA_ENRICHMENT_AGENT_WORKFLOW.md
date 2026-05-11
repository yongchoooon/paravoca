# 데이터 보강 Agent 구현 계획

작성 기준일: 2026-05-06

이 문서는 한국관광공사 OpenAPI 묶음을 PARAVOCA AX Agent Studio의 workflow에 붙이는 구현 계획입니다. 핵심은 전체 API를 매번 호출하는 방식이 아니라, 현재 run의 요청, 수집된 데이터, 상품 초안, QA 결과를 보고 필요한 보강만 실행하는 구조입니다.

구현 상태: Phase 10에서 1차 구현을 완료했고, Phase 10.2에서 `DataGapProfilerAgent`, `ApiCapabilityRouterAgent`, 네 개의 API family planner, `EvidenceFusionAgent`를 Gemini prompt + JSON schema 기반 판단으로 전환했습니다. Phase 12.3 기준 현재 코드는 기본 TourAPI 수집 이후 raw 후보를 `TOURAPI_CANDIDATE_SHORTLIST_LIMIT` 기준 shortlist로 줄이고, Gemini가 shortlist 기준 gap report를 만듭니다. `DataGapProfilerAgent`는 반복적인 `missing_overview`를 만들지 않고 `missing_detail_info`로 통합하며, 후보별 item-level gap은 최대 1개, 전체 gap은 최대 24개로 제한합니다. Router는 gap을 planner lane으로 분배하고, `TourApiDetailPlannerAgent`, `VisualDataPlannerAgent`, `RouteSignalPlannerAgent`, `ThemeDataPlannerAgent`가 각자 짧은 계획을 만듭니다. 코드 action인 `EnrichmentExecutor`는 KorService2 상세 보강, Visual API 이미지 후보, Route/Signal API 보조 근거, Theme API 테마 후보를 계획된 call에 한해서만 실행합니다. shortlist 안에서 실행 가능한 `contentId` 대상은 `ENRICHMENT_MAX_CALL_BUDGET=6` 때문에 임의로 잘리지 않습니다. 아직 provider가 없는 KTO operation은 plan/skipped 상태로만 기록합니다. OfficialWebEvidenceAgent와 HumanDataRequestAgent는 후속 Phase 범위입니다.

## 목표

1. 현재 TourAPI 목록 조회 중심 데이터를 상세/테마/수요/이미지/연관 데이터로 보강한다.
2. Agent가 데이터 공백을 구조화해 어떤 API 호출이 필요한지 판단한다.
3. 호출 결과를 상품 기획, 상세페이지 카피, FAQ, QA, Poster Studio에 재사용한다.
4. 운영자가 확인해야 하는 항목과 API로 확인된 항목을 분리한다.
5. API 트래픽, 지연 시간, 라이선스, 해석 주의사항을 실행 로그에 남긴다.

## 제안 workflow

현재 workflow:

```text
Planner
  -> Data
  -> Research
  -> Product
  -> Marketing
  -> QA
  -> Human Approval
```

Phase 10 구현 workflow:

```text
Planner
  -> GeoResolverAgent
  -> BaselineDataAgent
  -> DataGapProfilerAgent
  -> ApiCapabilityRouterAgent
  -> TourApiDetailPlannerAgent
  -> VisualDataPlannerAgent
  -> RouteSignalPlannerAgent
  -> ThemeDataPlannerAgent
  -> EnrichmentExecutor
  -> EvidenceFusionAgent
  -> Research
  -> Product
  -> Marketing
  -> QA
  -> Human Approval
```

후속 확장 workflow에서는 EvidenceFusion 이후에도 운영 필드가 부족할 때 `OfficialWebEvidenceAgent`와 `HumanDataRequestAgent`를 추가합니다.

Revision/QA 기반 보강 workflow:

```text
Manual Edit or QA Issue
  -> DataGapProfilerAgent
  -> ApiCapabilityRouterAgent
  -> TourApiDetailPlannerAgent / VisualDataPlannerAgent / RouteSignalPlannerAgent / ThemeDataPlannerAgent
  -> EnrichmentExecutor
  -> EvidenceFusionAgent
  -> OfficialWebEvidenceAgent, if needed
  -> HumanDataRequestAgent, if needed
  -> RevisionPatchAgent or QA
```

Poster Studio 연계 workflow:

```text
Approved or Reviewable Run
  -> PosterContextBuilder
  -> DataGapProfilerAgent
  -> ApiCapabilityRouterAgent
  -> VisualDataEnrichment
  -> PosterPromptAgent
  -> Human Poster Option Review
  -> PosterImageAgent
  -> PosterQAReview
```

## Agent 구성

### 1. BaselineDataAgent

현재 `DataAgent`의 역할을 분리한 이름입니다. 기존 구현을 보존하면서, 기본 TourAPI 조회를 담당합니다.

담당:

- 지역 코드 조회
- 지역/키워드/행사/숙박 목록 조회
- 기본 `tourism_items` 저장
- 기본 `source_documents` 저장 및 vector indexing

현재 구현과의 연결:

- `backend/app/tools/tourism.py`
- `backend/app/api/routes_data.py`
- `backend/app/agents/workflow.py::data_agent`
- `backend/app/tools/tourism_enrichment.py`

현재 코드 반영:

- 프로젝트 Phase 9에서 `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2` provider method와 상세 보강 저장 로직을 구현했습니다.
- `categoryCode2`, `locationBasedList2` provider method도 추가했지만, 아직 DataGapProfiler/Router가 호출 여부를 판단하는 구조에는 연결하지 않았습니다.
- source document content에는 상세 소개, 이용정보, 이미지 후보 metadata가 반영됩니다.
- Run Detail Evidence에서는 상세 정보와 이미지 후보를 확인할 수 있습니다.

남은 개선:

- `searchFestival2` 호출 시 `end_date`를 API가 지원하는 범위 안에서 더 정교하게 반영할 수 있는지 명세 확인
- 상세 보강을 모든 item에 무조건 적용하지 않고 DataGapProfilerAgent가 필요한 대상만 선택하게 개선
- location/category 결과를 코스 조합과 상품 ranking에 반영

### 2. DataGapProfilerAgent

수집된 데이터와 생성 목표를 보고 부족한 정보를 구조화합니다.

입력:

```json
{
  "normalized_request": {},
  "source_items": [],
  "retrieved_documents": [],
  "products": [],
  "marketing_assets": [],
  "qa_report": {}
}
```

출력:

```json
{
  "data_gaps": [
    {
      "id": "gap_001",
      "gap_type": "missing_image_asset",
      "severity": "medium",
      "required_for": ["poster_studio", "marketing_assets"],
      "target_entities": ["tourapi:content:12345"],
      "candidate_source_families": ["kto_tourism_photo", "kto_photo_contest"],
      "reason": "상품 후보에 대표 이미지가 없고 포스터 생성 옵션 추천에 사용할 시각 소재가 부족합니다.",
      "confidence": 0.82
    }
  ]
}
```

판단 규칙:

| 조건 | 생성할 gap |
|---|---|
| `overview`가 비어 있거나 너무 짧음 | `missing_detail_common` |
| 운영 시간/요금/주차/휴무 정보 없음 | `missing_detail_info` |
| 대표 이미지 없음 | `missing_image_asset` |
| 상품/요청에 반려동물 키워드 포함 | `missing_pet_policy` |
| 웰니스/힐링/스파/명상 키워드 포함 | `missing_wellness_attributes` |
| 의료/검진/뷰티/병원 키워드 포함 | `missing_medical_context` |
| 걷기/트레킹/둘레길/GPX 키워드 포함 | `missing_route_asset` |
| 역사/문화/해설/외국인 키워드 포함 | `missing_story_asset` |
| 생태/친환경/공정관광/ESG 키워드 포함 | `missing_sustainability_context` |
| 지역 후보 ranking 근거가 필요함 | `missing_demand_signal` |
| 30일 이내 특정 날짜 운영 | `missing_crowding_signal` |
| itinerary가 1개 장소 중심으로 약함 | `missing_related_places` |
| 가격/예약/집결지/취소 정책 필요 | `missing_user_business_info` |

구현 방식:

- Phase 10.2부터 production 경로는 Gemini prompt + JSON schema 결과를 기준으로 한다.
- `LLM_ENABLED=true`에서는 `llm_calls.provider=gemini`, `purpose=data_gap_profile`로 기록한다.
- LLM이 꺼진 로컬 테스트 환경에서는 fake 결과를 꾸미지 않고 테스트 호환 계산만 수행한다.
- QA issue에서 들어온 공백은 후속 revision enrichment에서 severity를 한 단계 올리는 방향으로 확장한다.

### 3. ApiCapabilityRouterAgent

`data_gaps`를 API family planner lane으로 배분합니다. 실제 API operation과 arguments는 각 planner가 자기 source family subset만 보고 만듭니다.

입력:

```json
{
  "data_gaps": [],
  "normalized_request": {},
  "source_items": [],
  "budget_policy": {
    "max_external_calls": 20,
    "max_latency_ms": 15000,
    "allow_medical_api": false,
    "allow_visual_api": true
  }
}
```

출력:

```json
{
  "enrichment_plan": [
    {
      "id": "call_001",
      "tool_name": "kto_tour_detail_common",
      "source_family": "kto_tourapi_kor",
      "reason": "상품 후보의 상세 주소/홈페이지/개요 보강",
      "arguments": {
        "content_id": "12345",
        "content_type_id": "12"
      },
      "priority": 1,
      "depends_on": [],
      "cache_policy": "use_cache_if_fresh"
    }
  ],
  "skipped_gaps": [
    {
      "gap_id": "gap_009",
      "reason": "의료관광 API는 현재 run policy에서 비활성화되어 있습니다."
    }
  ]
}
```

라우팅 규칙:

| gap_type | tool 후보 |
|---|---|
| `missing_detail_common` | `kto_tour_detail_common` |
| `missing_detail_info` | `kto_tour_detail_intro`, `kto_tour_detail_info` |
| `missing_image_asset` | `kto_tour_detail_image`, `kto_tourism_photo_search`, `kto_photo_contest_search` |
| `missing_pet_policy` | `kto_pet_area_search`, `kto_pet_location_search`, `kto_pet_detail` |
| `missing_wellness_attributes` | `kto_wellness_keyword_search`, `kto_wellness_detail`, `kto_wellness_image` |
| `missing_medical_context` | `kto_medical_keyword_search`, `kto_medical_detail` |
| `missing_route_asset` | `kto_durunubi_course_list`, `kto_durunubi_path_list` |
| `missing_story_asset` | `kto_audio_keyword_search`, `kto_audio_location_search`, `kto_audio_detail` |
| `missing_sustainability_context` | `kto_eco_tourism_search`, `kto_eco_tourism_detail` |
| `missing_demand_signal` | `kto_tourism_bigdata_visitors` |
| `missing_crowding_signal` | `kto_attraction_crowding_forecast` |
| `missing_related_places` | `kto_related_places_area`, `kto_related_places_keyword` |
| `missing_user_business_info` | `official_web_search`, `official_page_extract`, `user_detail_request`, `internal_policy_lookup` |

예산/호출 제한:

- 기본 run에서 보강 API는 최대 10회로 시작한다.
- Poster Studio에서는 visual API 최대 8회, detail API 최대 5회로 시작한다.
- 의료관광 API는 별도 플래그가 켜진 경우만 호출한다.
- 동일 run 안에서 같은 source family와 같은 argument 호출은 dedupe한다.
- 캐시가 fresh하면 외부 호출을 생략하고 `cache_hit=true`로 기록한다.

### 4. EnrichmentExecutor

`enrichment_plan`을 실행해 실제 데이터를 가져옵니다.

담당:

- API 호출
- retry/backoff
- 응답 정규화
- DB upsert
- `source_documents` 생성
- tool call log 기록

출력:

```json
{
  "enrichment_run_id": "enrich_...",
  "results": [
    {
      "plan_id": "call_001",
      "status": "succeeded",
      "source_family": "kto_tourapi_kor",
      "normalized_records": 1,
      "source_document_ids": ["doc:tourapi:content:12345:detail"]
    }
  ],
  "failed_calls": [],
  "data_quality_flags": []
}
```

실패 처리:

| 실패 유형 | 처리 |
|---|---|
| API key 없음 | 해당 source family disabled, run은 계속 진행 |
| 4xx/5xx | tool call failed 기록, downstream에 unavailable flag 전달 |
| timeout | 1회 retry 후 실패 기록 |
| 응답 구조 변경 | parser error flag 저장 |
| license/usage 불명확 | asset은 candidate로 저장하고 게시 사용 불가 표시 |
| 의료 API 호출 차단 | skipped로 기록 |

### 5. EvidenceFusionAgent

기존 TourAPI, 테마 API, 사진 API, 수요/혼잡/연관 데이터를 하나의 근거 묶음으로 합칩니다.

입력:

```json
{
  "source_items": [],
  "retrieved_documents": [],
  "enrichment_results": [],
  "data_gaps": []
}
```

출력:

```json
{
  "evidence_profile": {
    "entities": [
      {
        "entity_id": "tourapi:content:12345",
        "title": "장소명",
        "coverage": {
          "common": "confirmed",
          "detail_info": "confirmed",
          "images": "candidate",
          "demand_signal": "available",
          "crowding_signal": "not_requested",
          "related_places": "available"
        },
        "trust_notes": [
          "방문자 수는 관광객 수와 동일하게 해석하지 않습니다.",
          "이미지 사용 전 출처 표시 조건을 확인해야 합니다."
        ]
      }
    ]
  },
  "retrieval_documents": [],
  "remaining_gaps": []
}
```

병합 규칙:

- 같은 `content_id`가 있으면 국문 관광정보 상세를 중심 entity로 사용한다.
- 이름/주소/좌표가 비슷한 테마 API 결과는 candidate match로 묶는다.
- 수요/혼잡/연관 정보는 설명 본문에 섞지 않고 signal로 보관한다.
- 서로 충돌하는 정보가 있으면 최신 `retrieved_at`과 source trust를 보고 `needs_review`로 표시한다.
- 이미지 asset은 게시 후보와 프롬프트 참고 후보를 분리한다.

### 6. ProductizationDataAdvisorAgent

보강된 근거를 실제 상품 결정으로 번역합니다.

출력:

```json
{
  "productization_advice": [
    {
      "product_id": "product_1",
      "recommended_changes": [
        {
          "type": "add_related_place",
          "title": "연관 음식점 후보 추가",
          "reason": "중심 관광지와 음식 유형 연관 데이터가 확인되었습니다.",
          "evidence_ids": ["related_..."]
        }
      ],
      "risk_notes": [
        {
          "type": "crowding",
          "severity": "medium",
          "message": "운영 후보 날짜의 집중률을 확인한 뒤 집결 시간을 조정하세요."
        }
      ],
      "poster_data_hints": [
        {
          "type": "visual_keyword",
          "value": "해안 야경",
          "source": "kto_tourism_photo"
        }
      ]
    }
  ]
}
```

활용:

- Product Agent가 itinerary를 보강한다.
- Marketing Agent가 카피와 FAQ를 조정한다.
- QA Agent가 리스크를 더 정확히 표시한다.
- Poster Studio가 사용자에게 이미지 생성 옵션을 추천한다.

### 7. OfficialWebEvidenceAgent

`missing_user_business_info`가 발견되었을 때 사용자에게 바로 묻기 전에 공식 웹 근거를 찾습니다. 이 Agent는 공공 API가 제공하지 않는 최신 운영 정보를 공식 홈페이지, 예약 페이지, 행사 공지, 운영사 정책 페이지에서 확인하는 역할입니다.

검색 우선순위:

1. 관광지/행사/운영사 공식 홈페이지
2. 공식 예약/판매 페이지
3. 지자체 또는 주최 측 공지
4. 플랫폼 정책 페이지
5. 뉴스/블로그/커뮤니티는 참고 자료로만 분류

입력:

```json
{
  "gap": {
    "gap_type": "missing_user_business_info",
    "fields": ["meeting_point", "cancellation_policy", "booking_time"]
  },
  "product_context": {
    "title": "부산 야경 + 전통시장 푸드투어",
    "region_name": "부산",
    "places": ["광안리", "전통시장 후보"]
  }
}
```

출력:

```json
{
  "web_evidence_documents": [
    {
      "id": "web_ev_...",
      "field": "meeting_point",
      "status": "candidate",
      "source_type": "official_booking_page",
      "url": "https://example.com/product/123",
      "retrieved_at": "2026-05-06T00:00:00+09:00",
      "summary": "집결지 후보가 확인되었지만 상품별 운영일에 따라 달라질 수 있습니다.",
      "confidence": 0.72,
      "needs_human_review": true
    }
  ],
  "remaining_user_request_fields": ["final_price", "partner_terms"]
}
```

사용 규칙:

- 검색 snippet만으로 확정하지 않고 URL, 조회 시각, source type을 저장한다.
- 공식 페이지가 아니면 `candidate` 또는 `reference_only`로 저장한다.
- 가격, 예약 가능 시간, 취소 정책은 공식 근거가 있어도 `needs_human_review`를 유지할 수 있다.
- API 근거와 웹 근거가 충돌하면 사용자 확인 대상으로 넘긴다.
- 내부 판매가, 파트너 정산 조건, 플랫폼 자체 정책은 웹 검색 결과보다 사용자/내부 DB를 우선한다.

### 8. HumanDataRequestAgent

공공 API와 공식 웹 근거로도 확인하기 어려운 운영 정보를 사용자에게 요청합니다. 이 Agent는 사용자를 첫 번째 정보원으로 쓰지 않습니다. 먼저 공식 웹 검색으로 확인 가능한 항목을 줄이고, 남은 공백만 질문으로 만듭니다.

전처리 흐름:

```text
missing_user_business_info
  -> 공식 웹 검색 후보 생성
  -> 공식 홈페이지/예약 페이지/행사 공지/운영사 정책 페이지 확인
  -> 확인 가능한 정보는 web evidence로 저장
  -> 불확실하거나 내부 정책에 해당하는 정보만 사용자 질문으로 전환
```

웹 검색으로 먼저 확인할 항목:

| 항목 | 우선 확인할 웹 근거 | 사용자에게 묻는 조건 |
|---|---|---|
| 운영 시간 | 공식 홈페이지, 공식 예약 페이지, 행사 공지 | 공식 근거가 없거나 날짜별 운영 시간이 불명확할 때 |
| 예약 가능 시간 | 공식 예약 페이지, 운영사 안내 페이지 | 재고/파트너 슬롯처럼 외부에 공개되지 않는 정보일 때 |
| 집결지 | 예약 상세 페이지, 운영사 안내, 행사 공식 공지 | 위치가 여러 개이거나 상품별 집결지가 다를 때 |
| 취소/환불 정책 | 플랫폼 정책 페이지, 운영사 정책 페이지 | 이 프로젝트에서 판매할 자체 정책과 충돌하거나 내부 확정이 필요할 때 |
| 포함/불포함 사항 | 예약 상세 페이지, 상품 상세 페이지 | 공급사별 조건이 다르거나 판매자가 직접 정해야 할 때 |
| 가격 | 공식 예약 페이지, 운영사 상품 페이지 | 변동 가능성이 있거나 최종 판매가/마진/프로모션가가 필요한 때 |

공식 웹 검색으로도 넘기지 않고 바로 사용자/내부 DB로 보내야 할 항목:

- 파트너 정산 조건
- 이 프로젝트에서 적용할 최종 판매가
- 플랫폼 자체 취소/환불 정책
- 내부 프로모션 여부
- 최소 출발 인원과 공급사 계약 조건
- 운영자가 직접 정해야 하는 포함/불포함 사항

웹 근거 저장 예:

```json
{
  "web_evidence_documents": [
    {
      "field": "meeting_point",
      "status": "candidate",
      "title": "운영사 공식 예약 안내",
      "url": "https://example.com/product/123",
      "source_type": "official_booking_page",
      "retrieved_at": "2026-05-06T00:00:00+09:00",
      "summary": "집결지 후보가 확인되었지만 상품별 운영일에 따라 달라질 수 있습니다.",
      "confidence": 0.72,
      "needs_human_review": true
    }
  ]
}
```

요청 대상:

- 공식 웹 근거로 확정되지 않은 실제 판매 가격
- 공식 웹 근거와 다른 내부 포함/불포함 사항
- 공개 예약 페이지에서 확인되지 않는 예약 가능 시간
- 공급사/파트너 조건
- 상품별로 확정해야 하는 정확한 집결지
- 플랫폼 또는 운영자가 직접 적용할 취소/환불 정책
- 최소/최대 인원
- 언어 가이드 가능 여부
- 의료/안전 관련 운영 기준

출력:

```json
{
  "user_detail_requests": [
    {
      "field": "meeting_point",
      "label": "집결지",
      "reason": "공공 API와 공식 웹 근거에서 이 상품에 적용할 정확한 집결지를 확정할 수 없습니다.",
      "required_for": ["publish", "qa_pass"],
      "suggested_format": "주소 또는 장소명",
      "web_search_attempted": true,
      "web_evidence_ids": ["web_ev_..."]
    }
  ]
}
```

UI에서는 Run Detail에 "운영자 입력 필요" 패널을 추가하는 방식이 적합합니다. 이 패널에는 바로 질문만 보여주지 말고, 먼저 시도한 공식 웹 검색 결과와 왜 확정하지 못했는지를 함께 보여줍니다.

## Tool catalog

### 기존 provider 확장

```text
kto_tour_area_code
kto_tour_area_based_list
kto_tour_location_based_list
kto_tour_search_keyword
kto_tour_search_festival
kto_tour_search_stay
kto_tour_detail_common
kto_tour_detail_intro
kto_tour_detail_info
kto_tour_detail_image
```

### 사진/포스터 보강

```text
kto_tourism_photo_search
kto_tourism_photo_sync
kto_photo_contest_search
kto_photo_contest_sync
```

### 테마 보강

```text
kto_wellness_area_search
kto_wellness_location_search
kto_wellness_keyword_search
kto_wellness_detail_common
kto_wellness_detail_intro
kto_wellness_detail_info
kto_wellness_detail_image

kto_medical_area_search
kto_medical_location_search
kto_medical_keyword_search
kto_medical_detail_common
kto_medical_detail_intro
kto_medical_detail_info

kto_pet_area_search
kto_pet_keyword_search
kto_pet_location_search
kto_pet_detail_pet

kto_durunubi_course_list
kto_durunubi_path_list

kto_audio_story_search
kto_audio_theme_search

kto_eco_area_search
```

### 수요/혼잡/연관 보강

```text
kto_tourism_bigdata_visitors
kto_attraction_crowding_forecast
kto_related_places_area
kto_related_places_keyword
```

### 공식 웹 근거/사용자 입력 보강

```text
official_web_search
official_page_extract
official_booking_page_extract
official_notice_search
internal_policy_lookup
user_detail_request
```

사용 순서:

```text
official_web_search
  -> official_page_extract
  -> internal_policy_lookup, if internal business policy may override public information
  -> user_detail_request, only for fields still unresolved
```

## DB 설계 후보

현재 `tourism_items`, `source_documents`, `tool_calls`를 유지하면서 보강용 테이블을 추가합니다.

### enrichment_runs

```text
id
workflow_run_id
trigger_type              -- initial_run, qa_revision, poster_studio, manual
status                    -- planned, running, succeeded, partially_succeeded, failed
gap_report_json
plan_json
result_summary_json
created_at
started_at
finished_at
```

### enrichment_tool_calls

기존 `tool_calls`를 그대로 써도 되지만, 보강 plan과 연결하려면 별도 테이블 또는 metadata 확장이 필요합니다.

```text
id
enrichment_run_id
workflow_run_id
plan_id
tool_name
source_family
arguments_json
status
response_summary_json
error_json
cache_hit
latency_ms
created_at
```

### tourism_entities

여러 API 결과를 하나의 장소/코스/자원으로 묶는 canonical entity입니다.

```text
id
canonical_name
entity_type              -- attraction, event, stay, food, route, photo_spot, medical, wellness
region_code
sigungu_code
address
map_x
map_y
primary_source_item_id
match_confidence
created_at
updated_at
```

### tourism_visual_assets

```text
id
entity_id
source_family
source_item_id
title
image_url
thumbnail_url
shooting_place
shooting_date
photographer
keywords_json
license_type
license_note
usage_status             -- candidate, approved_for_reference, approved_for_publish, blocked
retrieved_at
```

### tourism_route_assets

```text
id
entity_id
source_family
course_name
path_name
gpx_url
distance_km
estimated_duration
start_point
end_point
nearby_places_json
safety_notes_json
retrieved_at
```

### tourism_signal_records

수요, 집중률, 연관성처럼 본문 정보와 성격이 다른 데이터를 저장합니다.

```text
id
entity_id
region_code
sigungu_code
source_family
signal_type              -- visitor_count, crowding_forecast, related_place
period_start
period_end
value_json
interpretation_note
retrieved_at
```

### web_evidence_documents

공공 API 밖의 최신 운영 정보를 공식 웹 근거로 저장합니다. 사용자에게 질문하기 전 확인한 검색/페이지 추출 결과를 남기는 용도입니다.

```text
id
workflow_run_id
entity_id
field_name               -- meeting_point, booking_time, cancellation_policy, price, inclusions
status                   -- confirmed, candidate, reference_only, conflicted, rejected
source_type              -- official_site, official_booking_page, official_notice, platform_policy, other
title
url
summary
retrieved_at
published_at
confidence
needs_human_review
raw_json
created_at
```

저장 원칙:

- `confirmed`는 공식 출처와 상품 맥락이 명확할 때만 사용한다.
- 가격, 예약 가능 시간, 취소 정책은 기본적으로 `candidate` 또는 `needs_human_review=true`로 둔다.
- 비공식 페이지는 `reference_only`로 저장하고 QA 확정 근거로 쓰지 않는다.

### source_documents 확장

현재 table을 유지하고 metadata를 풍부하게 만듭니다.

추가 metadata 후보:

```json
{
  "source_family": "kto_wellness",
  "trust_level": 0.9,
  "retrieved_at": "2026-05-06T00:00:00+09:00",
  "valid_from": null,
  "valid_to": null,
  "license_note": "공식 응답 기준",
  "data_quality_flags": [],
  "interpretation_notes": []
}
```

## Backend API 설계 후보

### 데이터 capability 조회

```http
GET /api/data/sources/capabilities
```

응답:

```json
{
  "sources": [
    {
      "source_family": "kto_pet",
      "enabled": true,
      "requires_service_key": true,
      "supported_gaps": ["missing_pet_policy"],
      "default_ttl_hours": 24
    }
  ]
}
```

### run 데이터 공백 분석

```http
POST /api/workflow-runs/{run_id}/data-gaps/analyze
```

응답:

```json
{
  "data_gaps": [],
  "coverage_summary": {
    "detail": "partial",
    "visual": "weak",
    "demand": "not_requested",
    "operation_policy": "needs_user_input"
  }
}
```

### 보강 plan 생성

```http
POST /api/workflow-runs/{run_id}/enrichment-plan
```

요청:

```json
{
  "max_external_calls": 10,
  "enabled_source_families": [
    "kto_tourapi_kor",
    "kto_tourism_photo",
    "kto_related_places",
    "kto_crowding_forecast"
  ]
}
```

응답:

```json
{
  "enrichment_plan": [],
  "estimated_calls": 7,
  "skipped_gaps": []
}
```

### 보강 실행

```http
POST /api/workflow-runs/{run_id}/enrich
```

응답:

```json
{
  "enrichment_run_id": "enrich_...",
  "status": "succeeded",
  "source_documents_added": 12,
  "visual_assets_added": 5,
  "signals_added": 3
}
```

### 보강 이력 조회

```http
GET /api/workflow-runs/{run_id}/enrichment-runs
```

응답:

```json
{
  "items": [
    {
      "id": "enrich_...",
      "trigger_type": "poster_studio",
      "status": "succeeded",
      "created_at": "..."
    }
  ]
}
```

## Frontend UI 계획

Run Detail 화면 용어는 현재 개발 확인용 표현을 유지합니다. 데이터 보강 기능은 나중에 다음 패널로 붙입니다.

### Data Coverage 패널

표시:

- 기본 정보: 충분/부분/부족
- 운영 정보: 충분/부분/부족
- 이미지 자료: 충분/부분/부족
- 수요 신호: 있음/없음/요청 안 함
- 혼잡 신호: 있음/없음/요청 안 함
- 연관 관광지: 있음/없음/요청 안 함
- 사용자 입력 필요: 필드 목록

### Recommended Data Calls 패널

표시:

- 추천 API 호출 목록
- 호출 이유
- 예상 호출 수
- 이미 캐시된 항목
- 실행/스킵 토글

### Evidence Profile 패널

표시:

- 상품별 근거 coverage
- 사진 후보
- 연관 관광지 후보
- 혼잡/수요 signal
- 해석 주의사항

### Poster Studio 연계

Poster Studio에서 사용할 데이터:

- Run Review의 상품명, 타깃, 핵심 가치, itinerary, FAQ, QA issue
- 관광사진/공모전 사진의 촬영지, 키워드, 이미지 URL
- 집중률/혼잡 signal에 따른 포스터 메시지 톤
- 오디오 가이드/생태/웰니스 데이터에서 추출한 분위기와 스토리 키워드

사용자 옵션 추천:

```json
{
  "poster_options": {
    "layout": ["세로형 여행 포스터", "SNS 정사각형", "상세페이지 히어로"],
    "visual_theme": ["해안 야경", "로컬 시장", "걷기 코스", "웰니스 휴식"],
    "included_text": [
      "상품명",
      "한 줄 소개",
      "핵심 코스 3개",
      "운영자 확인 필요 문구"
    ],
    "exclude_text": [
      "가격",
      "예약 확정 표현",
      "효과 보장 표현"
    ],
    "reference_sources": [
      "kto_tourism_photo",
      "kto_photo_contest",
      "run_review"
    ]
  }
}
```

## Agent prompt skeleton

### DataGapProfilerAgent prompt

```text
너는 여행 상품 운영 데이터 검토 Agent다.
입력된 run 요청, 지역 범위, shortlist 관광 후보, 검색 근거, 자연어 API capability brief를 보고 실제 상품화에 필요한 데이터 공백을 구조화한다.

규칙:
- shortlist 밖 raw 후보에 대해서는 개별 gap을 만들지 않는다.
- 이미 근거가 있는 항목과 확인이 필요한 항목을 분리한다.
- 가격, 예약 가능 여부, 집결지, 취소 정책은 외부 API만으로 확정하지 않는다.
- 방문자 수, 집중률, 연관 관광지 데이터는 운영 판단 보조 신호로만 분류한다.
- poster_studio에 필요한 이미지/시각 키워드 공백도 별도 표시한다.
- 요청 상품 유형과 무관한 gap을 만들지 않는다.
- `missing_overview`는 만들지 않고 `missing_detail_info`로 통합한다.
- 같은 후보에 반복 gap을 여러 개 만들지 않고 우선순위 gap만 남긴다.
- 전체 gaps는 24개 이하로 제한한다.
- 확실하지 않은 정보는 추측하지 말고 needs_review에 남긴다.
- 출력은 JSON schema를 지킨다.
```

### ApiCapabilityRouterAgent prompt

```text
너는 데이터 공백을 API family planner lane으로 배분하는 Agent다.
입력된 data_gaps와 source capability catalog 요약을 보고 어떤 planner가 어떤 gap을 맡을지만 정한다.

규칙:
- API endpoint와 arguments를 직접 만들지 않는다.
- 각 gap은 tourapi_detail, visual_data, route_signal, theme_data 중 하나의 lane에만 배정한다.
- 의료관광 API는 allow_medical_api가 false이면 낮은 우선순위 또는 보류 사유를 남긴다.
- 출력은 family_routes 중심 JSON schema를 지킨다.
```

### API Family Planner prompt

```text
너는 특정 KTO API family lane만 담당하는 계획 Agent다.
Router가 배정한 gap과 해당 lane의 짧은 capability 요약만 보고 세부 call 또는 skipped/future 기록을 만든다.

규칙:
- assigned_gaps에 없는 gap_id를 만들지 않는다.
- TourApiDetailPlannerAgent는 Phase 10.2부터 실제 planned_calls를 만들 수 있다.
- detail planner의 실행 call은 detailCommon2/detailIntro2/detailInfo2/detailImage2 묶음으로 만든다.
- shortlist 안에서 contentId가 있는 실행 가능 대상은 임의 6개 budget으로 자르지 않는다.
- VisualDataPlannerAgent는 Phase 12.1부터, RouteSignalPlannerAgent는 Phase 12.2부터, ThemeDataPlannerAgent는 Phase 12.3부터 feature flag와 서비스키가 있으면 실제 planned_calls를 만들 수 있다.
- 의료관광은 allow_medical_api가 false이면 feature_flag_disabled로 남긴다.
- reason과 planning_reasoning은 짧게 쓴다.
```

### OfficialWebEvidenceAgent prompt

```text
너는 사용자에게 묻기 전에 공식 웹 근거를 먼저 확인하는 Agent다.
입력된 missing_user_business_info 항목을 공식 홈페이지, 예약 페이지, 행사 공지, 운영사 정책 페이지에서 확인한다.

규칙:
- 공식 출처를 우선하고, 비공식 출처는 reference_only로 분류한다.
- URL, 조회 시각, source type, 요약, confidence를 반드시 남긴다.
- 가격, 예약 가능 시간, 취소 정책은 공식 근거가 있어도 needs_human_review를 유지할 수 있다.
- 내부 판매가, 파트너 정산, 플랫폼 자체 정책은 사용자/내부 DB 확인 대상으로 남긴다.
- 확정하지 못한 항목만 remaining_user_request_fields로 반환한다.
```

### EvidenceFusionAgent prompt

```text
너는 여러 공공 관광 데이터 응답을 하나의 상품화 근거 묶음으로 정리하는 Agent다.

규칙:
- 같은 장소로 보이는 데이터는 candidate match로 묶고 confidence를 표시한다.
- 데이터 해석 주의사항을 삭제하지 않는다.
- 수요/혼잡/연관성 signal을 관광지 설명 본문처럼 쓰지 않는다.
- 충돌하거나 오래된 정보는 needs_review로 표시한다.
- Product/Marketing/QA가 써도 되는 claim과 쓰면 안 되는 claim을 분리한다.
- UI에 보여줄 요약은 ui_highlights에 한국어로 작성한다.
- downstream Agent가 쓸 수 있도록 evidence_ids를 안정적으로 남긴다.
```

## 구현 단계

### Step 1. Capability catalog 추가

파일 후보:

- `backend/app/tools/kto_capabilities.py`
- `backend/app/schemas/enrichment.py`

내용:

- source family 목록
- 지원 gap type
- tool name
- TTL
- risk level
- enabled flag

완료 기준:

- `/api/data/sources/capabilities`에서 현재 켜진 source 목록을 볼 수 있다.
- API key가 없는 source는 disabled로 표시된다.

### Step 2. 기존 TourAPI 상세 method 추가

파일 후보:

- `backend/app/tools/tourism.py`
- `backend/app/tests/test_tourism_api.py`

내용:

- `detail_common`
- `detail_intro`
- `detail_info`
- `detail_image`

완료 기준:

- content_id 기반 상세 조회 테스트 통과
- source document에 상세/반복/이미지 정보가 포함됨

### Step 3. DataGapProfilerAgent Gemini 구현

파일 후보:

- `backend/app/agents/data_enrichment.py`
- `backend/app/agents/workflow.py`
- `backend/app/tests/test_data_gap_agent.py`

완료 기준:

- `LLM_ENABLED=true`에서 `llm_calls.provider=gemini`, `purpose=data_gap_profile`로 기록
- 이미지 없는 item에서 `missing_image_asset` 생성
- 반려동물 요청에서 `missing_pet_policy` 생성
- 도보 요청에서 `missing_route_asset` 생성
- 가격/집결지 누락은 `missing_user_business_info`로 분리하고, 바로 사용자 질문으로 만들지 않는다.

### Step 4. ApiCapabilityRouterAgent Gemini 구현

파일 후보:

- `backend/app/agents/data_enrichment.py`
- `backend/app/agents/workflow.py`
- `backend/app/tests/test_enrichment_router.py`

완료 기준:

- `LLM_ENABLED=true`에서 `llm_calls.provider=gemini`, `purpose=api_capability_routing`으로 기록
- gap type을 API family planner lane으로 변환
- max call budget 적용
- disabled source family skip
- 의료관광 API 보호 플래그 적용
- `missing_user_business_info`는 `official_web_search`와 `official_page_extract`를 `user_detail_request`보다 먼저 계획

### Step 4-1. API Family Planner Gemini 구현

파일 후보:

- `backend/app/agents/data_enrichment.py`
- `backend/app/agents/workflow.py`
- `backend/app/tests/test_data_enrichment.py`

완료 기준:

- `TourApiDetailPlannerAgent`는 `purpose=tourapi_detail_planning`으로 Gemini 호출을 기록
- `VisualDataPlannerAgent`는 `purpose=visual_data_planning`으로 Gemini 호출을 기록
- `RouteSignalPlannerAgent`는 `purpose=route_signal_planning`으로 Gemini 호출을 기록
- `ThemeDataPlannerAgent`는 `purpose=theme_data_planning`으로 Gemini 호출을 기록
- 각 planner prompt에는 자기 source family subset만 들어간다.
- 네 planner의 fragment를 합쳐 `enrichment_plan`을 만든다.

### Step 5. OfficialWebEvidenceAgent 구현

파일 후보:

- `backend/app/agents/web_evidence.py`
- `backend/app/tools/web_evidence.py`
- `backend/app/tests/test_web_evidence_agent.py`

내용:

- 공식 홈페이지/예약 페이지/행사 공지 우선 검색
- 페이지 요약과 URL, 조회 시각 저장
- 가격/예약/집결지/취소 정책의 확정 가능 여부 판단
- 비공식 출처는 참고 자료로만 분류
- 남은 항목을 `remaining_user_request_fields`로 정리

완료 기준:

- 집결지 후보가 공식 예약 페이지에서 확인되면 `web_evidence_documents`에 candidate로 저장
- 공식 근거가 없으면 `user_detail_request` 후보로 넘어감
- 가격과 취소 정책은 공식 페이지가 있어도 `needs_human_review`를 유지할 수 있음
- 웹 근거와 API 근거가 충돌하면 `conflicted` 상태로 저장

### Step 6. Enrichment executor와 DB 저장

파일 후보:

- `backend/app/tools/kto_enrichment.py`
- `backend/app/api/routes_enrichment.py`
- `backend/app/db/models.py`

완료 기준:

- enrichment run 생성/조회
- tool call plan 실행
- 결과 upsert
- source document indexing

### Step 7. Workflow 연결

파일 후보:

- `backend/app/agents/workflow.py`
- `backend/app/schemas/workflow.py`

완료 기준:

- 기본 workflow에서 선택적으로 보강 실행
- QA revision에서 필요한 보강만 재실행
- final output에 `data_gaps`, `evidence_profile`, `productization_advice` 포함
- `missing_user_business_info`가 남아 있을 때 `OfficialWebEvidenceAgent`를 먼저 실행하고, 이후에도 남은 항목만 `HumanDataRequestAgent`로 전달

### Step 8. Run Detail UI 추가

파일 후보:

- `frontend/src/pages/RunDetail.tsx`
- `frontend/src/pages/RunDetail.module.css`
- `frontend/src/services/runsApi.ts`

완료 기준:

- 데이터 coverage 확인
- 추천 API 호출 실행
- 보강 결과 evidence 확인
- 공식 웹 검색으로 확인한 후보와 운영자 입력 필요 필드 확인

### Step 9. Poster Studio와 연결

파일 후보:

- `backend/app/agents/poster.py`
- `backend/app/tools/openai_images.py`
- `frontend/src/pages/PosterStudio.tsx`

완료 기준:

- Run Review 기반 포스터 옵션 추천
- 관광사진/공모전 사진 기반 visual hint 생성
- 사용자가 옵션을 수정해 포스터 생성 프롬프트 확정
- 이미지 생성 모델은 구현 시점의 OpenAI 공식 문서에서 최신 모델명을 확인
- 생성 이미지와 prompt/evidence를 asset으로 저장

## 품질 지표

| 지표 | 의미 | 목표 |
|---|---|---|
| `gap_resolution_rate` | 생성된 data gap 중 API/사용자 입력으로 해결된 비율 | 60% 이상 |
| `useful_call_rate` | downstream 결과에 실제 반영된 API 호출 비율 | 70% 이상 |
| `unsupported_claim_reduction` | QA에서 출처 없음/확인 필요 claim이 줄어든 비율 | 개선 추적 |
| `visual_asset_coverage` | 포스터 후보 상품 중 이미지/시각 키워드가 확보된 비율 | 80% 이상 |
| `latency_added_ms` | 보강 workflow 추가 지연 시간 | 기본 run 15초 이내 |
| `cache_hit_rate` | 보강 API 캐시 적중률 | 40% 이상 |
| `human_acceptance_rate` | 운영자가 보강 추천을 유지한 비율 | 60% 이상 |

## 해석/검수 guardrails

- 방문자 수는 관광객 수, 예약 수, 매출로 해석하지 않는다.
- 집중률 예측은 실제 혼잡 확정값으로 표현하지 않는다.
- Tmap 연관 관광지는 차량 이동 기반 연결성으로 설명한다.
- 반려동물 동반 조건은 장소별 제한과 함께 표시한다.
- 의료관광 데이터는 의료 효과, 치료 결과, 안전성 보장 표현에 쓰지 않는다.
- 이미지 asset은 라이선스와 출처 표시 조건을 확인하기 전 게시 확정 상태로 두지 않는다.
- GPX/트레킹 코스는 날씨, 야간, 체력, 교통 접근성 리스크를 QA에서 확인한다.

## 관련 문서

- [05_DATA_SOURCES_AND_INGESTION.md](./05_DATA_SOURCES_AND_INGESTION.md)
- [05_01_KTO_OPENAPI_DATA_ENRICHMENT_PLAN.md](./05_01_KTO_OPENAPI_DATA_ENRICHMENT_PLAN.md)
- [06_AGENT_WORKFLOW_SPEC.md](./06_AGENT_WORKFLOW_SPEC.md)
- [07_BACKEND_API_AND_DB_SPEC.md](./07_BACKEND_API_AND_DB_SPEC.md)
- [08_FRONTEND_UI_SPEC.md](./08_FRONTEND_UI_SPEC.md)
