from __future__ import annotations

import httpx
import pytest
import re
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import (
    NotionPageCreateRequest,
    _build_notion_markdown,
    _normalize_ennoia_markdown,
    _post_notion_page,
    _server_created_at,
    app,
)


class FakeNotionClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return httpx.Response(200, json={"id": "abc-def", "url": "https://www.notion.so/test-page"})


def test_health_endpoint_available():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["notion_version"] == "2026-03-11"


def test_rejects_unsupported_proposal_type():
    with pytest.raises(ValueError):
        NotionPageCreateRequest(title="title", markdown="# body", proposal_type="unknown")



def test_normalizes_html_buttons_and_images_to_markdown():
    markdown = """
<div>
  <a href="https://example.com" target="_blank">Notion에서 열기</a>
  <img src="https://example.com/a.jpg" alt="대표 이미지" />
</div>
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert "[Notion에서 열기](https://example.com)" in normalized
    assert "![대표 이미지](https://example.com/a.jpg)" in normalized
    assert "<div" not in normalized
    assert "<img" not in normalized


def test_normalizes_html_tables_to_notion_tables():
    markdown = """
<table style="width:100%">
  <tr><th>구분</th><th>내용</th></tr>
  <tr><td>핵심 메시지</td><td>숲 | 호수 연계</td></tr>
  <tr><td>CTA</td><td><a href="https://example.com">자세히 보기</a></td></tr>
</table>
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert '<table fit-page-width="true" header-row="true">' in normalized
    assert "<td>구분</td>" in normalized
    assert "<td>내용</td>" in normalized
    assert "<td>핵심 메시지</td>" in normalized
    assert "<td>숲 | 호수 연계</td>" in normalized
    assert "<td>[자세히 보기](https://example.com)</td>" in normalized
    assert 'style="width:100%"' not in normalized
    assert "<th" not in normalized


def test_extracts_html_image_tables_to_image_blocks():
    markdown = """
<table>
  <tr>
    <td><a href="https://example.com/a.jpg"><img src="https://example.com/a.jpg" alt="이미지 1" /></a></td>
    <td><a href="https://example.com/b.jpg"><img src="https://example.com/b.jpg" alt="이미지 2" /></a></td>
    <td><a href="https://example.com/c.jpg"><img src="https://example.com/c.jpg" alt="이미지 3" /></a></td>
  </tr>
</table>
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert "![이미지 1](https://example.com/a.jpg)" in normalized
    assert "![이미지 2](https://example.com/b.jpg)" in normalized
    assert "![이미지 3](https://example.com/c.jpg)" in normalized
    assert "<table" not in normalized
    assert "<td>" not in normalized


def test_normalizes_pipe_tables_to_notion_tables():
    markdown = """
| 번호 | 광고 카피 |
| --- | --- |
| 1 | 숲에서 쉬는 여행 |
| 2 | 청풍호 \| 호반 감성 |
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert '<table fit-page-width="true" header-row="true">' in normalized
    assert "<td>번호</td>" in normalized
    assert "<td>광고 카피</td>" in normalized
    assert "<td>숲에서 쉬는 여행</td>" in normalized
    assert "<td>청풍호 | 호반 감성</td>" in normalized
    assert "| --- | --- |" not in normalized


def test_extracts_pipe_image_tables_to_image_blocks():
    markdown = """
| 이미지 1 | 이미지 2 | 이미지 3 |
| --- | --- | --- |
| ![보름달](https://example.com/a.jpg) | ![야경](https://example.com/b.jpg) | ![전망](https://example.com/c.jpg) |
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert "![보름달](https://example.com/a.jpg)" in normalized
    assert "![야경](https://example.com/b.jpg)" in normalized
    assert "![전망](https://example.com/c.jpg)" in normalized
    assert "<table" not in normalized
    assert "| 이미지 1 | 이미지 2 | 이미지 3 |" not in normalized


def test_keeps_multiline_table_cell_bullets_inside_the_cell():
    markdown = """
