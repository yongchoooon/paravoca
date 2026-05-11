# Phase 12.3 Theme APIs Actual Connection

작성 기준일: 2026-05-11

Phase 12.3은 99번 KTO API 명세 중 테마 계열을 실제 provider/executor로 연결한 단계입니다. 이 데이터는 상품화 보조 근거이며, 인증, 효능, 안전, 의료 효과, 반려동물 허용 여부를 확정하는 근거로 쓰지 않습니다.

## 구현된 범위

- `kto_wellness`
  - 문서: `99_03_KTO_WELLNESS_TOURISM_SPEC.md`
  - 실제 실행 operation: `searchKeyword`
  - feature flag: `KTO_WELLNESS_ENABLED`
- `kto_pet`
  - 문서: `99_05_KTO_PET_TOUR_SPEC.md`
  - 실제 실행 operation: `searchKeyword2`, 후보별 `detailPetTour2`
  - feature flag: `KTO_PET_ENABLED`
- `kto_audio`
  - 문서: `99_07_KTO_AUDIO_GUIDE_SPEC.md`
  - 실제 실행 operation: `storySearchList`, `themeSearchList`
  - feature flag: `KTO_AUDIO_ENABLED`
- `kto_eco`
  - 문서: `99_08_KTO_ECO_TOURISM_SPEC.md`
  - 실제 실행 operation: `areaBasedList1`
  - feature flag: `KTO_ECO_ENABLED`
- `kto_medical`
  - 문서: `99_04_KTO_MEDICAL_TOURISM_SPEC.md`
  - 실제 실행 operation: `searchKeyword`
  - feature flag: `ALLOW_MEDICAL_API`

base URL은 환경변수가 아니라 `backend/app/tools/themes.py`의 provider 코드 상수로 관리합니다. flag가 꺼져 있거나 `TOURAPI_SERVICE_KEY`가 없으면 실제 호출하지 않고 skipped/disabled로 기록합니다. 의료관광은 `ALLOW_MEDICAL_API=true`일 때만 실제 호출합니다.

## 데이터 흐름

1. `DataGapProfilerAgent`가 `missing_theme_specific_data`, `missing_pet_policy`, `missing_wellness_attributes`, `missing_story_asset`, `missing_multilingual_story`, `missing_sustainability_context`, `missing_medical_context` gap을 만든다.
2. `ApiCapabilityRouterAgent`가 theme 계열이 필요하다고 판단하면 `ThemeDataPlannerAgent`로 배정한다.
3. `ThemeDataPlannerAgent`는 활성화된 source family와 남은 call budget 안에서 필요한 call만 계획한다.
4. `EnrichmentExecutor`가 계획된 theme call만 실행한다.
5. 테마 후보는 `tourism_entities`에 `entity_type=theme_candidate`로 저장한다.
6. 이미지 URL이 있으면 `tourism_visual_assets`에 `usage_status=needs_license_review`로 저장한다.
7. 테마 근거는 source document로 만들어 Chroma에 색인한다.
8. `EvidenceFusionAgent`는 후보별 `theme_candidates`를 `candidate_evidence_cards`에 반영한다.
9. Product/Marketing/QA는 테마 데이터를 보조 근거로만 사용하고, 확인되지 않은 claim은 `needs_review`/`restricted_claims`로 분리한다.

## 저장 정책

`tourism_entities`에는 아래 정보가 저장됩니다.

- source family와 operation
- 후보명, 주소, 문의처
- 연결된 TourAPI item/source item
- theme attributes
- 운영/예약/요금 등 확인 필요 정보
- raw response와 retrieved_at

`tourism_visual_assets`에는 이미지 URL이 있는 후보만 저장합니다.

- source family와 operation
- title/caption 성격의 후보명
- image URL과 thumbnail URL
- 사용권 확인 필요 상태
- raw response와 retrieved_at

source document metadata에는 `source_family`, `content_type=theme`, `theme_source_family`, `theme_attributes`, `needs_review_notes`, `data_quality_flags`, `interpretation_notes`, geo context, `trust_level`을 남깁니다.

## Claim 제한

Theme 데이터는 아래 claim을 허용하지 않습니다.

- 웰니스/의료관광 정보를 건강 개선, 치료, 효능, 안전 보장으로 단정
- 반려동물 API 후보를 실제 동반 가능 확정 정보로 단정
- 생태 관광 정보를 정량 환경 효과나 인증처럼 단정
- 오디오/다국어 후보를 실제 현장 제공 언어로 단정
- 이미지 후보를 게시 확정 이미지로 단정

허용되는 표현은 “테마 후보”, “보조 근거”, “운영자 확인 필요”, “사용권 확인 필요”, “상품화 참고” 수준입니다.

## 비활성/빈 결과/실패 처리

- feature flag가 꺼져 있으면 실제 호출하지 않고 `feature_flag_disabled`로 기록합니다.
- `ALLOW_MEDICAL_API=false`이면 의료관광은 workflow enabled가 되지 않습니다.
- API 결과가 0개이면 workflow 실패가 아니라 “테마 후보 없음” 성격의 성공 summary로 남깁니다.
- API 호출 실패는 해당 enrichment tool call만 `failed`로 남기고 workflow 전체는 계속 진행합니다.
- DB 저장이나 스키마 오류는 개발자가 확인할 수 있도록 failed/error로 남깁니다.

## 아직 하지 않는 것

- 의료/웰니스 효능 claim 자동 생성
- 반려동물 동반 가능 여부 확정 표시
- 테마 API별 ranking 알고리즘 고도화
- 운영자 검수 UI에서 테마 후보를 수동 승인/반려하는 별도 workflow
- Phase 13 배포/운영 준비

## 12.3 완료 후 안정화

Phase 12.3 완료 시점에 함께 정리한 운영 안정화 항목입니다.

- workflow run 상품 생성 상한을 20개로 확장했습니다.
- ProductAgent는 요청 수, 상한 20개, 사용 가능한 evidence document 수를 비교해 실제 생성 개수를 정합니다.
- 요청 수보다 evidence가 부족하면 가능한 개수까지만 생성하고, 부족 사유를 `needs_review`/`coverage_notes`에 남깁니다.
- Run 생성 modal에서는 상품 수 상한만 안내하고, 근거 부족 안내 문구는 제거했습니다.
- ResearchSynthesisAgent는 EvidenceFusion 결과를 대체하지 않고, 원본 evidence card 위에 상품화 해석과 risk guidance만 병합합니다.
- ResearchSynthesisAgent 1차 Gemini 호출은 최대 8,192 output token을 사용하고, timeout 시 `research_synthesis_compact_retry`로 최대 4,096 output token compact 재시도를 수행합니다.
- Gemini HTTP timeout은 `GEMINI_TIMEOUT_SECONDS` 설정값으로 분리했습니다.

## 검증

- `TOURAPI_SERVICE_KEY= conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests`
- `PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build`
- 실제 `.env`의 `TOURAPI_SERVICE_KEY`로 wellness, pet, audio, eco live smoke를 실행합니다.
- medical live smoke는 `ALLOW_MEDICAL_API=true`일 때만 실행합니다.
