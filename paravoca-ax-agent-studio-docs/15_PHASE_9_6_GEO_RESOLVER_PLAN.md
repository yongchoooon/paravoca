# Phase 9.6: GeoResolverAgent와 TourAPI v4.4 지역/분류 전환 계획 및 구현 결과

작성 기준일: 2026-05-07

## 배경

Phase 9까지 PARAVOCA는 TourAPI 검색, 상세 보강, source document, Chroma evidence 표시까지 구현했습니다. Phase 9.5에서는 embedding provider를 분리해 Chroma를 유지하면서 local semantic embedding으로 교체할 수 있게 했습니다.

하지만 `run_e84714a8a7af42a2`에서 문제가 드러났습니다. 사용자는 "이번 달 대전에서 외국인 대상 액티비티 상품을 3개 기획해줘"라고 요청했지만, Evidence에는 강릉, 정선, 부산, 고창 등 다른 지역 데이터가 섞였습니다.

직접 원인을 확인한 결과:

- TourAPI 지역 코드 조회는 대전을 찾았습니다.
- workflow가 응답의 `code`를 `region_code`로 읽지 못해 `None`으로 버렸습니다.
- 이후 `searchFestival2`, `searchStay2`, Chroma search가 지역 필터 없이 실행되었습니다.
- v4.4 공식 문서 기준으로는 `areaCode`보다 `lDongRegnCd`/`lDongSignguCd` 법정동 코드가 목록/검색 필터의 중심입니다.

따라서 Phase 9.6은 단순히 대전 코드만 고치는 작업이 아니라, 자연어 prompt에서 지역 의도를 추출하고 TourAPI v4.4의 법정동/분류체계로 안전하게 변환하는 계층을 도입하는 작업입니다.

## 현재 구현 결과 요약

Phase 9.6 구현 결과는 다음과 같습니다.

- `GeoResolverAgent`가 Planner 다음에 실행됩니다.
- `LLM_ENABLED=true`이면 GeoResolver가 Gemini를 호출해 장소 span, 복수 지역 여부, 해외 목적지 여부를 추출하고, Phase 12.0부터는 TourAPI `ldong` catalog 후보 중 실제 검색에 사용할 `resolved_locations`도 선택합니다.
- 최종 코드는 Gemini 선택 결과를 그대로 믿지 않고, Python resolver가 공식 `ldong` catalog에 실제 존재하는 code인지와 confidence를 검증합니다.
- Run 생성 UI는 별도 Region 입력을 받지 않고 자연어 request를 source of truth로 사용합니다.
- TourAPI v4.4 `ldongCode2?lDongListYn=Y` 전체 paging sync와 `lclsSystmCode2` sync를 `python -m app.tools.sync_tourapi_catalogs`로 제공합니다.
- resolver는 DB에 동기화된 공식 TourAPI 시도/시군구 catalog를 우선 사용합니다.
- 특정 예시 지명을 코드에 하드코딩하거나 실패 시 seed/fallback으로 추정하지 않습니다.
- `부산 부산진구 전포동 일대`, `대청도`처럼 상위 시군구가 확정된 세부 동네명/섬/생활권명은 상위 시군구 코드와 원문 keyword를 함께 보존하고, 수집 후 keyword가 포함된 item/document만 남깁니다.
- `중구`처럼 후보가 여러 개인 요청은 run status를 `failed`로 저장하되 후보 안내를 UI에 표시합니다.
- 지역 이동형 코스나 두 곳 이상의 지역을 한 번에 연결하는 요청은 현재 지원하지 않습니다. 감지된 후보 중 하나만 선택해 다시 요청하라는 안내로 종료합니다.
- 해외 목적지는 `unsupported` 상태로 멈추고 "PARAVOCA는 현재 국내 관광 데이터만 지원합니다."라는 안내를 표시합니다.
- DataAgent와 RAG metadata/filter는 `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3`를 저장하고 사용합니다.
- Run Detail Evidence table은 사용자에게 내부 `Geo`/`LCLS` 코드 컬럼을 노출하지 않고, content type은 한국어로 표시합니다.

## 목표

Phase 9.6의 목표는 다음입니다.

