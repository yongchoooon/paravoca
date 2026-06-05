from __future__ import annotations

import base64
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import ImageGenerateRequest, app, _image_bytes_from_openai_response, _new_timestamped_image_path


def test_health_endpoint_available():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rejects_more_than_three_input_images():
    with pytest.raises(ValueError):
        ImageGenerateRequest(
            prompt="poster prompt",
            input_image_urls=[
                "https://example.com/a.png",
                "https://example.com/b.png",
                "https://example.com/c.png",
                "https://example.com/d.png",
            ],
        )


def test_rejects_non_http_input_image_url():
    with pytest.raises(ValueError):
        ImageGenerateRequest(prompt="poster prompt", input_image_urls=["file:///tmp/a.png"])


def test_decodes_openai_b64_json_response():
    expected = b"png-bytes"
    payload = {"data": [{"b64_json": base64.b64encode(expected).decode("ascii")}]} 
    assert _image_bytes_from_openai_response(None, payload) == expected


def test_new_image_path_uses_utc_timestamp_id(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "storage_dir", tmp_path)

    image_id, image_path = _new_timestamped_image_path()

    assert re.fullmatch(r"\d{8}T\d{12}Z", image_id)
    assert image_path == tmp_path / f"{image_id}.png"


def test_new_image_path_adds_suffix_on_timestamp_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "storage_dir", tmp_path)

    fixed_now = datetime(2026, 6, 5, 15, 45, 12, 345678, tzinfo=UTC)

    class FixedDatetime:
        @classmethod
        def now(cls, tz):
            assert tz is UTC
            return fixed_now

    monkeypatch.setattr(main_module, "datetime", FixedDatetime)

    first_id, first_path = _new_timestamped_image_path()
    first_path.write_bytes(b"existing")
    second_id, second_path = _new_timestamped_image_path()

    assert first_id == "20260605T154512345678Z"
    assert second_id == "20260605T154512345678Z-2"
    assert second_path == tmp_path / "20260605T154512345678Z-2.png"
    assert not second_path.exists()
