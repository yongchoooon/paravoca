# 99-13. 한국관광공사 지역별 관광 자원 수요 API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서/한국관광공사_지역별 관광 자원 수요` 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 99번 API 명세 문서의 공통 형식에 맞춰 정리했습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_지역별 관광 자원 수요` |
| 공식 페이지 | https://www.data.go.kr/data/15152138/openapi.do |
| PARAVOCA source_family | `kto_regional_tourism_demand` |
| 데이터 성격 | `signal` |
| 활용 목적 | 지역별 관광 서비스 수요와 문화 자원 수요를 후보 ranking, 지역 매력도 판단, 상품 기획 근거의 보조 신호로 사용합니다. |

이 API는 `한국관광공사_국문 관광정보 서비스_GW`가 아닙니다. KorService2가 관광지/행사/숙박/상세 관광 콘텐츠를 제공하는 core tourism API라면, 이 문서는 지역 단위 수요지표를 제공하는 별도 signal API입니다.

원본에는 상세기능 목록과 response schema가 중심으로 들어 있습니다. 요청 파라미터 표가 없으므로 endpoint와 응답 schema만 확정 정보로 기록하고, 실제 구현 직전 공식 Swagger/활용신청 페이지에서 필수 요청 파라미터를 재확인해야 합니다.

## 공통 호출 규칙

- 공공데이터포털 REST GET 서비스로 취급합니다.
- 인증키, 응답 타입, paging 파라미터 이름은 공식 Swagger에서 최종 확인합니다.
- JSON 응답의 `items.item`은 단일 object 또는 list로 올 수 있으므로 provider에서 항상 list로 정규화합니다.
- `resultCode != "0000"`이면 tool call 실패로 기록합니다.
- 수요 지표는 상품 판매량, 예약 가능성, 매출을 보장하지 않습니다. 생성 결과에서는 “수요 신호”, “관심 가능성”, “보조 근거” 수준으로만 표현합니다.

## Operation 목록

| 번호 | Operation | Endpoint | 설명 | 일일 트래픽 |
|---:|---|---|---|---:|
| 1 | `areaTarSvcDemList` | `/areaTarSvcDemList` | 지역별 관광 서비스 수요 정보 목록 조회 | 1000 |
| 2 | `areaCulResDemList` | `/areaCulResDemList` | 지역별 문화 자원 수요 정보 목록 조회 | 1000 |

## 구현 주의

- `baseYm`은 기준 연월이므로 workflow의 여행 기간과 직접 일치하지 않을 수 있습니다.
- `areaCd`/`signguCd`는 이 API의 지역/시군구 코드입니다. KorService2의 `lDongRegnCd`/`lDongSignguCd`와 바로 동일하다고 가정하지 말고 catalog mapping 또는 별도 변환 계층을 둡니다.
- 지표값(`tarSvcDemIxVal`, `culResDemIxVal`)은 정량 ranking 보조값으로만 사용하고, 실제 수요나 매출 예측으로 단정하지 않습니다.

## Operation 상세

### 1. `areaTarSvcDemList` 지역별 관광 서비스 수요 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaTarSvcDemList` |
| 설명 | 지역별 관광 서비스 수요 정보 목록을 조회합니다. 관광 서비스 수요는 SNS 언급량, 소비액, 내비게이션 검색량 세부 지표로 구성됩니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaTarSvcDemList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과 상태 코드 |
| `resultMsg` | `string` | API 호출 결과 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지 결과 수 |
| `pageNo` | `number` | 현재 페이지 번호 |
| `totalCount` | `number` | 전체 결과 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `tarSvcDemIxVal` | `string` | 관광 서비스 수요 세부 지표값 |
| `baseYm` | `string` | 기준 연월 |
| `areaCd` | `string` | 지역 코드 |
| `areaNm` | `string` | 지역명 |
| `signguCd` | `string` | 시군구 코드 |
| `signguNm` | `string` | 시군구명 |
| `tarSvcDemIxCd` | `string` | 관광 서비스 수요 지표 코드 |
| `tarSvcDemIxNm` | `string` | 관광 서비스 수요 세부 지표명 |

세부 지표 구성:

| 지표 범위 | 설명 |
|---|---|
| SNS 언급량 | 각 지자체별 관광 관련 언급량 중 레포츠, 휴식/힐링, 미식, 체험 여행 유형별 키워드 언급 수 |
| 소비액 | 각 지자체별 쇼핑업, 식음료, 숙박업, 운송업, 여가 서비스업 업종별 소비액 |
| 내비게이션 검색량 | 각 지자체별 내비게이션 목적지 검색량 중 숙박, 음식, 쇼핑 유형별 목적지 검색량 |

### 2. `areaCulResDemList` 지역별 문화 자원 수요 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/areaCulResDemList` |
| 설명 | 지역별 문화 자원 수요 정보 목록을 조회합니다. 문화 자원 수요는 내비게이션 검색량 세부 지표로 구성됩니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `areaCulResDemList_response` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과 상태 코드 |
| `resultMsg` | `string` | API 호출 결과 상태 메시지 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지 결과 수 |
| `pageNo` | `number` | 현재 페이지 번호 |
| `totalCount` | `number` | 전체 결과 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `culResDemIxVal` | `string` | 문화 자원 수요 세부 지표값 |
| `baseYm` | `string` | 기준 연월 |
| `areaCd` | `string` | 지역 코드 |
| `areaNm` | `string` | 지역명 |
| `signguCd` | `string` | 시군구 코드 |
| `signguNm` | `string` | 시군구명 |
| `culResDemIxCd` | `string` | 문화 자원 수요 지표 코드 |
| `culResDemIxNm` | `string` | 문화 자원 수요 세부 지표명 |

세부 지표 구성:

| 지표 범위 | 설명 |
|---|---|
| 내비게이션 검색량 | 각 지자체별 내비게이션 목적지 검색량 중 문화 관광, 레저 스포츠, 역사 관광, 체험 관광, 자연 관광 유형별 목적지 검색량 |
