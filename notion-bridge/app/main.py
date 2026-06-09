from __future__ import annotations

import html
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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
    notion_bridge_max_markdown_chars: int = 150000
    notion_bridge_max_notion_markdown_bytes: int = 475000


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
        markdown_size = len(cleaned.encode("utf-8"))
        if markdown_size > settings.notion_bridge_max_notion_markdown_bytes:
            raise ValueError(
                f"markdown must be <= {settings.notion_bridge_max_notion_markdown_bytes} bytes when encoded as UTF-8"
            )
        return cleaned

    @field_validator("proposal_type")
    @classmethod
    def validate_proposal_type(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in _ALLOWED_PROPOSAL_TYPES:
            raise ValueError(f"proposal_type must be one of {sorted(_ALLOWED_PROPOSAL_TYPES)}")
        return cleaned



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
        "max_notion_markdown_bytes": settings.notion_bridge_max_notion_markdown_bytes,
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
    notion_markdown = _build_notion_markdown(title=payload.title, markdown=payload.markdown, created_at=_server_created_at())
    notion_markdown_size = len(notion_markdown.encode("utf-8"))
    if notion_markdown_size > settings.notion_bridge_max_notion_markdown_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "reason": "notion_markdown_too_large_after_normalization",
                "max_bytes": settings.notion_bridge_max_notion_markdown_bytes,
                "actual_bytes": notion_markdown_size,
            },
        )

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


def _server_created_at() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")


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
    text = re.sub(r"<\s*br\s*/?\s*>", "<br />", text, flags=re.IGNORECASE)
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

    image_gallery = _build_image_gallery(rows)
    if image_gallery:
        return "\n\n" + image_gallery + "\n\n"

    return "\n\n" + _build_notion_table(rows, header_row=True) + "\n\n"


def _replace_pipe_tables(markdown: str) -> str:
    lines = markdown.split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        if index + 1 < len(lines) and _is_pipe_table_header(lines[index], lines[index + 1]):
            header_line = lines[index]
            separator_line = lines[index + 1]
            rows = [_parse_pipe_table_row(header_line)]
            index += 2
            current_row: list[str] | None = None

            while index < len(lines):
                line = lines[index]
                if _is_pipe_table_row(line):
                    if current_row is not None:
                        rows.append(current_row)
                    current_row = _parse_pipe_table_row(line)
                    index += 1
                    continue

                if current_row is not None and _is_table_cell_continuation(line):
                    current_row[-1] = _append_cell_continuation(current_row[-1], line)
                    index += 1
                    continue

                break

            if current_row is not None:
                rows.append(current_row)

            if len(rows) == 1:
                output.append(header_line)
                output.append(separator_line)
                continue

            image_gallery = _build_image_gallery(rows)
            if image_gallery:
                output.append(image_gallery)
            else:
                output.append(_build_notion_table(rows, header_row=True))
            continue

        output.append(lines[index])
        index += 1

    return "\n".join(output)


def _is_table_cell_continuation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if _is_pipe_table_row(stripped):
        return False
    return bool(
        re.match(r"^[-*]\s+\S+", stripped)
        or re.match(r"^\d+[.)]\s+\S+", stripped)
        or line.startswith((" ", "\t"))
    )


def _append_cell_continuation(cell: str, line: str) -> str:
    continuation = line.strip()
    continuation = continuation.rstrip("|").strip()
    if not continuation:
        return cell
    if cell:
        return f"{cell}<br>{continuation}"
    return continuation


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


def _build_image_gallery(rows: list[list[str]]) -> str:
    images, has_non_image_content = _collect_table_images(rows)
    if (has_non_image_content or len(images) < 2) and len(rows) > 1:
        images, has_non_image_content = _collect_table_images(rows[1:])

    if has_non_image_content or len(images) < 2:
        return ""

    return "\n\n".join(f"![{alt or 'image'}]({url})" for alt, url in images[:6])


def _collect_table_images(rows: list[list[str]]) -> tuple[list[tuple[str, str]], bool]:
    images: list[tuple[str, str]] = []
    has_non_image_content = False
    for row in rows:
        for cell in row:
            cleaned = cell.strip()
            if not cleaned:
                continue
            cell_images = _extract_cell_images(cleaned)
            remaining = cleaned
            for image_markdown, _, _ in cell_images:
                remaining = remaining.replace(image_markdown, "")
            remaining = re.sub(r"[\s|/·,]+", "", remaining)
            if cell_images and not remaining:
                images.extend((alt, url) for _, alt, url in cell_images)
            else:
                has_non_image_content = True

    return images, has_non_image_content


def _extract_cell_images(cell: str) -> list[tuple[str, str, str]]:
    images: list[tuple[str, str, str]] = []

    linked_image_pattern = re.compile(r"\[!\[([^\]]*)\]\(([^)\s]+)\)\]\(([^)\s]+)\)")
    consumed_spans: list[tuple[int, int]] = []
    for match in linked_image_pattern.finditer(cell):
        image_url = match.group(2).strip()
        link_url = match.group(3).strip()
        images.append((match.group(0), match.group(1).strip(), link_url or image_url))
        consumed_spans.append(match.span())

    plain_image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
    for match in plain_image_pattern.finditer(cell):
        if any(start <= match.start() and match.end() <= end for start, end in consumed_spans):
            continue
        images.append((match.group(0), match.group(1).strip(), match.group(2).strip()))

    return images


def _normalize_table_cell(cell_html: str) -> str:
    line_break_token = "___PARAVOCA_BR___"
    cell = re.sub(r"<\s*br\s*/?\s*>", line_break_token, cell_html, flags=re.IGNORECASE)
    cell = _strip_tags(cell)
    cell = html.unescape(cell)
    parts = [re.sub(r"\s+", " ", part).strip() for part in cell.split(line_break_token)]
    cell = "<br />".join(part for part in parts if part)
    return cell


def _escape_notion_table_cell(cell: str) -> str:
    parts = re.split(r"<br\s*/?>", cell)
    return "<br />".join(html.escape(part, quote=False) for part in parts)


def _strip_unsupported_html_tag(match: re.Match[str]) -> str:
    tag = match.group(0)
    tag_name_match = re.match(r"<\s*/?\s*([a-zA-Z0-9_-]+)", tag)
    if not tag_name_match:
        return ""
    tag_name = tag_name_match.group(1).lower()
    if tag_name in {"table", "tr", "td", "br", "colgroup", "col"}:
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