| 항목 | 내용 |
| --- | --- |
| 세일즈 포인트 | - 무료 입장 명소 위주로 구성되어 비용 부담이 적습니다. |
- 인스타그램 포토존으로 알려진 보름달 조형물 등이 포함되어 있습니다.
- 부산항대교 야경과 도심 조망이 가능한 명소들로 동선이 구성되어 있습니다.
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert '<table fit-page-width="true" header-row="true">' in normalized
    assert (
        "<td>- 무료 입장 명소 위주로 구성되어 비용 부담이 적습니다.<br />"
        "- 인스타그램 포토존으로 알려진 보름달 조형물 등이 포함되어 있습니다.<br />"
        "- 부산항대교 야경과 도심 조망이 가능한 명소들로 동선이 구성되어 있습니다.</td>"
    ) in normalized
    assert normalized.count("<br />- ") == 2


def test_keeps_multiline_html_table_cells_inside_the_cell():
    markdown = """
<table>
  <tr><th>항목</th><th>내용</th></tr>
  <tr><td>판매/홍보 문구</td><td>Headline: 반려동물과 함께 걷는 부산<br>Subcopy: 해안 산책 코스입니다.<br>CTA: 코스 확인하기</td></tr>
</table>
"""

    normalized = _normalize_ennoia_markdown(markdown)

    assert '<table fit-page-width="true" header-row="true">' in normalized
    assert "<td>판매/홍보 문구</td>" in normalized
    assert (
        "<td>Headline: 반려동물과 함께 걷는 부산<br />"
        "Subcopy: 해안 산책 코스입니다.<br />"
        "CTA: 코스 확인하기</td>"
    ) in normalized


def test_build_notion_markdown_sets_requested_title_and_demotes_existing_h1():
    result = _build_notion_markdown(title="서귀포 상품 제안서", markdown="# 여행 상품 추천\n\n## 1. 상품")

    assert result.startswith("# 서귀포 상품 제안서\n\n## 여행 상품 추천")
    assert "\n\n### 1. 상품" in result


def test_server_created_at_uses_korean_datetime_format():
    value = _server_created_at()

    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", value)


def test_build_notion_markdown_prepends_created_at_once():
    result = _build_notion_markdown(
        title="제천 마케팅",
        markdown="## 마케팅 광고 패키지",
        created_at="2026-06-08 21:26:51",
    )

    assert "작성일시: 2026-06-08 21:26:51" in result
    assert result.count("작성일시:") == 1

    already_has_timestamp = _build_notion_markdown(
        title="제천 마케팅",
        markdown="작성일시: 2026-06-08 21:26:51\n\n## 마케팅 광고 패키지",
        created_at="2026-06-08 21:30:00",
    )

    assert already_has_timestamp.count("작성일시:") == 1
    assert "2026-06-08 21:30:00" not in already_has_timestamp


def test_post_notion_page_uses_markdown_body_and_headers():
    client = FakeNotionClient()

    _post_notion_page(
        client=client,
        api_key="secret-test",
        parent_page_id="parent-id",
        notion_version="2026-03-11",
        markdown="# Page",
    )

    call = client.calls[0]
    assert call["url"] == "https://api.notion.com/v1/pages"
    assert call["headers"]["Authorization"] == "Bearer secret-test"
    assert call["headers"]["Notion-Version"] == "2026-03-11"
    assert call["json"] == {"parent": {"page_id": "parent-id"}, "markdown": "# Page"}


def test_create_page_requires_bearer_token_when_configured(monkeypatch):
    monkeypatch.setattr(main_module.settings, "notion_bridge_token", "expected")
    client = TestClient(app)

    response = client.post(
        "/notion/pages",
        json={"title": "title", "markdown": "# body", "proposal_type": "travel_recommendation"},
    )

    assert response.status_code == 401