1. 사용자가 웹에서 `Region`을 따로 입력하지 않아도 자연어 prompt에서 지역 의도를 추출한다.
2. 단일 지역과 복수 지역 요청을 구분한다. 복수 지역 또는 지역 이동형 요청은 지원하지 않고 단일 지역 선택 안내로 종료한다.
3. TourAPI v4.4 기준 `ldongCode2`와 `lclsSystmCode2`를 catalog로 저장한다.
4. `areaCode` 중심 조회를 `lDongRegnCd`, `lDongSignguCd`, `lclsSystm1/2/3` 중심으로 전환한다.
5. 지역 코드를 못 찾았을 때 전국 검색으로 조용히 fallback하지 않는다.
6. Evidence가 사용자가 요청한 지역 scope 밖의 데이터를 포함하지 않도록 DataAgent와 RAG filter를 강화한다.
7. 기존 mock/dummy provider 테스트를 실제 v4.4 구조에 맞는 fake provider로 교체한다.

## 비목표

Phase 9.6에서 하지 않을 것:

- Product/Marketing이 evidence 내용을 완전히 반영해 생성하는 작업. 이는 Phase 11의 Agent 실제화 범위입니다.
- 예약, 가격, 재고, 판매 가능 여부 확정.
- 모든 별칭을 수작업으로 완성하는 것.
- 특정 테스트 예시를 하드코딩하거나, 실패 시 seed/fallback으로 조용히 추정하는 것.
- 외부 지도/지오코딩 API 의존. 현재 구현은 TourAPI `ldongCode2` catalog와 deterministic resolver를 기준으로 합니다.

## 핵심 설계: GeoResolverAgent

GeoResolverAgent는 자연어 prompt에서 지리 의도를 추출하고 TourAPI 조회 가능한 코드로 변환하는 Agent입니다.

중요한 설계 원칙:

- LLM 단독 판단에 맡기지 않습니다.
- LLM은 자연어 span과 관계를 뽑는 데 쓰고, 최종 코드는 catalog resolver가 검증합니다.
- catalog에 없거나 애매한 경우에는 `needs_clarification=true`로 표시합니다.
- 지역이 명시된 요청에서 지역 resolve 실패 시 전국 검색을 금지합니다.

## Agent 위치

기존 workflow:

```text
PlannerAgent
-> DataAgent
-> ResearchAgent
-> ProductAgent
-> MarketingAgent
-> QAComplianceAgent
-> HumanApprovalNode
```

Phase 9.6 이후:

```text
PlannerAgent
-> GeoResolverAgent
-> DataAgent
-> ResearchAgent
-> ProductAgent
-> MarketingAgent
-> QAComplianceAgent
-> HumanApprovalNode
```

PlannerAgent는 더 이상 부산 하드코딩 또는 단순 `region` 필드 중심으로 동작하지 않습니다. PlannerAgent는 prompt, period, target, product_count, preferences를 정리하고, GeoResolverAgent가 `geo_scope`를 만들어 DataAgent에 넘깁니다.

## GeoScope 출력 스키마

현재 권장 JSON:

```json
{
  "geo_scope": {
    "mode": "single_region",
    "source": "prompt",
    "original_text": "부산 부산진구 전포동 일대 외국인 대상 액티비티 상품 3개",
    "locations": [
      {
        "text": "부산 부산진구",
        "normalized_name": "부산광역시 부산진구",
        "role": "primary",
        "match_type": "ldong_signgu",
        "ldong_regn_cd": "26",
        "ldong_regn_nm": "부산광역시",
        "ldong_signgu_cd": "230",
        "ldong_signgu_nm": "부산진구",
        "legacy_area_code": "6",
        "legacy_sigungu_code": null,
        "keyword": "전포동",
        "confidence": 0.99,
        "evidence": "ldongCode2 signgu exact match"
      }
    ],
    "unresolved_locations": [],
    "excluded_locations": [],
    "keywords": ["전포동"],
    "needs_clarification": false,
    "clarification_question": null
  }
}
```

복수 지역 또는 지역 이동형 요청은 아래처럼 정상 검색으로 넘기지 않습니다.

```json
{
  "geo_scope": {
    "mode": "unsupported_multi_region",
    "status": "needs_clarification",
    "needs_clarification": true,
    "clarification_question": "현재 PARAVOCA는 한 번에 하나의 지역만 지원합니다. 아래 후보 중 하나만 포함해 다시 요청해 주세요.",
    "candidates": [
      {"name": "부산광역시", "ldong_regn_cd": "26", "ldong_signgu_cd": null},
      {"name": "경상남도 양산시", "ldong_regn_cd": "48", "ldong_signgu_cd": "330"}
    ]
  }
}
```

