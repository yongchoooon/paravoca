# Phase 12.0 Retrieval Stability and Empty Result UX

작성 기준일: 2026-05-10

Phase 12.0은 추가 KTO API를 실제 연결하기 전, 기존 TourAPI/RAG 검색 흐름이 잘못된 지역 근거를 섞거나 빈 결과를 내부 오류처럼 보여주는 문제를 정리한 안정화 단계입니다.

## 구현 요약

- Chroma 검색에서 metadata filter를 query `where` 조건으로 먼저 적용합니다.
- `source`, `ldong_regn_cd`, `ldong_signgu_cd`, `content_type`, `source_family`, `test_case` filter와 list `$in` filter를 지원합니다.
- Python 후처리 filter는 안전장치로 유지합니다.
- `BaselineDataAgent`가 TourAPI 수집, source document upsert, indexing, vector search, post-filter count를 diagnostics로 남깁니다.
- 데이터가 실제로 부족한 경우 `RuntimeError` stack trace 대신 `insufficient_source_data` final output을 생성합니다.
- 사용자 화면은 “관광 근거 데이터가 부족합니다” 안내와 다음 요청 제안을 보여주고, Developer 화면은 diagnostics와 raw error/debug 정보를 유지합니다.

## GeoResolver 보정

GeoResolverAgent는 이제 단순히 장소 span만 추출하지 않고, Gemini prompt에 TourAPI `ldongCode2` catalog 후보를 함께 받아 `resolved_locations`를 출력합니다.

역할 분리는 다음과 같습니다.

- Gemini GeoResolverAgent: 자연어 지역 표현을 보고 TourAPI catalog 후보 중 실제 검색에 사용할 시도/시군구 코드를 선택합니다.
- Python resolver: Gemini가 고른 코드가 실제 catalog에 있는지, confidence가 충분한지 검증합니다.
- Python matcher fallback: 명확한 exact/normalized/fuzzy 행정구역명만 처리하고, 확신이 낮으면 clarification으로 보냅니다.

`대청도` 같은 섬/생활권/관광지명은 TourAPI 법정동 catalog에 직접 없을 수 있습니다. 이 경우 Gemini가 catalog 후보 중 상위 시군구를 선택하면, 예를 들어 `인천광역시 옹진군` 코드를 사용하되 원문 지명 `대청도`는 keyword로 보존합니다.

중요 정책:

- 특정 지명 예시를 코드에 하드코딩하지 않습니다.
- catalog에 없는 지명을 Python 부분 문자열 match로 억지 확정하지 않습니다.
- `대청도`가 `청도군`처럼 부분 문자열로 잘못 매칭되지 않도록 normalized/fuzzy match를 강화했습니다.
- Gemini가 고른 code가 catalog에 없거나 confidence가 낮으면 확정하지 않습니다.

## 좁은 지역 keyword filter

TourAPI가 시도/시군구까지만 filter를 지원하는 경우가 있습니다. 이때 workflow는 다음 순서로 동작합니다.

1. 상위 시군구 코드로 TourAPI를 조회합니다.
2. GeoResolver가 보존한 keyword 또는 sub-area term을 확인합니다.
3. 수집한 item의 title/address/overview/raw에 keyword가 있는 항목만 남깁니다.
4. RAG 검색 결과도 title/content/metadata에 keyword가 있는 문서만 남깁니다.
5. 남는 근거가 없으면 상위 시군구 전체나 전국으로 자동 fallback하지 않고 `insufficient_source_data`로 종료합니다.

예:

- 사용자 입력: `대청도 액티비티 상품`
- 확정 코드: `인천광역시 옹진군`
- 보존 keyword: `대청도`
- 최종 후보: 옹진군 전체가 아니라 `대청도`가 포함된 item/document만 사용

## DataGapProfiler 안정화

DataGapProfilerAgent가 후보마다 반복적인 gap을 길게 펼쳐 `MAX_TOKENS`로 실패하던 문제를 줄였습니다.

변경 사항:

- `missing_overview`는 허용 gap type으로 쓰지 않습니다.
- 개요/상세 설명 부족은 `missing_detail_info`로 통합합니다.
- 같은 `target_item_id`에는 item-level gap을 최대 1개만 만들도록 prompt에서 제한합니다.
- `gaps` 출력은 최대 24개로 제한합니다.
- `reason`, `productization_impact`, `needs_review` 길이와 개수를 제한합니다.
- normalize 단계에서도 gap을 severity 기준으로 정렬하고 최대 24개만 유지합니다.

`maxOutputTokens`는 여전히 필요합니다. 모델/API에는 출력 한계가 있고, 제한을 없애거나 크게 늘리는 것은 구조적으로 긴 JSON을 더 오래 생성하다 실패하게 만들 수 있습니다. Phase 12.0의 해결 방향은 출력 한도 상향이 아니라, Agent가 목적에 맞는 짧은 gap report만 만들도록 제한하는 것입니다.

## 검증

검증 명령:

```bash
TOURAPI_SERVICE_KEY= conda run -n paravoca-ax-agent-studio pytest -q backend/app/tests
PATH=/Users/yongchoooon/miniforge3/envs/paravoca-ax-agent-studio/bin:$PATH npm run build
```

검증 결과:

- Backend: `84 passed, 2 skipped`
- Frontend build: 성공, Vite chunk size warning만 있음

## 다음 단계

다음 구현은 Phase 12.1이었고, 현재는 Phase 12.2까지 구현 완료 상태입니다.

Phase 12.1에서는 99번 문서에 정리된 Visual 계열 API를 실제 provider/executor로 연결합니다.

- 관광사진 정보_GW
- 관광공모전 사진 수상작 정보
- 이미지 후보 저장
- 이미지 라이선스/사용 조건 표시
- Product card / Evidence + QA / Poster Studio hints로 연결

Phase 12.2에서는 두루누비, 연관 관광지, 관광빅데이터, 혼잡 예측, 지역 관광수요 provider/executor를 연결했고, 다음 구현은 Phase 12.3 Theme APIs입니다.
