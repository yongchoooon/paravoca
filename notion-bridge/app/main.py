from __future__ import annotations

import html
import re
import time
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    notion_api_key: str = ""
    notion_parent_page_id: str = ""
    notion_version: str = "2026-03-11"
    notion_bridge_token: str = ""
    notion_bridge_request_timeout_seconds: float = 30.0
    notion_bridge_max_title_chars: int = 120
    notion_bridge_max_markdown_chars: int = 80000


settings = Settings()
app = FastAPI(title="PARAVOCA Ennoia Notion Bridge", version="0.1.0")

_ALLOWED_PROPOSAL_TYPES = {
    "travel_recommendation",
    "product_planner",
    "operations",
    "marketing",
    "poster_result",
}


class NotionPageCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    markdown: str = Field(..., min_length=1)
    proposal_type: str = Field(..., min_length=1)
    created_at: str = ""

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("title is required")
        if len(cleaned) > settings.notion_bridge_max_title_chars:
            raise ValueError(f"title must be <= {settings.notion_bridge_max_title_chars} characters")
        return cleaned

    @field_validator("markdown")
    @classmethod
    def validate_markdown(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("markdown is required")
        if len(cleaned) > settings.notion_bridge_max_markdown_chars:
            raise ValueError(f"markdown must be <= {settings.notion_bridge_max_markdown_chars} characters")
        return cleaned

    @field_validator("proposal_type")
    @classmethod
    def validate_proposal_type(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in _ALLOWED_PROPOSAL_TYPES:
            raise ValueError(f"proposal_type must be one of {sorted(_ALLOWED_PROPOSAL_TYPES)}")
        return cleaned

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        return " ".join(value.strip().split())


class NotionPageCreateResponse(BaseModel):
    page_url: str
    markdown: str
    page_id: str
    title: str
    proposal_type: str
    latency_ms: int


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    expected = settings.notion_bridge_token.strip()
    if not expected:
        return
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[len(prefix) :].strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "auth_configured": bool(settings.notion_bridge_token.strip()),
        "notion_configured": bool(settings.notion_api_key.strip() and settings.notion_parent_page_id.strip()),
        "notion_version": settings.notion_version,
        "max_markdown_chars": settings.notion_bridge_max_markdown_chars,
    }


@app.post("/notion/pages", response_model=NotionPageCreateResponse, dependencies=[Depends(require_bearer_token)])
def create_notion_page(payload: NotionPageCreateRequest) -> NotionPageCreateResponse:
    api_key = settings.notion_api_key.strip()
    parent_page_id = settings.notion_parent_page_id.strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="NOTION_API_KEY is not configured")
    if not parent_page_id:
        raise HTTPException(status_code=500, detail="NOTION_PARENT_PAGE_ID is not configured")

    started = time.perf_counter()
    notion_markdown = _build_notion_markdown(title=payload.title, markdown=payload.markdown, created_at=payload.created_at)

    with httpx.Client(timeout=settings.notion_bridge_request_timeout_seconds, follow_redirects=True) as client:
        response = _post_notion_page(
            client=client,
            api_key=api_key,
            parent_page_id=parent_page_id,
            notion_version=settings.notion_version,
            markdown=notion_markdown,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "reason": "notion_page_create_failed",
                "status_code": response.status_code,
                "response": _safe_response_json(response),
            },
        )

    response_payload = response.json()
    page_url = response_payload.get("url")
    page_id = response_payload.get("id", "")
    if not isinstance(page_url, str) or not page_url:
        page_url = _fallback_notion_page_url(page_id)
    if not page_url:
        raise HTTPException(status_code=502, detail={"reason": "notion_response_missing_page_url"})

    latency_ms = int((time.perf_counter() - started) * 1000)
    return NotionPageCreateResponse(
        page_url=page_url,
        markdown=f"[Notion에서 열기]({page_url})",
        page_id=page_id,
        title=payload.title,
        proposal_type=payload.proposal_type,
        latency_ms=latency_ms,
    )


def _post_notion_page(
    *,
    client: httpx.Client,
    api_key: str,
    parent_page_id: str,
    notion_version: str,
    markdown: str,
) -> httpx.Response:
    return client.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": notion_version,
            "Content-Type": "application/json",
        },
        json={
            "parent": {"page_id": parent_page_id},
            "markdown": markdown,
        },
    )


def _build_notion_markdown(*, title: str, markdown: str, created_at: str = "") -> str:
    markdown_with_timestamp = _prepend_created_at(markdown=markdown, created_at=created_at)
    normalized = _normalize_ennoia_markdown(markdown_with_timestamp)
    demoted = _demote_headings(normalized)
    return f"# {title}\n\n{demoted}".strip()


def _prepend_created_at(*, markdown: str, created_at: str) -> str:
    cleaned = created_at.strip()
    if not cleaned or markdown.lstrip().startswith("작성일시:"):
        return markdown
    return f"작성일시: {cleaned}\n\n{markdown}"