### `mode` 값

| mode | 의미 | 예시 |
|---|---|---|
| `single_region` | 단일 지역 | "대전에서 액티비티 3개" |
| `unsupported_multi_region` | 현재 미지원인 복수 지역/지역 이동형 요청 | "부산과 양산을 연결해서" |
| `nearby` | 특정 장소 주변 | "대전역 근처에서" |
| `nationwide` | 전국 또는 지역 미지정 | "전국 축제 중에서" |
| `clarification_required` | 해석 불가 또는 충돌 | "중구 야간 관광"처럼 후보가 여러 개인 경우 |

### `role` 값

| role | 의미 |
|---|---|
| `primary` | 단일 또는 주요 지역 |
| `nearby_anchor` | 주변 검색 기준점 |
| `comparison` | 비교 대상 |
| `excluded` | 제외 지역 |

### `match_type` 값

| match_type | 의미 |
|---|---|
| `ldong_region` | TourAPI catalog 시도 match |
| `ldong_signgu` | TourAPI catalog 시군구 match |
| `keyword_only` | 행정코드는 찾았지만 검색에는 keyword 유지가 필요한 지명 |
| `unresolved` | 코드 확정 실패 |

## 지역 해석 계층

GeoResolverAgent는 다음 순서로 resolve합니다.

1. Gemini catalog selection
   - 장소명, 복수 지역 여부, 제외 표현을 추출합니다.
   - TourAPI `ldong` catalog 후보 중 실제 검색에 사용할 `resolved_locations`를 선택합니다.
   - 선택한 code가 catalog에 없거나 confidence가 낮으면 확정하지 않습니다.
   - 두 곳 이상 지역이 감지되면 Python resolver가 `unsupported_multi_region`으로 종료합니다.

2. Exact catalog matching fallback
   - `ldongCode2`로 sync한 시도/시군구 이름에 exact match합니다.
   - 예: 대전 -> 대전광역시 `30`.

3. Normalized matching fallback
   - "광역시", "특별자치도", "시", "군", "구" suffix를 정규화합니다.
   - 예: "대전" -> "대전광역시", "영양" -> "영양군".

4. Parent-scoped keyword extraction
   - TourAPI catalog가 시도/시군구까지만 제공하는 경우, 상위 지역이 확정된 세부 동네명/섬/생활권명은 검색 keyword로 유지합니다.
   - BaselineDataAgent는 상위 code로 수집한 뒤 keyword가 들어간 근거만 유지합니다.
   - 예: "부산 부산진구 전포동 일대" -> 부산광역시 부산진구 `26`/`230` + keyword `전포동`.
   - 상위 지역 없이 catalog에 없는 장소명만 있는 경우에는 억지로 특정 시군구에 매핑하지 않습니다.

5. Fuzzy matching
   - 명백한 오타나 일부 입력은 catalog 후보와 confidence를 남깁니다.
   - threshold 이하이거나 후보가 여러 개면 clarification으로 보냅니다.

6. Ambiguity scoring
   - 여러 후보가 있으면 confidence와 prompt context로 점수화합니다.
   - 예: "중구"는 여러 시도에 존재하므로 상위 시도가 없으면 ambiguous.

7. Clarification gate
   - confidence가 낮거나 후보가 여러 개면 workflow를 `failed`로 종료하고 사용자에게 지역 후보 안내 UI를 보여줍니다.

## TourAPI v4.4 코드 catalog

Phase 9.6에서 추가할 catalog는 두 종류입니다.

### 1. 법정동 catalog

source operation:

```text
ldongCode2
```

저장 후보 테이블:

```text
tourapi_ldong_codes
```

필드:

| 필드 | 설명 |
|---|---|
| `id` | 내부 ID |
| `ldong_regn_cd` | 법정동 시도 코드 |
| `ldong_regn_nm` | 법정동 시도명 |
| `ldong_signgu_cd` | 법정동 시군구 코드, 시도 row면 null 가능 |
| `ldong_signgu_nm` | 법정동 시군구명 |
| `full_name` | 예: 경상북도 울릉군 |
| `normalized_name` | suffix/공백 정규화 이름 |
| `aliases` | JSON list |
| `source` | `tourapi_ldong_code` |
| `synced_at` | sync 시각 |
| `raw` | 원본 응답 |

