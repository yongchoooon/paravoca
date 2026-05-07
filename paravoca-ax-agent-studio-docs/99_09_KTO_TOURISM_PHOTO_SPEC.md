# 99-09. 한국관광공사 관광사진 정보_GW API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_관광사진 정보_GW` |
| 공식 페이지 | https://www.data.go.kr/data/15101914/openapi.do |
| PARAVOCA source_family | `kto_tourism_photo` |
| 데이터 성격 | `visual` |
| 활용 목적 | 관광사진 갤러리의 제목, 촬영지, 촬영월, 이미지 URL, 키워드를 포스터/상세페이지 시각 근거로 사용합니다. |

원본에는 서비스별 상세기능 목록과 response schema가 중심으로 들어 있습니다. 요청 파라미터 표가 없는 operation은 endpoint와 응답 schema만 확정 정보로 기록하고, 실제 구현 직전 공식 Swagger/활용신청 페이지에서 필수 요청 파라미터를 재확인해야 합니다.

## 공통 호출 규칙

- 공공데이터포털 REST GET 서비스로 취급합니다.
- 인증키, 응답 타입, paging 파라미터 이름은 서비스별 공식 Swagger에서 최종 확인합니다.
- JSON 응답의 `items.item`은 단일 object 또는 list로 올 수 있으므로 provider에서 항상 list로 정규화합니다.
- `resultCode != "0000"`이면 tool call 실패로 기록합니다.
- 빈 결과는 API 실패가 아닐 수 있지만, 지역/키워드/기간 필터가 빠져 전국 fallback이 되는 것은 실패로 봅니다.

## Operation 목록

| 번호 | Operation | Endpoint | 설명 | 일일 트래픽 | 출처 |
|---:|---|---|---|---:|---|
| 1 | `galleryList1` | `/galleryList1` | 관광사진갤러리 목록 조회 | 1000 | 상단 상세기능 |
| 2 | `galleryDetailList1` | `/galleryDetailList1` | 관광사진갤러리 상세 목록 조회 | 1000 | 상단 상세기능 |
| 3 | `gallerySyncDetailList1` | `/gallerySyncDetailList1` | 관광사진갤러리 동기화 목록 조회 | 1000 | 상단 상세기능 |
| 4 | `gallerySearchList1` | `/gallerySearchList1` | 관광사진갤러리 키워드 검색 목록 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 실제 게시 이미지와 생성 참고 이미지를 구분하고, 공공누리/출처 표시/상업적 사용 가능 범위를 확인합니다.

## Operation 상세

### 1. `galleryList1` 관광사진갤러리 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/galleryList1` |
| 설명 | 사진갤러리 목록을 조회하는 기능입니다. 제목으로 중복 콘텐츠를 제거하여 그룹화하고, 사진의 URL경로, 촬영월, 촬영장소 등의 내용을 목록으로 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `galleryList_header`, `galleryList_body`, `galleryList_items`, `galleryList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `galContentTypeId` | `string` | 콘텐츠 타입 아이디 |
| `galPhotographyMonth` | `string` | 촬영월 |
| `galPhotographyLocation` | `string` | 촬영장소 |
| `galWebImageUrl` | `string` | 웹용 이미지 경로 |
| `galCreatedtime` | `string` | 등록일 |
| `galModifiedtime` | `string` | 수정일 |
| `galPhotographer` | `string` | 촬영자 |
| `galSearchKeyword` | `string` | 검색 키워드 |
| `galContentId` | `string` | 콘텐츠 아이디 |
| `galTitle` | `string` | 제목 |

### 2. `galleryDetailList1` 관광사진갤러리 상세 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/galleryDetailList1` |
| 설명 | 사진갤러리 상세 목록을 조회하는 기능입니다. 사진갤러리 목록 조회를 통해 제목에 해당하는 그룹화된 목록이며, 사진의 URL경로, 촬영월, 촬영장소 등의 내용을 목록으로 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `galleryDetailList_header`, `galleryDetailList_body`, `galleryDetailList_items`, `galleryDetailList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `galContentId` | `string` | 콘텐츠 아이디 |
| `galContentTypeId` | `string` | 콘텐츠 타입 아이디 |
| `galTitle` | `string` | 제목 |
| `galWebImageUrl` | `string` | 웹용 이미지 경로 |
| `galCreatedtime` | `string` | 등록일 |
| `galModifiedtime` | `string` | 수정일 |
| `galPhotographyMonth` | `string` | 촬영월 |
| `galPhotographyLocation` | `string` | 촬영장소 |
| `galPhotographer` | `string` | 촬영자 |
| `galSearchKeyword` | `string` | 검색 키워드 |

### 3. `gallerySyncDetailList1` 관광사진갤러리 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/gallerySyncDetailList1` |
| 설명 | 사진갤러리 상세 내용을 동기화으로 목록조회하는 기능 |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `gallerySyncDetailList_header`, `gallerySyncDetailList_body`, `gallerySyncDetailList_items`, `gallerySyncDetailList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultMsg` | `string` | API 호출 결과의 상태 |
| `resultCode` | `string` | API 호출 결과의 상태 코드 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `galUseFlag` | `string` | 콘텐츠 표출여부 |
| `galWebImageUrl` | `string` | 웹용 이미지 경로 |
| `galSearchKeyword` | `string` | 검색 키워드 |
| `galTitle` | `string` | 제목 |
| `galContentId` | `string` | 콘텐츠 아이디 |
| `galContentTypeId` | `string` | 콘텐츠 타입 아이디 |
| `galCreatedtime` | `string` | 등록일 |
| `galModifiedtime` | `string` | 수정일 |
| `galPhotographyMonth` | `string` | 촬영월 |
| `galPhotographyLocation` | `string` | 촬영장소 |
| `galPhotographer` | `string` | 촬영자 |

### 4. `gallerySearchList1` 관광사진갤러리 키워드 검색 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/gallerySearchList1` |
| 설명 | 키워드검색을 통해 사진갤러리 목록을 조회하는 기능입니다. 키워드검색을 통해 키워드 항목데이터와 매칭되는 정보를 목록으로 표출하며, 제목에 해당하는 그룹화된 목록을 제공합니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `gallerySearchList_header`, `gallerySearchList_body`, `gallerySearchList_items`, `gallerySearchList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `galContentId` | `string` | 콘텐츠 아이디 |
| `galContentTypeId` | `string` | 콘텐츠 타입 아이디 |
| `galTitle` | `string` | 제목 |
| `galWebImageUrl` | `string` | 웹용 이미지 경로 |
| `galCreatedtime` | `string` | 등록일 |
| `galModifiedtime` | `string` | 수정일 |
| `galPhotographyMonth` | `string` | 촬영월 |
| `galPhotographyLocation` | `string` | 촬영장소 |
| `galPhotographer` | `string` | 촬영자 |
| `galSearchKeyword` | `string` | 검색 키워드 |
