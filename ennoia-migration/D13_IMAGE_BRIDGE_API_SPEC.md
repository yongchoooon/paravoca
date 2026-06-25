# D13. Ennoia Image Bridge API Spec

## 목적

Ennoia에서 직접 OpenAI 이미지 API를 호출하면 생성 이미지를 base64로만 다루기 어렵다. 이 브리지 API는 Ennoia API Connector가 포스터 프롬프트와 선택적 참조 이미지 URL을 보내면, 서버가 OpenAI `gpt-image-2` 이미지 API를 호출하고 생성 이미지를 로컬 파일로 저장한 뒤 Ennoia가 렌더링할 수 있는 `image_url`과 `markdown`을 반환한다.

## 운영 구조

```text
Ennoia API Connector
→ Cloudflare Quick Tunnel URL /generate
→ image-bridge FastAPI Docker container
→ OpenAI Images API
→ image-bridge/data/images/{image_id}.jpg 저장
→ Cloudflare URL /images/{image_id}.jpg 반환
→ Ennoia Markdown/HTML에서 이미지 렌더링
```

Quick Tunnel을 쓰는 동안 base URL은 실행할 때마다 바뀔 수 있다. 예:

```text
https://workforce-bean-wind-associate.trycloudflare.com
```

Ennoia API Connector에는 현재 실행 중인 tunnel URL에 `/generate`를 붙여 사용한다.

```text
https://workforce-bean-wind-associate.trycloudflare.com/generate
```

## 인증

`POST /generate`는 bearer token을 요구한다.

```http
Authorization: Bearer {IMAGE_BRIDGE_TOKEN}
```

`IMAGE_BRIDGE_TOKEN`은 데스크탑의 `.env.image-bridge`에 설정된 값이다. Ennoia API Connector의 secret/header 설정에 같은 값을 넣는다.

`GET /health`와 `GET /images/{id}.jpg`는 인증 없이 접근한다. Ennoia가 생성 이미지를 웹 화면에서 바로 불러와야 하기 때문이다.

## Endpoint 요약

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| `GET` | `/health` | 서버 상태 확인 | 없음 |
| `POST` | `/generate` | 이미지 생성 요청 | Bearer token |
| `GET` | `/images/{image_id}.jpg` | 생성 이미지 파일 렌더링 | 없음 |

## GET /health

### Request

```bash
curl https://{TUNNEL_HOST}/health
```

### Response 예시

```json
{
  "status": "ok",
  "model": "gpt-image-2",
  "storage_dir": "data/images",
  "auth_configured": true
}
```

## POST /generate

### Request headers

```http
Authorization: Bearer {IMAGE_BRIDGE_TOKEN}
Content-Type: application/json
```

### Request body

```json
{
  "prompt": "Create one portrait travel promotion poster draft...",
  "input_image_urls": [
    "https://example.com/reference.jpg"
  ],
  "size": "1024x1536",
  "quality": "low",
  "output_format": "jpeg"
}
```

### Fields

| Field | Type | Required | 설명 |
|---|---|---:|---|
| `prompt` | string | yes | OpenAI 이미지 생성에 넣을 최종 프롬프트. A16 PosterPromptBuilderAgent 출력값을 그대로 넣는다. |
| `input_image_urls` | string[] | no | 참조 이미지 URL 배열. 없거나 빈 배열이면 텍스트만으로 생성한다. 최대 3개. |
| `size` | string | no | 기본 `1024x1536`. 허용값: `1024x1024`, `1024x1536`, `1536x1024`, `auto`. |
| `quality` | string | no | 호환용 입력 필드. 서버는 요청값과 무관하게 항상 `medium`으로 OpenAI에 전달한다. |
| `output_format` | string | no | 기본 `jpeg`. 허용값: `png`, `jpeg`, `webp`. latency가 중요하면 `jpeg`를 우선 사용한다. |
| `model` | string | no | 기본 `.env.image-bridge`의 `IMAGE_BRIDGE_MODEL`. 현재 기본 `gpt-image-2`. 보통 생략한다. |

### 이미지 입력이 없을 때

`input_image_urls`를 생략하거나 빈 배열로 보내면 브리지 서버는 OpenAI에 다음 endpoint를 호출한다.

```text
POST https://api.openai.com/v1/images/generations
```

### 이미지 입력이 있을 때

`input_image_urls`가 있으면 브리지 서버는 다음 순서로 처리한다.

1. 각 이미지 URL을 다운로드한다.
2. 이미지 파일 여부와 크기 제한을 확인한다.
3. OpenAI에 다음 endpoint를 multipart form-data로 호출한다.

```text
POST https://api.openai.com/v1/images/edits
```