운영 방침:

- `tourapi_ldong_codes`는 공식 TourAPI catalog sync 결과만 저장합니다.
- `영종도`, `가덕도` 같은 섬/생활권/관광권 표현을 임의로 특정 시군구에 하드코딩하지 않습니다.
- 사용자가 "부산 강서구 가덕도"처럼 상위 시군구를 함께 주면 `부산광역시 강서구` 코드와 `가덕도` keyword로 검색합니다.
- 상위 지역 없이 catalog에 없는 지명만 주어진 경우에는 후보 확인 또는 후속 지오코딩/alias 관리 기능의 대상으로 남깁니다.
- 향후 alias table을 추가하더라도 운영자가 승인한 source, 적용 범위, confidence, 만료/갱신 정책을 함께 저장해야 합니다.

### 2. 신분류체계 catalog

source operation:

```text
lclsSystmCode2
```

저장 후보 테이블:

```text
tourapi_lcls_codes
```

필드:

| 필드 | 설명 |
|---|---|
| `id` | 내부 ID |
| `lcls_systm_1` | 대분류 코드 |
| `lcls_systm_1_name` | 대분류명 |
| `lcls_systm_2` | 중분류 코드 |
| `lcls_systm_2_name` | 중분류명 |
| `lcls_systm_3` | 소분류 코드 |
| `lcls_systm_3_name` | 소분류명 |
| `content_type_id` | xlsx mapping 또는 API-derived 관광타입 |
| `content_type_name` | 관광타입명 |
| `aliases` | 자연어 테마 alias |
| `synced_at` | sync 시각 |
| `raw` | 원본 응답 |

초기 테마 alias:

| 사용자 표현 | 분류 후보 |
|---|---|
| 축제 | `EV01` |
| 공연 | `EV02` |
| 행사 | `EV03` |
| 전통체험 | `EX010100` |
| 공예체험 | `EX02` |
| 농촌체험, 어촌체험 | `EX03` |
| 웰니스, 힐링, 스파 | `EX05` |
| 산업관광 | `EX06` |
| 요트 | `LS020300` |
| 수상레저 | `LS02` |
| 패러글라이딩 | `LS030300` |
| 시장 | `SH06` |
| 음식, 미식 | `FD` |
| 섬 | `NA020500` |
| 해변, 해수욕장 | `NA020900` |

## Provider 변경 계획

대상 파일:

- `backend/app/tools/tourism.py`
- `backend/app/schemas/tourism.py`
- `backend/app/rag/source_documents.py`
- `backend/app/agents/workflow.py`

### 신규 provider method

```python
def ldong_code(
    *,
    ldong_regn_cd: str | None = None,
    list_yn: str = "N",
    limit: int = 100,
) -> list[dict[str, Any]]:
    ...

def lcls_system_code(
    *,
    lcls_systm_1: str | None = None,
    lcls_systm_2: str | None = None,
    lcls_systm_3: str | None = None,
    list_yn: str = "N",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    ...
```

### 기존 search method 파라미터 전환

현재:

```python
search_keyword(query=keyword, region_code=region_code)
search_festival(region_code=region_code, start_date=...)
search_stay(region_code=region_code)
area_based_list(region_code=region_code, content_type=...)
```

Phase 9.6 이후:

```python
search_keyword(
    query=keyword,
    ldong_regn_cd=location.ldong_regn_cd,
    ldong_signgu_cd=location.ldong_signgu_cd,
    lcls_systm_1=theme.lcls_systm_1,
    lcls_systm_2=theme.lcls_systm_2,
    lcls_systm_3=theme.lcls_systm_3,
)
```

`region_code`는 backward compatibility alias로 남기되, 새 workflow에서는 사용하지 않습니다.

### `TourismItem` 확장

추가 필드:

```python
legacy_area_code: str | None
legacy_sigungu_code: str | None
ldong_regn_cd: str | None
ldong_regn_nm: str | None
ldong_signgu_cd: str | None
ldong_signgu_nm: str | None
lcls_systm_1: str | None
lcls_systm_2: str | None
lcls_systm_3: str | None
```

정규화 우선순위:

