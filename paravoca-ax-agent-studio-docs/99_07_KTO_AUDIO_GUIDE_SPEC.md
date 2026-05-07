# 99-07. 한국관광공사 관광지 오디오 가이드정보_GW API 명세

작성 기준일: 2026-05-07

이 문서는 `API명세서` 폴더의 원본을 PARAVOCA 구현 기준으로 정규화한 내부 API 명세입니다. 원본의 endpoint 이름과 응답 필드명은 그대로 보존하고, 서비스마다 달랐던 출력 형식을 공통 Markdown 구조로 맞췄습니다.

## 원본과 범위

| 항목 | 값 |
|---|---|
| 원본 입력 파일 | `API명세서/한국관광공사_관광지 오디오 가이드정보_GW` |
| 공식 페이지 | https://www.data.go.kr/data/15101971/openapi.do |
| PARAVOCA source_family | `kto_audio` |
| 데이터 성격 | `story` |
| 활용 목적 | 관광지/이야기 정보, 다국어 지원, 오디오/대본/이미지 URL을 스토리텔링 보강 근거로 사용합니다. |

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
| 1 | `themeBasedList` | `/themeBasedList` | 관광지 기본 정보 목록 조회 | 1000 | 상단 상세기능 |
| 2 | `themeLocationBasedList` | `/themeLocationBasedList` | 관광지 위치기반 정보 목록 조회 | 1000 | 상단 상세기능 |
| 3 | `themeSearchList` | `/themeSearchList` | 관광지 키워드 검색 목록 조회 | 1000 | 상단 상세기능 |
| 4 | `storyBasedList` | `/storyBasedList` | 이야기 기본 정보 목록 조회 | 1000 | 상단 상세기능 |
| 5 | `storyLocationBasedList` | `/storyLocationBasedList` | 이야기 위치기반 정보 목록 조회 | 1000 | 상단 상세기능 |
| 6 | `storySearchList` | `/storySearchList` | 이야기 키워드 검색 목록 조회 | 1000 | 상단 상세기능 |
| 7 | `themeBasedSyncList` | `/themeBasedSyncList` | 관광지정보 동기화 목록 조회 | 1000 | 상단 상세기능 |
| 8 | `storyBasedSyncList` | `/storyBasedSyncList` | 이야기정보 동기화 목록 조회 | 1000 | 상단 상세기능 |

## 구현 주의

- 대본 원문은 장문 복제하지 않고 요약과 출처 중심으로 저장합니다. 음성/이미지 사용 조건은 별도 확인합니다.

## Operation 상세

