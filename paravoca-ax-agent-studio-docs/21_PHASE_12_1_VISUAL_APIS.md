# Phase 12.1 Visual APIs Actual Connection

작성 기준일: 2026-05-10

Phase 12.1은 99번 KTO API 명세 중 Visual 계열을 실제 provider/executor로 연결한 단계입니다. 이 단계의 목표는 이미지를 게시 확정 자산으로 쓰는 것이 아니라, 상품 검토와 상세페이지/포스터 기획에 참고할 수 있는 `이미지 후보`를 수집하고 사용권 확인 필요 상태를 명확히 남기는 것입니다.

## 구현된 범위

- `kto_tourism_photo`
  - 문서: `99_09_KTO_TOURISM_PHOTO_SPEC.md`
  - 실제 실행 operation: `gallerySearchList1`
  - feature flag: `KTO_TOURISM_PHOTO_ENABLED`
- `kto_photo_contest`
  - 문서: `99_02_KTO_PHOTO_CONTEST_AWARD_SPEC.md`
  - 실제 실행 operation: `phokoAwrdList`
  - feature flag: `KTO_PHOTO_CONTEST_ENABLED`

기본값은 둘 다 `false`입니다. flag가 꺼져 있으면 실제 API를 호출하지 않고 skipped/disabled로 기록합니다.

## 데이터 흐름

1. `DataGapProfilerAgent`가 `missing_image_asset` 또는 `missing_visual_reference` gap을 만든다.
2. `ApiCapabilityRouterAgent`가 Visual 계열이 필요하다고 판단하면 `VisualDataPlannerAgent`로 배정한다.
3. `VisualDataPlannerAgent`는 활성화된 source family에 대해서만 짧은 실행 계획을 만든다.
4. `EnrichmentExecutor`가 계획된 visual call만 실행한다.
5. 결과는 `tourism_visual_assets`에 저장하고, source document로도 만들어 Chroma에 색인한다.
6. `EvidenceFusionAgent`는 후보별 `visual_candidates`와 `needs_license_review` 상태를 `candidate_evidence_cards`에 반영한다.
7. Run Detail에서는 이미지를 `이미지 후보`와 `사용권 확인 필요` 상태로 표시한다.

## 저장 정책

`tourism_visual_assets`에는 아래 성격의 정보가 저장됩니다.

- source family와 operation
- 연결된 TourAPI content/source item
- 이미지 URL과 thumbnail URL
- 촬영 장소, 촬영 시기, 촬영자, 키워드
- license/copyright 정보
- `usage_status`
  - `needs_license_review`: 이미지 URL이 있지만 게시 전 사용권 확인 필요
  - `unavailable`: API 응답에 사용 가능한 이미지 URL이 없음

이 이미지는 상품 카드에 바로 게시할 확정 이미지가 아닙니다. Product/Marketing/QA에는 candidate evidence로만 전달하고, 게시 가능/변형 가능/상업 이용 가능 같은 claim은 만들지 않습니다.

## 비활성/빈 결과/실패 처리

- feature flag가 꺼져 있으면 실제 호출하지 않고 `feature_flag_disabled`로 기록합니다.
- API 결과가 0개이면 workflow 실패가 아니라 “이미지 후보 없음” 성격의 성공 summary로 남깁니다.
- API 호출 실패는 해당 enrichment tool call만 `failed`로 남기고 workflow 전체는 계속 진행합니다.
- DB 저장이나 스키마 오류는 개발자가 확인할 수 있도록 failed/error로 남깁니다.

## 아직 하지 않는 것

- Phase 12.3 Theme API 연결
- 이미지 사용권 최종 판정
- Poster Studio 이미지 생성
- ProductAgent 전체 재설계

## 검증

- `TOURAPI_SERVICE_KEY= conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests`
- `PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build`
