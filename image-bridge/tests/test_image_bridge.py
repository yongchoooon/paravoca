from __future__ import annotations

import base64
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import (
    ImageGenerateRequest,
    _call_image_edits,
    _call_image_generations,
    _image_bytes_from_openai_response,
    _new_timestamped_image_path,
    app,
)


class FakeOpenAIClient:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return object()


def test_health_endpoint_available():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["default_output_format"] == "jpeg"


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


def test_rejects_unsupported_output_format():
    with pytest.raises(ValueError):
        ImageGenerateRequest(prompt="poster prompt", output_format="bmp")


def test_decodes_openai_b64_json_response():
    expected = b"png-bytes"
    payload = {"data": [{"b64_json": base64.b64encode(expected).decode("ascii")}]} 
    assert _image_bytes_from_openai_response(None, payload) == expected


def test_new_image_path_uses_kst_timestamp_id_and_jpg_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "storage_dir", tmp_path)

    image_id, image_path = _new_timestamped_image_path()

    assert re.fullmatch(r"\d{8}T\d{12}KST", image_id)
    assert image_path == tmp_path / f"{image_id}.jpg"


def test_new_image_path_uses_png_extension_when_requested(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "storage_dir", tmp_path)

    image_id, image_path = _new_timestamped_image_path("png")

    assert image_path == tmp_path / f"{image_id}.png"


def test_new_image_path_adds_suffix_on_timestamp_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "storage_dir", tmp_path)

    fixed_now = datetime(2026, 6, 5, 15, 45, 12, 345678, tzinfo=ZoneInfo("Asia/Seoul"))

    class FixedDatetime:
        @classmethod
        def now(cls, tz):
            assert tz == ZoneInfo("Asia/Seoul")
            return fixed_now

    monkeypatch.setattr(main_module, "datetime", FixedDatetime)

    first_id, first_path = _new_timestamped_image_path()
    first_path.write_bytes(b"existing")
    second_id, second_path = _new_timestamped_image_path()

    assert first_id == "20260605T154512345678KST"
    assert second_id == "20260605T154512345678KST-2"
    assert second_path == tmp_path / "20260605T154512345678KST-2.jpg"
    assert not second_path.exists()


def test_generation_request_asks_openai_for_jpeg_output():
    client = FakeOpenAIClient()

    _call_image_generations(
        client=client,
        api_key="sk-test",
        model="gpt-image-2",
        prompt="poster prompt",
        size="1024x1024",
        quality="low",
        output_format="jpeg",
    )

    assert client.calls[0]["url"] == "https://api.openai.com/v1/images/generations"
    assert client.calls[0]["json"]["output_format"] == "jpeg"


def test_edit_request_asks_openai_for_jpeg_output(monkeypatch):
    client = FakeOpenAIClient()
    monkeypatch.setattr(
        main_module,
        "_download_input_images",
        lambda urls: [{"extension": "jpg", "bytes": b"image", "content_type": "image/jpeg"}],
    )

    _call_image_edits(
        client=client,
        api_key="sk-test",
        model="gpt-image-2",
        prompt="poster prompt",
        size="1024x1536",
        quality="low",
        output_format="jpeg",
        input_image_urls=["https://example.com/reference.jpg"],
    )

    assert client.calls[0]["url"] == "https://api.openai.com/v1/images/edits"
    assert client.calls[0]["data"]["output_format"] == "jpeg"