def _normalize_ennoia_markdown(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*img\b[^>]*>", _replace_img_tag, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<\s*a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)<\s*/\s*a\s*>", _replace_anchor_tag, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<\s*table\b[^>]*>.*?<\s*/\s*table\s*>", _replace_table_tag, text, flags=re.IGNORECASE | re.DOTALL)
    text = _replace_pipe_tables(text)
    text = re.sub(r"<\s*/?\s*div\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", _strip_unsupported_html_tag, text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _replace_table_tag(match: re.Match[str]) -> str:
    table_html = match.group(0)
    row_matches = re.findall(r"<\s*tr\b[^>]*>(.*?)<\s*/\s*tr\s*>", table_html, flags=re.IGNORECASE | re.DOTALL)
    rows: list[list[str]] = []
    for row_html in row_matches:
        cell_matches = re.findall(r"<\s*(?:td|th)\b[^>]*>(.*?)<\s*/\s*(?:td|th)\s*>", row_html, flags=re.IGNORECASE | re.DOTALL)
        cells = [_normalize_table_cell(cell) for cell in cell_matches]
        if cells:
            rows.append(cells)

    if not rows:
        return _strip_tags(table_html)

    return "\n\n" + _build_notion_table(rows, header_row=True) + "\n\n"


def _replace_pipe_tables(markdown: str) -> str:
    lines = markdown.split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        if index + 1 < len(lines) and _is_pipe_table_header(lines[index], lines[index + 1]):
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and _is_pipe_table_row(lines[index]):
                table_lines.append(lines[index])
                index += 1

            rows = [_parse_pipe_table_row(line) for line in table_lines[:1] + table_lines[2:]]
            output.append(_build_notion_table(rows, header_row=True))
            continue

        output.append(lines[index])
        index += 1

    return "\n".join(output)


def _is_pipe_table_header(header_line: str, separator_line: str) -> bool:
    if not _is_pipe_table_row(header_line) or not _is_pipe_table_row(separator_line):
        return False
    cells = _parse_pipe_table_row(separator_line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _is_pipe_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _parse_pipe_table_row(line: str) -> list[str]:
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return [cell.replace("\\|", "|").strip() for cell in cells]


def _build_notion_table(rows: list[list[str]], *, header_row: bool) -> str:
    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    lines = [f'<table fit-page-width="true" header-row="{str(header_row).lower()}">']
    for row in normalized_rows:
        lines.append("\t<tr>")
        for cell in row:
            lines.append(f"\t\t<td>{_escape_notion_table_cell(cell)}</td>")
        lines.append("\t</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _normalize_table_cell(cell_html: str) -> str:
    cell = re.sub(r"<\s*br\s*/?\s*>", " ", cell_html, flags=re.IGNORECASE)
    cell = _strip_tags(cell)
    cell = html.unescape(cell)
    cell = re.sub(r"\s+", " ", cell).strip()
    return cell


def _escape_notion_table_cell(cell: str) -> str:
    return html.escape(cell, quote=False)


def _strip_unsupported_html_tag(match: re.Match[str]) -> str:
    tag = match.group(0)
    tag_name_match = re.match(r"<\s*/?\s*([a-zA-Z0-9_-]+)", tag)
    if not tag_name_match:
        return ""
    tag_name = tag_name_match.group(1).lower()
    if tag_name in {"table", "tr", "td", "colgroup", "col"}:
        return tag
    return ""


def _replace_anchor_tag(match: re.Match[str]) -> str:
    url = html.unescape(match.group(1).strip())
    label = _strip_tags(match.group(2)).strip()
    label = re.sub(r"\s+", " ", html.unescape(label))
    if not label:
        label = url
    return f"[{label}]({url})"


def _replace_img_tag(match: re.Match[str]) -> str:
    tag = match.group(0)
    src = _extract_attr(tag, "src")
    if not src:
        return ""
    alt = _extract_attr(tag, "alt") or "image"
    return f"![{html.unescape(alt)}]({html.unescape(src)})"


def _extract_attr(tag: str, attr: str) -> str | None:
    pattern = rf"\b{re.escape(attr)}=[\"']([^\"']+)[\"']"
    match = re.search(pattern, tag, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


def _demote_headings(markdown: str) -> str:
    def replace(match: re.Match[str]) -> str:
        hashes = match.group(1)
        text = match.group(2)
        if len(hashes) >= 6:
            return match.group(0)
        return f"{hashes}# {text}"

    return re.sub(r"^(#{1,5})\s+(.+)$", replace, markdown, flags=re.MULTILINE)


def _fallback_notion_page_url(page_id: str) -> str:
    compact = page_id.replace("-", "").strip()
    if not compact:
        return ""
    return f"https://www.notion.so/{compact}"


def _safe_response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:1000]}