1. `detailCommon2`의 `lDongRegnCd`, `lDongSignguCd`, `lclsSystm1/2/3`
2. 목록 응답의 `lDongRegnCd`, `lDongSignguCd`, `lclsSystm1/2/3`
3. legacy `areacode`, `sigungucode`
4. resolver에서 전달한 location scope

## DB 변경 계획

### `tourism_items`

기존:

```text
region_code
sigungu_code
```

추가:

```text
legacy_area_code
legacy_sigungu_code
ldong_regn_cd
ldong_signgu_cd
lcls_systm_1
lcls_systm_2
lcls_systm_3
geo_resolution_id
```

`region_code`와 `sigungu_code`는 migration 기간 동안 유지합니다.

### `source_documents.document_metadata`

추가 metadata:

```json
{
  "legacy_area_code": "3",
  "legacy_sigungu_code": null,
  "ldong_regn_cd": "30",
  "ldong_signgu_cd": "200",
  "lcls_systm_1": "EV",
  "lcls_systm_2": "EV01",
  "lcls_systm_3": "EV010200",
  "geo_scope_id": "geo_...",
  "geo_role": "primary"
}
```

Chroma filter:

```python
filters={
    "source": "tourapi",
    "ldong_regn_cd": "30",
    "ldong_signgu_cd": "200",
}
```

주의:

- Chroma collection의 metadata schema 자체는 느슨하지만, 기존 vector에는 새 metadata가 없습니다.
- Phase 9.6 적용 후 reset reindex가 필요합니다.

### 신규 테이블 후보

`tourapi_ldong_codes`

```text
id
ldong_regn_cd
ldong_regn_nm
ldong_signgu_cd
ldong_signgu_nm
full_name
normalized_name
aliases_json
raw_json
synced_at
```

`tourapi_lcls_codes`

```text
id
lcls_systm_1
lcls_systm_1_name
lcls_systm_2
lcls_systm_2_name
lcls_systm_3
lcls_systm_3_name
content_type_id
content_type_name
aliases_json
raw_json
synced_at
```

`geo_resolutions`

```text
id
run_id
input_text
mode
status
locations_json
unresolved_locations_json
excluded_locations_json
keywords_json
needs_clarification
clarification_question
confidence
raw_json
created_at
```

## Workflow 변경

### PlannerAgent

현재:

- `request.region` 또는 기본값 부산을 사용합니다.
- 부산만 `region_code=6`으로 하드코딩합니다.

변경:

- `region` field는 optional로 두고 message를 source of truth로 봅니다.
- PlannerAgent는 지리 해석을 하지 않습니다.
- `normalized_request`에는 `message`, `period`, `target_customer`, `product_count`, `preferences`, `avoid`만 안정화합니다.

### GeoResolverAgent

입력:

```json
{
  "message": "부산 부산진구 전포동 일대 외국인 대상 액티비티 상품 3개",
  "region": null,
  "preferences": ["야간 관광", "축제"]
}
```

처리:

1. 장소 후보 추출.
2. 복수 지역 여부와 제외 관계 추출.
3. `tourapi_ldong_codes`에서 exact/normalized/fuzzy 후보 match.
4. 상위 시군구가 확정된 세부 동네명은 keyword로 분리.
5. confidence와 ambiguity 계산.
6. `geo_scope` 저장.

출력:

```json
{
  "geo_scope": {
    "mode": "single_region",
    "locations": [...],
    "needs_clarification": false
  }
}
```

### DataAgent

변경 전:

- 하나의 `region_code`로 keyword/festival/stay를 호출합니다.
- `region_code=None`이면 전국 검색으로 흘러갈 수 있었습니다.

변경 후:

- `geo_scope.locations`를 순회합니다.
- location별로 `lDongRegnCd`, `lDongSignguCd`를 전달합니다.
- 복수 지역 또는 지역 이동형 요청은 데이터 조회 전에 종료합니다.
- `needs_clarification=true`면 데이터 조회 전에 run을 `failed` 상태로 전환하고, 사용자에게 지역 후보 안내를 표시합니다.
- location이 있는 요청에서 `lDongRegnCd`가 없으면 API를 호출하지 않습니다.

DataAgent 검색 전략:

