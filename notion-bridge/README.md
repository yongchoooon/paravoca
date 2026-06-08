# PARAVOCA Ennoia Notion Bridge

Ennoia API Connector에서 PARAVOCA 최종 Markdown을 보내면, 이 FastAPI 컨테이너가 Notion API로 페이지를 생성하고 Notion URL을 반환한다.

## Request

```http
POST /notion/pages
Authorization: Bearer <NOTION_BRIDGE_TOKEN>
Content-Type: application/json
```

```json
{
  "title": "서귀포 동선 중심 여행상품 제안서",
  "markdown": "# 여행 상품 추천\n\n...",
  "proposal_type": "travel_recommendation"
}
```

`proposal_type` 허용값:

- `travel_recommendation`
- `product_planner`
- `operations`
- `marketing`
- `poster_result`

## Behavior

- `markdown`은 Notion의 Markdown page 생성 API로 전달한다.
- 서버는 입력 Markdown 앞에 `# {title}`을 붙이고, 기존 heading은 한 단계 낮춰 Notion page title이 요청 title로 잡히게 한다.
- Ennoia 출력에 포함된 HTML 버튼과 이미지 태그는 Markdown 링크와 이미지 문법으로 정규화한다.
- Notion API key는 서버 환경변수에만 둔다. Ennoia에는 `NOTION_BRIDGE_TOKEN`만 넣는다.

## Response

```json
{
  "page_url": "https://www.notion.so/...",
  "markdown": "[Notion에서 열기](https://www.notion.so/...)",
  "page_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "title": "서귀포 동선 중심 여행상품 제안서",
  "proposal_type": "travel_recommendation",
  "latency_ms": 1200
}
```

## Notion setup

1. Notion Integration을 생성한다.
2. Integration secret을 `NOTION_API_KEY`로 저장한다.
3. PARAVOCA 문서를 저장할 상위 Notion 페이지를 만든다.
4. 그 페이지에서 Integration을 초대한다.
5. 상위 페이지 ID를 `NOTION_PARENT_PAGE_ID`로 저장한다.

## Local run

```bash
cp .env.notion-bridge.example .env.notion-bridge
# Fill NOTION_API_KEY, NOTION_PARENT_PAGE_ID, NOTION_BRIDGE_TOKEN

docker compose --env-file .env.notion-bridge -f docker-compose.notion-bridge.yml up --build notion-bridge
```

Health check:

```bash
curl http://localhost:8081/health
```

Create page test:

```bash
curl -X POST http://localhost:8081/notion/pages \
  -H "Authorization: Bearer $NOTION_BRIDGE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"PARAVOCA 테스트 문서","markdown":"# 테스트\n\n본문입니다.","proposal_type":"travel_recommendation"}'
```

## Cloudflare Tunnel

### Quick test tunnel

```bash
cloudflared tunnel --url http://localhost:8081
```

### Stable Docker tunnel

1. In Cloudflare Zero Trust, create a Tunnel.
2. Add a public hostname, for example `notion-api.example.com`.
3. Route it to the local service URL inside Docker:

```text
http://notion-bridge:8081
```

4. Copy the tunnel token and set it locally:

```bash
export CLOUDFLARE_TUNNEL_TOKEN="..."
```

5. Start both services:

```bash
docker compose --env-file .env.notion-bridge -f docker-compose.notion-bridge.yml --profile tunnel up -d --build
```

## Ennoia connector notes

- Method: `POST`
- URL: `https://notion-api.example.com/notion/pages`
- Header: `Authorization: Bearer <NOTION_BRIDGE_TOKEN>`
- Body: `title`, `markdown`, `proposal_type`
- Display: render `markdown` or link to `page_url`.

Body schema:

```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "description": "Notion page title."
    },
    "markdown": {
      "type": "string",
      "description": "Final PARAVOCA proposal markdown."
    },
    "proposal_type": {
      "type": "string",
      "description": "One of: travel_recommendation, product_planner, operations, marketing, poster_result."
    }
  },
  "required": [
    "title",
    "markdown",
    "proposal_type"
  ],
  "additionalProperties": false
}
```
