from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from backend.app.firestore_rest import FirestoreRestClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)


def test_document_set_get_round_trip_encodes_nested_data_and_timestamps():
    stored = {}

    def handler(method, url, kwargs):
        if method == "GET":
            return FakeResponse(200, {"fields": stored}) if stored else FakeResponse(404)
        if method == "PATCH":
            stored.update(kwargs["json"]["fields"])
            return FakeResponse(200, {"fields": stored})
        raise AssertionError(method)

    session = FakeSession(handler)
    client = FirestoreRestClient("test-project", session=session)
    ref = client.collection("training_data").document("abc")
    moment = datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc)
    ref.set({"sample_id": "S-1", "verified": True, "concentration": 1.25, "created_at": moment, "photos": [{"storage_path": "training/a.jpg"}]})
    snapshot = ref.get()

    assert snapshot.exists is True
    data = snapshot.to_dict()
    assert data["sample_id"] == "S-1"
    assert data["verified"] is True
    assert data["concentration"] == 1.25
    assert data["created_at"] == moment
    assert data["photos"] == [{"storage_path": "training/a.jpg"}]


def test_get_returns_nonexistent_snapshot_on_404():
    session = FakeSession(lambda *_: FakeResponse(404))
    snapshot = FirestoreRestClient("test-project", session=session).collection("testing_data").document("missing").get()
    assert snapshot.exists is False
    assert snapshot.to_dict() is None


def test_update_uses_update_mask_and_exists_precondition():
    captured = {}

    def handler(method, url, kwargs):
        captured.update(method=method, url=url, params=kwargs.get("params"), body=kwargs.get("json"))
        return FakeResponse(200, {})

    session = FakeSession(handler)
    FirestoreRestClient("test-project", session=session).collection("testing_data").document("t1").update({"verified": True, "note": None})
    params = captured["params"]
    assert ("updateMask.fieldPaths", "verified") in params
    assert ("updateMask.fieldPaths", "note") in params
    assert ("currentDocument.exists", "true") in params


def test_where_and_limit_use_firestore_run_query():
    captured = {}

    def handler(method, url, kwargs):
        captured.update(method=method, url=url, body=kwargs.get("json"))
        return FakeResponse(200, [])

    session = FakeSession(handler)
    list(FirestoreRestClient("test-project", session=session).collection("training_data").where("sample_id", "==", "S-1").limit(1).stream())
    assert captured["method"] == "POST"
    assert captured["url"].endswith("documents:runQuery")
    query = captured["body"]["structuredQuery"]
    assert query["where"]["fieldFilter"]["field"]["fieldPath"] == "sample_id"
    assert query["where"]["fieldFilter"]["op"] == "EQUAL"
    assert query["limit"] == 1


def test_order_by_uses_run_query_with_descending_direction():
    captured = {}

    def handler(method, url, kwargs):
        captured.update(body=kwargs.get("json"))
        return FakeResponse(200, [])

    session = FakeSession(handler)
    list(FirestoreRestClient("test-project", session=session).collection("testing_data").order_by("created_at", direction="DESCENDING").limit(5).stream())
    order = captured["body"]["structuredQuery"]["orderBy"][0]
    assert order["field"]["fieldPath"] == "created_at"
    assert order["direction"] == "DESCENDING"


def test_bare_collection_stream_follows_list_documents_pagination():
    calls = []

    def handler(method, url, kwargs):
        calls.append(kwargs.get("params", {}))
        if len(calls) == 1:
            return FakeResponse(200, {"documents": [{"name": "projects/p/databases/(default)/documents/training_data/a", "fields": {"n": {"integerValue": "1"}}}], "nextPageToken": "next"})
        return FakeResponse(200, {"documents": [{"name": "projects/p/databases/(default)/documents/training_data/b", "fields": {"n": {"integerValue": "2"}}}]})

    session = FakeSession(handler)
    docs = list(FirestoreRestClient("test-project", session=session).collection("training_data").stream())
    assert [doc.id for doc in docs] == ["a", "b"]
    assert calls[0]["pageSize"] == 1000
    assert calls[1]["pageToken"] == "next"


def test_delete_calls_document_delete_endpoint():
    session = FakeSession(lambda method, *_: FakeResponse(200) if method == "DELETE" else FakeResponse(404))
    FirestoreRestClient("test-project", session=session).collection("testing_data").document("t1").delete()
    assert session.calls[0][0] == "DELETE"