참조 이미지 URL은 prompt 문자열에 직접 넣지 않는다. 서버가 다운로드한 이미지 bytes를 OpenAI 요청의 `image[]` 파일 필드로 첨부한다.

### Response body

```json
{
  "image_url": "https://{TUNNEL_HOST}/images/20260605T154512345678KST.jpg",
  "markdown": "![generated poster](https://{TUNNEL_HOST}/images/20260605T154512345678KST.jpg)",
  "image_id": "20260605T154512345678KST",
  "input_image_count": 0,
  "model": "gpt-image-2",
  "size": "1024x1536",
  "quality": "low",
  "output_format": "jpeg",
  "provider_response_summary": {
    "endpoint": "images/generations",
    "request_id": "req_...",
    "usage": {
      "input_tokens": 22,
      "output_tokens": 1372,
      "total_tokens": 1394
    },
    "output_format": "jpeg"
  },
  "latency_ms": 69923
}
```

### Response fields

| Field | 설명 |
|---|---|
| `image_url` | Ennoia가 표시할 이미지 URL. 가장 중요한 필드. |
| `markdown` | Ennoia Markdown 출력에 바로 넣을 수 있는 이미지 문법. |
| `image_id` | 저장 파일명에 쓰이는 ID. 실제 파일은 `{image_id}.jpg`. |
| `input_image_count` | 요청에 포함된 참조 이미지 수. |
| `provider_response_summary.endpoint` | OpenAI 호출 종류. 이미지 입력 없음: `images/generations`, 이미지 입력 있음: `images/edits`. |
| `latency_ms` | 전체 처리 시간. 이미지 생성은 수십 초 걸릴 수 있다. |

`image_id`는 UUID가 아니라 생성 시각 기반 문자열이다. 기본 형식은 한국 시간 기준 `YYYYMMDDTHHMMSSffffffKST`이며, 같은 microsecond에 충돌하면 `-2`, `-3` 같은 suffix가 붙을 수 있다. 예: `20260605T154512345678KST.jpg`.

## Ennoia API Connector 설정

### Connector name

```text
AI 포스터 이미지 생성
```

### Method

```text
POST
```

### URL

```text
https://{현재_TUNNEL_HOST}/generate
```

예:

```text
https://workforce-bean-wind-associate.trycloudflare.com/generate
```

### Headers

```text
Authorization: Bearer {IMAGE_BRIDGE_TOKEN}
Content-Type: application/json
```

### Body payload

Ennoia API Connector의 `바디 > Code`에는 JSON Schema가 아니라 실제 요청 payload를 넣는다.
`type`, `properties`, `required`, `additionalProperties`가 들어간 schema 객체를 넣으면 서버는 그 schema 객체를 그대로 body로 받아서 `prompt` 누락 오류를 낸다.

텍스트만으로 생성할 때:

```json
{
  "prompt": "사과 이미지 그려줘",
  "input_image_urls": [],
  "size": "1024x1536",
  "quality": "low",
  "output_format": "jpeg"
}
```

참조 이미지가 있을 때:

```json
{
  "prompt": "Create one portrait travel promotion poster draft...",
  "input_image_urls": [
    "https://tong.visitkorea.or.kr/cms/resource/48/4065248_image2_1.jpg"
  ],
  "size": "1024x1536",
  "quality": "low",
  "output_format": "jpeg"
}
```

Builder로 직접 입력할 때는 아래 필드를 실제 요청 필드로 만든다.
Description은 값이 아니다. 예를 들어 `prompt`의 description에 “사과 이미지 그려줘”를 쓰면 안 되고, `prompt` 필드의 실제 값이 “사과 이미지 그려줘”가 되어야 한다.

| Key | Type | Description |
|---|---|---|
| `prompt` | `string` | 최종 이미지 생성 프롬프트. A17이 `${poster_prompt.last_output.prompt}` 값을 넣는다. |
| `input_image_urls` | `array` | 선택 입력. A17이 `${poster_prompt.last_output.input_image_urls}` 배열을 넣는다. 최대 3개. |
| `input_image_urls` array item | `string` | HTTP(S) image URL to use as a visual reference. |
| `size` | `string` | 기본값 `1024x1536`. |
| `quality` | `string` | 기본값 `low`. |
| `output_format` | `string` | 기본값 `jpeg`. |

서버 기준 required field:

```json
["prompt"]
```

`input_image_urls`는 required가 아니다.

Ennoia workflow 품질 정책:
- A16/A17은 `quality`를 항상 `low`로 보낸다.
- 사용자가 품질, 퀄리티, 고화질, `quality`, `medium`, `high`, `low`를 언급해도 `quality=low`를 유지한다.
- 브리지 서버도 요청 body의 `quality` 값과 무관하게 OpenAI에는 `medium`만 전달한다.
문자열 하나로 보내지 말고 배열로 보낸다.