| mode | 검색 전략 |
|---|---|
| `single_region` | 해당 지역의 관광지/레포츠/행사/음식/쇼핑/숙박을 의도에 따라 조회 |
| `unsupported_multi_region` | 조회 금지, 후보 중 하나만 선택하도록 안내 |
| `nearby` | anchor 좌표가 있으면 `locationBasedList2`, 없으면 keyword + ldong |
| `nationwide` | 지역 필터 없이 실행 가능하지만, prompt가 전국 의도인지 명시되어야 함 |
| `clarification_required` | 조회 금지, clarification |

### ResearchAgent

Phase 9.6 최소 변경:

- `geo_scope`와 retrieved docs의 지역 일치율을 summary에 포함합니다.
- Evidence가 요청 지역 밖이면 QA issue로 넘길 수 있는 flag를 남깁니다.

Phase 11에서 확장:

- Product 생성에 지역별 evidence 내용을 깊게 반영합니다.

## Frontend 변경

대상:

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/services/runsApi.ts`
- `frontend/src/pages/RunDetail.tsx`

변경 방향:

1. Create Run modal
   - `Region` 입력을 제거하고 큰 prompt textarea를 중심으로 둡니다.
   - 지역은 message에서 먼저 해석합니다.

2. Run list
   - 단일 `Region` 컬럼 대신 `Geo Scope` 표시.
   - 예: `대전`, `부산 → 양산`, `부산광역시 부산진구 전포동 일대`.

3. Run detail
   - Result Review 상단에 resolved geo scope 표시.
   - Evidence table은 사용자에게 내부 `Geo`/`LCLS` code 컬럼을 노출하지 않습니다.
   - content type은 `EVENT` 같은 내부 enum 대신 `행사`, `숙박`, `관광지`처럼 한국어로 표시합니다.
   - 지역 mismatch 여부는 내부 metadata와 QA/개발 로그에서 확인할 수 있게 유지합니다.

4. Clarification 상태
   - GeoResolverAgent가 애매하다고 판단하면 사용자에게 선택 UI 제공.
   - 예: "중구"는 서울/부산/대구/인천/대전/울산 등 여러 후보가 있습니다.

## 실제 데이터 전환 체크리스트

현재 더미/구형 데이터 의존 지점:

| 영역 | 현재 상태 | Phase 9.6 수정 |
|---|---|---|
| 지역 입력 | `region` field 중심 | message 기반 GeoResolverAgent |
| 지역 코드 | `areaCode2`, `areaCode`, `region_code` | `ldongCode2`, `lDongRegnCd`, `lDongSignguCd` |
| 분류 | `contentTypeId` 중심 | `contentTypeId` + `lclsSystm1/2/3` |
| 테스트 provider | 부산 더미 중심 | 대전/영종도/가덕도/울릉도/양산 fake v4.4 provider |
| RAG metadata | `region_code` | `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3` |
| UI | Region 입력 필드 | 자연어 prompt 중심 + resolved geo 표시 |
| Chroma | 기존 metadata로 색인 | reset reindex 필요 |

## 구현 단계

### Step 1. TourAPI v4.4 provider 확장

작업:

- `ldongCode2` method 추가.
- `lclsSystmCode2` method 추가.
- 목록/search method에 `ldong_regn_cd`, `ldong_signgu_cd`, `lcls_systm_1/2/3` 추가.
- 기존 `region_code`는 deprecated alias로 유지.
- `_tourapi_raw_to_item`이 `lDongRegnCd`, `lDongSignguCd`, `lclsSystm1/2/3`를 읽게 수정.

완료 기준:

- 실제 API로 `ldongCode2(lDongRegnCd=30)` 호출 시 대전 5개 구 반환.
- `searchFestival2(eventStartDate=20260501, lDongRegnCd=30)` 호출 시 대전 행사가 반환.
- 기존 tests는 통과.

### Step 2. Catalog sync

작업:

- DB table 추가.
- `python -m app.tools.sync_tourapi_catalogs` 또는 `python -m app.rag.sync_tourapi_catalogs` CLI 추가.
- `ldongCode2?lDongListYn=Y` 전체 목록을 `pageNo`/`totalCount` 기반으로 paging sync.
- `lclsSystmCode2?lclsSystmListYn=Y` 전체 sync.
- catalog가 비어 있으면 resolver가 seed/fallback으로 추측하지 않고 sync 필요 상태로 중단.

완료 기준:

- DB에 전국 시도/시군구 코드가 저장됨.
- DB에 신분류체계 전체가 저장됨.
- sync 결과 count와 diff가 출력됨.

### Step 3. GeoResolverAgent 구현

작업:

- `backend/app/agents/geo_resolver.py` 추가.
- deterministic resolver 먼저 구현.
- LLM이 켜져 있으면 span extraction에만 Gemini 사용 가능.
- LLM이 꺼져도 official catalog exact/normalized/fuzzy match로 동작.

완료 기준:

- "대전" -> `30`.
- "대전 유성구" -> `30`/`200`.
- "부산 강서구 가덕도" -> `26`/`440`, keyword `가덕도`.
- "인천 중구 영종도" -> `28`/`110`, keyword `영종도`.
- "울릉도" -> `47`/`940`.
- "영양" -> `47`/`760`.
- "부산과 양산을 연결해서" 또는 지역 이동형 요청 -> `unsupported_multi_region`, 후보 중 하나만 선택 안내.
- "중구" -> 후보 여러 개로 run status `failed`, 후보 안내 표시.
- "도쿄 여행 상품" -> `unsupported`.

### Step 4. Workflow 통합

작업:

- LangGraph에 `geo_resolver` node 추가.
- DataAgent가 `geo_scope`를 사용하도록 수정.
- 지역 resolve 실패 시 전국 fallback 금지.
- retrieved documents를 geo_scope 기준으로 후처리 필터링.

완료 기준:

- 새 workflow run의 tool call arguments에 `lDongRegnCd`/`lDongSignguCd`가 남음.
- 지역 명시 요청에서 `None` 지역 필터가 발생하지 않음.
- Evidence가 요청 지역 밖이면 run 실패 또는 QA warning으로 잡힘.

### Step 5. RAG metadata/reindex

작업:

- source document metadata 확장.
- Chroma filter를 `ldong_regn_cd`, `ldong_signgu_cd`로 전환.
- reindex command에 provider/model뿐 아니라 metadata schema 변경 안내 추가.

실행:

```bash
conda activate paravoca-ax-agent-studio
cd backend
python -m app.rag.reindex --collection source_documents --reset
```

완료 기준:

- 새 evidence metadata에 법정동/분류 코드가 포함됨.
- 지역별 query에서 타 지역 evidence가 top result에 섞이지 않음.

### Step 6. Frontend 반영

작업:

- Create Run UI에서 Region 필드 제거.
- Run Detail에 resolved geo scope 표시.
- Evidence table은 상세 정보와 이미지 후보를 보여주되 내부 `Geo`/`LCLS` 코드 컬럼은 숨김.
- Evidence content type은 한국어로 표시.
- ambiguous region clarification UI 추가.

완료 기준:

- 사용자가 message만으로 run 생성 가능.
- 복수 지역 또는 지역 이동형 요청은 UI에서 단일 지역 선택 안내로 표시됨.
- `중구` 요청은 status가 `failed`로 표시되고, 상세 화면에는 지역 후보 안내가 표시됨.
- 해외 목적지가 error처럼 보이지 않고 PARAVOCA 국내 지원 범위 안내로 표시됨.

### Step 7. 테스트

추가 테스트:

| 테스트 | 기대 결과 |
|---|---|
| `대전` | `ldong_regn_cd=30` |
| `대전 유성구` | `30`/`200` |
| `영종도` | catalog에 없으면 `failed` + 지역 후보 안내, 전국 fallback 금지 |
| `가덕도` | catalog에 없으면 `failed` + 지역 후보 안내, 전국 fallback 금지 |
| `인천 중구 영종도` | `28`/`110`, keyword `영종도` 유지 |
| `부산 강서구 가덕도` | `26`/`440`, keyword `가덕도` 유지 |
| `울릉도` | `47`/`940` |
| `영양` | `47`/`760` |
| `부산에서 시작해서 양산에서 끝나는` | `unsupported_multi_region`, 단일 지역 선택 안내 |
| `중구에서` | ambiguous, clarification |
| `부산 부산진구 전포동 일대` | `26`/`230`, keyword `전포동`, 다른 시도 추가 금지 |
| `도쿄 여행 상품` | `unsupported`, 국내 지원 안내 |
| 지역 resolve 실패 | 전국 fallback 금지 |
| 대전 2026-05 행사 검색 | `searchFestival2`에 `lDongRegnCd=30` 전달 |

검증 명령:

```bash
conda activate paravoca-ax-agent-studio
cd backend
pytest -q
cd ../frontend
npm run build
```

## 수용 기준

Phase 9.6 완료 기준:

1. 사용자가 `Region`을 비워도 message에서 지역을 resolve할 수 있습니다.
2. `areaCode`가 아니라 `lDongRegnCd/lDongSignguCd`가 tool call arguments에 남습니다.
3. 지역 명시 요청에서 `region_code=None` 또는 `lDongRegnCd=None`으로 전국 검색하지 않습니다.
4. Evidence metadata에 법정동 코드와 신분류체계 코드가 남습니다.
5. `run_e84714a8a7af42a2`와 같은 대전 요청을 새로 실행했을 때 강릉/정선/고창 evidence가 섞이지 않습니다.
6. 복수 지역/지역 이동형 요청은 데이터 검색 전에 중단되고, 후보 중 하나만 선택하라는 안내가 표시됩니다.
7. ambiguous 지역은 run status `failed`로 남고, 사용자에게 후보를 표시합니다.
8. backend tests와 frontend build가 통과합니다.

## Phase 9.6 이후 남는 작업

Phase 9.6은 evidence 검색 정확도를 고치는 작업입니다. Product 생성이 evidence 내용을 깊게 읽고 itinerary와 marketing copy를 생성하는 것은 Phase 11 범위입니다.

남는 작업:

- ProductAgent가 `geo_scope`와 location별 evidence quota를 사용하도록 개선.
- ResearchAgent가 지역/테마별 insight를 실제 evidence content에서 요약.
- MarketingAgent가 evidence에 없는 운영시간/가격/가능 조건을 단정하지 않도록 prompt 강화.
- QA가 geo mismatch, 기간 mismatch, unsupported claim을 더 강하게 판정.
- Data Enrichment Agent가 부족한 지역/테마 evidence를 추가 API로 보강.

## 구현 프롬프트 초안

Codex에게 Phase 9.6 구현을 요청할 때 사용할 수 있는 명령:

```text
Phase 9.6: GeoResolverAgent와 TourAPI v4.4 ldong/lcls 전환을 구현해줘.

