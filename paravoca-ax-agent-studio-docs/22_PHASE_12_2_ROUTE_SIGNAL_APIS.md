# Phase 12.2 Route / Related Places / Demand Signals Actual Connection

작성 기준일: 2026-05-10

Phase 12.2는 99번 KTO API 명세 중 동선, 연관 장소, 수요/혼잡 신호 계열을 실제 provider/executor로 연결한 단계입니다. 이 데이터는 상품 운영을 확정하는 근거가 아니라, 코스 후보, 주변 확장 후보, 시장성/혼잡 리스크를 판단하는 보조 근거입니다.

## 구현된 범위

- `kto_durunubi`
  - 문서: `99_06_KTO_DURUNUBI_SPEC.md`
  - 실제 실행 operation: `courseList`
  - feature flag: `KTO_DURUNUBI_ENABLED`
- `kto_related_places`
  - 문서: `99_12_KTO_RELATED_PLACES_SPEC.md`
  - 실제 실행 operation: `areaBasedList1`, `searchKeyword1`
  - feature flag: `KTO_RELATED_PLACES_ENABLED`
- `kto_tourism_bigdata`
  - 문서: `99_10_KTO_TOURISM_BIGDATA_SPEC.md`
  - 실제 실행 operation: `metcoRegnVisitrDDList`, `locgoRegnVisitrDDList`
  - feature flag: `KTO_BIGDATA_ENABLED`
- `kto_crowding_forecast`
  - 문서: `99_11_KTO_CROWDING_FORECAST_SPEC.md`
  - 실제 실행 operation: `tatsCnctrRatedList`
  - feature flag: `KTO_CROWDING_ENABLED`
- `kto_regional_tourism_demand`
  - 문서: `99_13_KTO_REGIONAL_TOURISM_DEMAND_SPEC.md`
  - 실제 실행 operation: `areaTarSvcDemList`, `areaCulResDemList`
  - feature flag: `KTO_REGIONAL_TOURISM_DEMAND_ENABLED`

base URL은 환경변수가 아니라 `backend/app/tools/route_signals.py`의 provider 코드 상수로 관리합니다. flag가 꺼져 있거나 `TOURAPI_SERVICE_KEY`가 없으면 실제 호출하지 않고 skipped/disabled로 기록합니다.

## 데이터 흐름

1. `DataGapProfilerAgent`가 `missing_route_context`, `missing_related_places`, `missing_demand_signal`, `missing_crowding_signal`, `missing_regional_demand_signal` gap을 만든다.
2. `ApiCapabilityRouterAgent`가 route/signal 계열이 필요하다고 판단하면 `RouteSignalPlannerAgent`로 배정한다.
3. `RouteSignalPlannerAgent`는 활성화된 source family와 남은 call budget 안에서 필요한 call만 계획한다.
4. `EnrichmentExecutor`가 계획된 route/signal call만 실행한다.
5. 두루누비 코스는 `tourism_route_assets`에 저장하고, 수요/혼잡/연관 장소 신호는 `tourism_signal_records`에 저장한다.
6. 저장된 route/signal 근거는 source document로 만들어 Chroma에 색인한다.
7. `EvidenceFusionAgent`는 후보별 `route_assets`, `signal_records`를 `candidate_evidence_cards`에 반영한다.
8. Product/Marketing/QA는 이 데이터를 보조 근거로만 사용하고, 판매량/예약 가능성/안전 보장 claim은 만들지 않는다.

## 저장 정책

`tourism_route_assets`에는 아래 정보가 저장됩니다.

- source family와 operation
- 연결된 TourAPI content/source item
- 코스명, 길명, GPX URL
- 거리, 예상 소요 시간
- 안전/운영 확인 메모
- raw response와 retrieved_at

`tourism_signal_records`에는 아래 정보가 저장됩니다.

- source family와 operation
- signal type
  - `related_places`
  - `visitor_demand`
  - `crowding_forecast`
  - `regional_service_demand`
  - `regional_culture_resource_demand`
- 지역 코드, 시군구 코드
- 기준 기간
- 값 payload
- interpretation note
- raw response와 retrieved_at

source document metadata에는 `source_family`, `content_type=route|signal`, `route_asset_id`, `signal_record_id`, `trust_level`, `data_quality_flags`, `interpretation_notes`, geo context를 남깁니다.

## Claim 제한

Route/signal 데이터는 아래 claim을 허용하지 않습니다.

- 방문자 수를 판매량이나 예약 가능성으로 단정
- 혼잡 예측을 실제 현장 혼잡, 안전, 쾌적함 보장으로 단정
- 연관 관광지를 실제 이동 가능한 코스로 단정
- 두루누비 코스를 PARAVOCA 상품의 확정 운영 동선으로 단정

허용되는 표현은 “보조 신호”, “코스 후보”, “운영자 확인 필요”, “우선순위 판단 참고” 수준입니다.

## 비활성/빈 결과/실패 처리

- feature flag가 꺼져 있으면 실제 호출하지 않고 `feature_flag_disabled`로 기록합니다.
- API 결과가 0개이면 workflow 실패가 아니라 “후보 없음” 성격의 성공 summary로 남깁니다.
- API 호출 실패는 해당 enrichment tool call만 `failed`로 남기고 workflow 전체는 계속 진행합니다.
- DB 저장이나 스키마 오류는 개발자가 확인할 수 있도록 failed/error로 남깁니다.

## 아직 하지 않는 것

- Theme API 연결은 이후 `23_PHASE_12_3_THEME_APIS.md`에서 구현 완료
- 두루누비 `routeList`를 `courseList` 결과와 계층적으로 결합
- 지역 관광수요 코드와 KorService2 ldong 코드의 정교한 별도 매핑
- route/signal 기반 ranking 알고리즘 고도화
- ProductAgent 전체 재설계

## 검증

- `TOURAPI_SERVICE_KEY= conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests`
- `PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build`