```json
[
  "https://tong.visitkorea.or.kr/cms/resource/48/4065248_image2_1.jpg"
]
```

## curl 테스트

아래 값은 실행 환경에 맞게 바꾼다.

```bash
export IMAGE_BRIDGE_BASE_URL="https://workforce-bean-wind-associate.trycloudflare.com"
export IMAGE_BRIDGE_TOKEN=".env.image-bridge에_넣은_토큰"
```

### 1. Health check

```bash
curl "$IMAGE_BRIDGE_BASE_URL/health"
```

### 2. 텍스트만으로 이미지 생성

```bash
curl -X POST "$IMAGE_BRIDGE_BASE_URL/generate" \
  -H "Authorization: Bearer $IMAGE_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create one portrait Korean travel poster draft for a family-friendly Busan market tour. Use warm colors, readable Korean title space, and a clean editorial layout.",
    "size": "1024x1536",
    "quality": "low"
  }'
```

예상 결과:

- `input_image_count`: `0`
- `provider_response_summary.endpoint`: `images/generations`
- `image_url`: `/images/{image_id}.jpg`

### 3. 참조 이미지 입력 테스트

테스트 이미지 URL:

```text
https://tong.visitkorea.or.kr/cms/resource/48/4065248_image2_1.jpg
```

curl:

```bash
curl -X POST "$IMAGE_BRIDGE_BASE_URL/generate" \
  -H "Authorization: Bearer $IMAGE_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create one portrait Korean travel poster draft using the provided reference image as visual context. Keep the poster premium, clean, tourism-oriented, and suitable for a Korean travel product. Do not copy logos or add unsupported claims. Include short Korean headline space and concise supporting copy space.",
    "input_image_urls": [
      "https://tong.visitkorea.or.kr/cms/resource/48/4065248_image2_1.jpg"
    ],
    "size": "1024x1536",
    "quality": "low"
  }'
```

예상 결과:

- `input_image_count`: `1`
- `provider_response_summary.endpoint`: `images/edits`
- `image_url`: `/images/{image_id}.jpg`

## 이미지 저장 위치

생성된 이미지는 image-bridge를 실행한 데스크탑 로컬 디스크에 저장된다.

컨테이너 내부:

```text
/app/data/images/{image_id}.jpg
```

호스트 레포 기준:

```text
image-bridge/data/images/{image_id}.jpg
```

예:

```bash
ls -lh image-bridge/data/images/20260605T154512345678KST.jpg
```

Cloudflare Quick Tunnel이 켜져 있는 동안에는 다음 URL로 접근할 수 있다.

```text
https://{TUNNEL_HOST}/images/{image_id}.jpg
```

Quick Tunnel을 끄면 파일은 로컬에 남지만 public URL은 더 이상 접근되지 않는다. Quick Tunnel을 다시 켜면 host가 바뀌므로 Ennoia connector URL도 새 URL로 갱신해야 한다.

## 오류 응답 요약

| 상황 | 상태 코드 | detail.reason 또는 detail |
|---|---:|---|
| Authorization header 없음 | `401` | `Missing bearer token` |
| Bearer token 불일치 | `403` | `Invalid bearer token` |
| body가 schema 객체이거나 `prompt` 누락 | `422` | `body.prompt Field required` |
| OpenAI key 미설정 | `500` | `OPENAI_API_KEY is not configured` |
| 참조 이미지 다운로드 실패 | `400` | `input_image_download_failed` |
| 참조 이미지가 너무 큼 | `400` | `input_image_too_large` |
| 참조 URL이 이미지가 아님 | `400` | `input_url_is_not_image` |
| OpenAI 이미지 API 실패 | `502` | `openai_image_request_failed` |
| OpenAI 응답에 이미지 없음 | `502` | `openai_response_missing_image` |

## 운영 주의사항

- Quick Tunnel URL은 매번 바뀔 수 있으므로 Ennoia connector URL도 같이 바꾼다.
- `.env.image-bridge`의 `IMAGE_BRIDGE_PUBLIC_BASE_URL`도 현재 tunnel host로 맞춘다.
- `IMAGE_BRIDGE_TOKEN`은 Ennoia connector에만 넣고 문서나 로그에 노출하지 않는다.
- 생성 이미지는 git에 올라가지 않는다. `image-bridge/data/images/`는 `.gitignore` 대상이다.
- 이미지 생성은 보통 수십 초 걸릴 수 있다. Ennoia connector timeout을 너무 짧게 잡지 않는다.