현재 기준:
- Phase 9.5 local semantic embedding까지 완료되어 있음.
- TourAPI 기존 workflow는 areaCode/region_code 중심이라 v4.4 법정동 필터를 제대로 쓰지 못함.
- Region 필드보다 자연어 message에서 지역 의도를 추출하는 구조가 필요함.
- conda env는 paravoca-ax-agent-studio를 사용하고 venv는 만들지 마.

구현 범위:
1. TourAPI provider에 ldongCode2, lclsSystmCode2 method 추가.
2. areaBasedList2/searchKeyword2/searchFestival2/searchStay2/locationBasedList2에 lDongRegnCd, lDongSignguCd, lclsSystm1/2/3 파라미터 추가.
3. TourismItem과 source document metadata에 ldong/lcls 필드 추가.
4. TourAPI catalog sync DB/CLI 추가.
5. GeoResolverAgent 추가.
6. LangGraph workflow에서 Planner 다음에 GeoResolverAgent를 실행.
7. DataAgent가 geo_scope 기준으로 단일 지역 또는 명시적 전국 TourAPI 검색.
8. 지역 resolve 실패 시 전국 검색 금지.
9. RAG filter를 ldong metadata 기준으로 전환하고 reindex 안내 추가.
10. frontend에서 Region 입력을 제거하고 message 중심 입력과 resolved geo scope 표시.
11. 테스트 추가:
   - 대전
   - 대전 유성구
   - 영종도/가덕도 단독 입력은 하드코딩 매핑하지 않고 clarification
   - 인천 중구 영종도, 부산 강서구 가덕도처럼 상위 지역이 있으면 keyword 유지
   - 울릉도
   - 영양
   - 부산 -> 양산 지역 이동형 요청은 단일 지역 선택 안내
   - 중구 ambiguous
   - 부산 부산진구 전포동 일대
   - 도쿄 같은 해외 목적지 unsupported
   - 지역 resolve 실패 시 전국 fallback 금지

검증:
- conda activate paravoca-ax-agent-studio
- cd backend && pytest -q
- cd frontend && npm run build
```