### 1. `themeBasedList` 관광지 기본 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/themeBasedList` |
| 설명 | 관광지 기본정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `themeBasedList_header`, `themeBasedList_body`, `themeBasedList_items`, `themeBasedList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `themeCategory` | `string` | 테마유형 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 주소상세 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |
| `langCheck` | `string` | 제공언어 |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |

### 2. `themeLocationBasedList` 관광지 위치기반 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/themeLocationBasedList` |
| 설명 | 내주변 좌표를 기반으로 관광지 정보목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `themeLocationBasedList_header`, `themeLocationBasedList_body`, `themeLocationBasedList_items`, `themeLocationBasedList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `langCheck` | `string` | 제공언어 |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `themeCategory` | `string` | 테마유형 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 주소상세 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |

### 3. `themeSearchList` 관광지 키워드 검색 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/themeSearchList` |
| 설명 | 키워드로 검색을 하여 관광지정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `themeSearchList_header`, `themeSearchList_body`, `themeSearchList_items`, `themeSearchList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `themeCategory` | `string` | 테마유형 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 주소상세 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |
| `langCheck` | `string` | 제공언어 |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |

### 4. `storyBasedList` 이야기 기본 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/storyBasedList` |
| 설명 | 이야기 기본정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `storyBasedList_header`, `storyBasedList_body`, `storyBasedList_items`, `storyBasedList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `stid` | `string` | 이야기아이디 |
| `stlid` | `string` | 이야기언어아이디 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |
| `audioTitle` | `string` | 오디오타이틀 |
| `script` | `string` | 대본 |
| `playTime` | `string` | 재생시간 |
| `audioUrl` | `string` | 오디오파일URL |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |

### 5. `storyLocationBasedList` 이야기 위치기반 정보 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/storyLocationBasedList` |
| 설명 | 내주변 좌표를 기반으로 이야기 정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `storyLocationBasedList_header`, `storyLocationBasedList_body`, `storyLocationBasedList_items`, `storyLocationBasedList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `stid` | `string` | 이야기아이디 |
| `stlid` | `string` | 이야기언어아이디 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |
| `audioTitle` | `string` | 오디오타이틀 |
| `script` | `string` | 대본 |
| `playTime` | `string` | 재생시간 |
| `audioUrl` | `string` | 오디오파일URL |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |

### 6. `storySearchList` 이야기 키워드 검색 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/storySearchList` |
| 설명 | 키워드로 검색을 하여 이야기 정보 목록을 조회하는 기능입니다. |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `storySearchList_header`, `storySearchList_body`, `storySearchList_items`, `storySearchList_item` |

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
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `stid` | `string` | 이야기아이디 |
| `stlid` | `string` | 이야기언어아이디 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |
| `audioTitle` | `string` | 오디오타이틀 |
| `script` | `string` | 대본 |
| `playTime` | `string` | 재생시간 |
| `audioUrl` | `string` | 오디오파일URL |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |

### 7. `themeBasedSyncList` 관광지정보 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/themeBasedSyncList` |
| 설명 | 관광지정보 동기화 목록을 조회하는 기능 |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `themeBasedSyncList_header`, `themeBasedSyncList_body`, `themeBasedSyncList_items`, `themeBasedSyncList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `syncStatus` | `string` | 콘텐츠상태 |
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `themeCategory` | `string` | 테마유형 |
| `addr1` | `string` | 주소 |
| `addr2` | `string` | 주소상세 |
| `title` | `string` | 관광지명 |
| `mapX` | `string` | 경도(X) |
| `mapY` | `string` | 위도(Y) |
| `langCheck` | `string` | 제공언어 |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |

### 8. `storyBasedSyncList` 이야기정보 동기화 목록 조회

| 항목 | 값 |
|---|---|
| Endpoint | `/storyBasedSyncList` |
| 설명 | 이야기정보 동기화 목록을 조회하는 기능 |
| 일일 트래픽 | 1000 |
| 매칭한 schema block | `storyBasedSyncList_header`, `storyBasedSyncList_body`, `storyBasedSyncList_items`, `storyBasedSyncList_item` |

응답 header 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `resultCode` | `string` | API 호출 결과의 상태 코드 |
| `resultMsg` | `string` | API 호출 결과의 상태 |

Paging/body 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `numOfRows` | `number` | 한 페이지의 결과 수 |
| `pageNo` | `number` | 현재 조회된 데이터의 페이지 번호 |
| `totalCount` | `number` | 전체 데이터의 총 수 |

Item 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `mapX` | `string` | 경도(X) |
| `title` | `string` | 관광지명 |
| `mapY` | `string` | 위도(Y) |
| `audioTitle` | `string` | 오디오타이틀 |
| `script` | `string` | 대본 |
| `playTime` | `string` | 재생시간 |
| `audioUrl` | `string` | 오디오파일URL |
| `langCode` | `string` | 언어 |
| `imageUrl` | `string` | 관광지이미지URL |
| `createdtime` | `string` | 등록일 |
| `modifiedtime` | `string` | 수정일 |
| `syncStatus` | `string` | 콘텐츠상태 |
| `tid` | `string` | 관광지아이디 |
| `tlid` | `string` | 관광지언어아이디 |
| `stid` | `string` | 이야기아이디 |
| `stlid` | `string` | 이야기언어아이디 |
