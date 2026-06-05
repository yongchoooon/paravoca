from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.main import ImageGenerateRequest, app, _image_bytes_from_openai_response


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
