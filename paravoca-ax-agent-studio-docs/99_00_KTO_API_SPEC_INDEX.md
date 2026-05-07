# 99. KTO API 명세 인덱스

작성 기준일: 2026-05-07

이 인덱스는 PARAVOCA에서 사용하거나 사용 예정인 한국관광공사/KTO API 명세를 99번 문서 체계로 통합한 것입니다. `API명세서` 폴더의 원본 파일과 기존 `05_03_TOURAPI_KORSERVICE2_V44_SPEC.md`를 읽어, endpoint 목록과 response schema를 같은 형식으로 재정리했습니다.

## Canonical 문서 목록

| 번호 | 문서 | API/source_family | 성격 | 원본 |
|---:|---|---|---|---|
| 99-01 | [99_01_KTO_TOURAPI_KORSERVICE2_V44_SPEC.md](./99_01_KTO_TOURAPI_KORSERVICE2_V44_SPEC.md) | `kto_tourapi_kor` | `core_tourism` | `05_03_TOURAPI_KORSERVICE2_V44_SPEC.md` |
| 99-02 | [99_02_KTO_PHOTO_CONTEST_AWARD_SPEC.md](./99_02_KTO_PHOTO_CONTEST_AWARD_SPEC.md) | `kto_photo_contest` | `visual` | `API명세서/한국관광공사_관광공모전(사진) 수상작 정보` |
| 99-03 | [99_03_KTO_WELLNESS_TOURISM_SPEC.md](./99_03_KTO_WELLNESS_TOURISM_SPEC.md) | `kto_wellness` | `theme` | `API명세서/한국관광공사_웰니스관광정보` |
| 99-04 | [99_04_KTO_MEDICAL_TOURISM_SPEC.md](./99_04_KTO_MEDICAL_TOURISM_SPEC.md) | `kto_medical` | `theme/high_risk` | `API명세서/한국관광공사_의료관광정보` |
| 99-05 | [99_05_KTO_PET_TOUR_SPEC.md](./99_05_KTO_PET_TOUR_SPEC.md) | `kto_pet` | `theme` | `API명세서/한국관광공사_반려동물_동반여행_서비스` |
| 99-06 | [99_06_KTO_DURUNUBI_SPEC.md](./99_06_KTO_DURUNUBI_SPEC.md) | `kto_durunubi` | `route` | `API명세서/한국관광공사_두루누비 정보 서비스_GW` |
| 99-07 | [99_07_KTO_AUDIO_GUIDE_SPEC.md](./99_07_KTO_AUDIO_GUIDE_SPEC.md) | `kto_audio` | `story` | `API명세서/한국관광공사_관광지 오디오 가이드정보_GW` |
| 99-08 | [99_08_KTO_ECO_TOURISM_SPEC.md](./99_08_KTO_ECO_TOURISM_SPEC.md) | `kto_eco` | `theme` | `API명세서/한국관광공사_생태 관광 정보_GW` |
| 99-09 | [99_09_KTO_TOURISM_PHOTO_SPEC.md](./99_09_KTO_TOURISM_PHOTO_SPEC.md) | `kto_tourism_photo` | `visual` | `API명세서/한국관광공사_관광사진 정보_GW` |
| 99-10 | [99_10_KTO_TOURISM_BIGDATA_SPEC.md](./99_10_KTO_TOURISM_BIGDATA_SPEC.md) | `kto_tourism_bigdata` | `signal` | `API명세서/한국관광공사_관광빅데이터 정보서비스_ GW` |
| 99-11 | [99_11_KTO_CROWDING_FORECAST_SPEC.md](./99_11_KTO_CROWDING_FORECAST_SPEC.md) | `kto_crowding_forecast` | `signal` | `API명세서/한국관광공사_관광지 집중률 방문자 추이 예측 정보` |
| 99-12 | [99_12_KTO_RELATED_PLACES_SPEC.md](./99_12_KTO_RELATED_PLACES_SPEC.md) | `kto_related_places` | `signal` | `API명세서/한국관광공사_관광지별 연관 관광지 정보` |
| 99-13 | [99_13_KTO_REGIONAL_TOURISM_DEMAND_SPEC.md](./99_13_KTO_REGIONAL_TOURISM_DEMAND_SPEC.md) | `kto_regional_tourism_demand` | `signal` | `API명세서/한국관광공사_지역별 관광 자원 수요` |

## 정리 기준

- 파일명과 문서 번호는 `99_00`-`99_13` 체계로 통일했습니다.
- 기존 `05_03_TOURAPI_KORSERVICE2_V44_SPEC.md`는 보존하되, API 명세 canonical 문서는 `99_01_KTO_TOURAPI_KORSERVICE2_V44_SPEC.md`입니다.
- 원본의 endpoint명, operation명, response field명은 임의로 바꾸지 않았습니다.
- 원본 상세기능 목록에 없지만 response schema가 있는 operation은 각 문서에서 `response schema만 있음`으로 표시했습니다.
- 원본에 요청 파라미터 표가 없는 서비스는 구현 직전 공식 Swagger에서 필수 파라미터를 재확인해야 합니다.

## 누락 확인

이전 보강 계획에서 언급한 API 중 `API명세서` 폴더에서 원본 파일을 찾지 못한 항목입니다.

| API | 상태 | 조치 |
|---|---|---|
| 없음 | 2026-05-07 현재 모두 정리됨 | `한국관광공사_지역별 관광 자원 수요`는 `99-13`에 정리했습니다. |

`국문 관광정보 서비스_GW`, `지역별 관광 자원 수요`, `관광공모전 사진 수상작`, `웰니스`, `의료`, `반려동물`, `두루누비`, `오디오 가이드`, `생태 관광`, `관광사진`, `관광빅데이터`, `집중률 예측`, `연관 관광지` 원본은 확인해 99번 문서로 정리했습니다.
