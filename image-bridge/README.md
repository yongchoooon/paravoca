# PARAVOCA Ennoia Image Bridge

Ennoia API Connector에서 포스터 프롬프트와 선택적 참조 이미지 URL을 보내면, 이 FastAPI 컨테이너가 OpenAI image API를 호출하고 생성 이미지를 로컬에 저장한 뒤 public image URL을 반환한다.

## Request

```http
POST /generate
Authorization: Bearer <IMAGE_BRIDGE_TOKEN>
Content-Type: application/json
```

```json
{
  "prompt": "Create one portrait travel promotion poster draft...",
  "input_image_urls": ["https://example.com/reference.jpg"],
  "size": "1024x1536",
  "quality": "low",
  "output_format": "jpeg"
}
```

`input_image_urls`는 선택값이며 최대 3개다. `output_format`은 선택값이며 기본값은 `jpeg`다. 허용값은 `png`, `jpeg`, `webp`다.

## Behavior

- `input_image_urls`가 없으면 `POST https://api.openai.com/v1/images/generations`를 JSON으로 호출한다.
- `input_image_urls`가 있으면 서버가 URL을 다운로드한 뒤 `POST https://api.openai.com/v1/images/edits`를 multipart form-data로 호출한다.
- OpenAI 요청에는 기본적으로 `output_format=jpeg`를 포함한다. OpenAI 공식 문서 기준 JPEG는 PNG보다 빠르므로 latency가 중요할 때 우선 사용할 수 있다.
- OpenAI 응답의 `b64_json`은 decode하고, `url` 응답은 다시 다운로드한다.
- 생성 이미지는 `data/images/{YYYYMMDDTHHMMSSffffffZ}.jpg`에 저장하고 `/images/{YYYYMMDDTHHMMSSffffffZ}.jpg`로 서빙한다.

## Response

```json
{
  "image_url": "https://image-api.example.com/images/20260605T154512345678Z.jpg",
  "markdown": "![generated poster](https://image-api.example.com/images/20260605T154512345678Z.jpg)",
  "image_id": "20260605T154512345678Z",
  "input_image_count": 1,
  "model": "gpt-image-2",
  "size": "1024x1536",
  "quality": "low",
  "output_format": "jpeg"
}
```

## Local run

```bash
cp .env.image-bridge.example .env.image-bridge
# Fill IMAGE_BRIDGE_OPENAI_API_KEY and IMAGE_BRIDGE_TOKEN

docker compose --env-file .env.image-bridge -f docker-compose.image-bridge.yml up --build image-bridge
```

Health check:

```bash
curl http://localhost:8080/health
```

Generate test:

```bash
curl -X POST http://localhost:8080/generate \
  -H "Authorization: Bearer $IMAGE_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Create one portrait Korean travel poster draft for a quiet coastal walking tour.","size":"1024x1536","quality":"low"}'
```

## Cloudflare Tunnel

### Quick test tunnel

For temporary testing, run:

```bash
cloudflared tunnel --url http://localhost:8080
```

Use the generated `https://*.trycloudflare.com` URL as `IMAGE_BRIDGE_PUBLIC_BASE_URL` and as the Ennoia connector base URL. This is convenient for tests but not intended as a stable production URL.

### Stable Docker tunnel

1. In Cloudflare Zero Trust, create a Tunnel.
2. Add a public hostname, for example `image-api.example.com`.
3. Route it to the local service URL inside Docker:

```text
http://image-bridge:8080
```

4. Copy the tunnel token and set it locally:

```bash
export CLOUDFLARE_TUNNEL_TOKEN="..."
```

5. Start both services:

```bash
docker compose --env-file .env.image-bridge -f docker-compose.image-bridge.yml --profile tunnel up -d --build
```

6. Set this in `.env.image-bridge` so returned URLs are public:

```env
IMAGE_BRIDGE_PUBLIC_BASE_URL=https://image-api.example.com
```

Restart the bridge after changing `.env.image-bridge`.

## Ennoia connector notes

- Method: `POST`
- URL: `https://image-api.example.com/generate`
- Header: `Authorization: Bearer <IMAGE_BRIDGE_TOKEN>`
- Body: prompt, optional `input_image_urls`, `size`, `quality`, `output_format`
- Display: render `markdown` or use `image_url` in Markdown.
