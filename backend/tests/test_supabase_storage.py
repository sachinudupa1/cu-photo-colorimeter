from __future__ import annotations

import httpx
import pytest

from backend.app import storage_service, settings


@pytest.fixture
def configured_storage(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_BUCKET_NAME", "cu-photo-images")
    monkeypatch.setattr(settings, "SUPABASE_SECRET_KEY", "test_secret_key_not_real")


def test_upload_uses_secret_key_only_in_apikey_header(monkeypatch, configured_storage):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["apikey"] = request.headers.get("apikey")
        captured["authorization"] = request.headers.get("authorization")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        return httpx.Response(200, json={"Key": "training/abc/photo.jpg"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(storage_service, "_new_client", lambda: httpx.Client(transport=transport))
    storage_service.storage_bucket().blob("training/abc/photo.jpg").upload_from_string(
        b"image-bytes", content_type="image/jpeg"
    )

    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.supabase.co/storage/v1/object/cu-photo-images/training/abc/photo.jpg"
    assert captured["apikey"] == "test_secret_key_not_real"
    assert captured["authorization"] is None
    assert captured["content_type"] == "image/jpeg"
    assert captured["body"] == b"image-bytes"


def test_download_returns_private_object_bytes(monkeypatch, configured_storage):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers.get("apikey") == "test_secret_key_not_real"
        return httpx.Response(200, content=b"private-photo")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(storage_service, "_new_client", lambda: httpx.Client(transport=transport))
    result = storage_service.storage_bucket().blob("training/a/photo.png").download_as_bytes()
    assert result == b"private-photo"


def test_exists_returns_false_for_missing_object(monkeypatch, configured_storage):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Object not found")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(storage_service, "_new_client", lambda: httpx.Client(transport=transport))
    assert storage_service.storage_bucket().blob("training/missing.jpg").exists() is False


def test_exists_returns_false_for_missing_object_with_empty_400(monkeypatch, configured_storage):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(400)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(storage_service, "_new_client", lambda: httpx.Client(transport=transport))
    assert storage_service.storage_bucket().blob("models/active.json").exists() is False


def test_delete_calls_storage_delete_endpoint(monkeypatch, configured_storage):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"message": "deleted"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(storage_service, "_new_client", lambda: httpx.Client(transport=transport))
    storage_service.storage_bucket().blob("testing/a/photo.jpg").delete()
    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/storage/v1/object/cu-photo-images/testing/a/photo.jpg")


def test_storage_config_rejects_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_BUCKET_NAME", "cu-photo-images")
    monkeypatch.setattr(settings, "SUPABASE_SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SUPABASE_SECRET_KEY"):
        settings.validate_supabase_config()
