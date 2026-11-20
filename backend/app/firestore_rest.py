"""Firestore REST adapter using Application Default Credentials (no gRPC dependency).

This deliberately uses Google's Firestore REST API so local development works on
Windows systems where Application Control blocks grpcio's native cygrpc DLL.
On Cloud Run, ADC resolves to the attached runtime service account.
"""
from __future__ import annotations

import base64
import math
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterator
from urllib.parse import quote

from . import settings


class FirestoreRestError(RuntimeError):
    pass


def _encode_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullValue": "NULL_VALUE"}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Firestore cannot store NaN or infinite numbers.")
        return {"doubleValue": value}
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return {"timestampValue": dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")}
    if isinstance(value, bytes):
        return {"bytesValue": base64.b64encode(value).decode("ascii")}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_encode_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": _encode_fields(value)}}
    raise TypeError(f"Unsupported Firestore value type: {type(value).__name__}")


def _encode_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _encode_value(value) for key, value in data.items()}


def _decode_value(value: dict[str, Any]) -> Any:
    if "nullValue" in value:
        return None
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "timestampValue" in value:
        raw = value["timestampValue"]
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if "bytesValue" in value:
        return base64.b64decode(value["bytesValue"])
    if "stringValue" in value:
        return value["stringValue"]
    if "arrayValue" in value:
        return [_decode_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return _decode_fields(value["mapValue"].get("fields", {}))
    if "geoPointValue" in value:
        return value["geoPointValue"]
    if "referenceValue" in value:
        return value["referenceValue"]
    raise ValueError("Firestore returned an unsupported value type.")


def _decode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: _decode_value(value) for key, value in fields.items()}


@lru_cache(maxsize=1)
def _authorized_session():
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError("google-auth is required for Firestore REST access.") from exc
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore"])
    return AuthorizedSession(credentials)


class DocumentSnapshot:
    def __init__(self, document_id: str, raw: dict[str, Any] | None):
        self.id = document_id
        self.exists = raw is not None
        self._data = _decode_fields(raw.get("fields", {})) if raw else None

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class FirestoreRestClient:
    def __init__(self, project_id: str | None = None, session=None):
        self.project_id = project_id or settings.PROJECT_ID
        if not self.project_id:
            raise RuntimeError("FIREBASE_PROJECT_ID is not configured")
        self._session = session
        self._base_url = (
            "https://firestore.googleapis.com/v1/projects/"
            f"{quote(self.project_id, safe='')}/databases/(default)/documents"
        )

    @property
    def session(self):
        if self._session is None:
            self._session = _authorized_session()
        return self._session

    def _request(self, method: str, url: str, *, params=None, json_body=None, allow_status=()) -> Any:
        response = self.session.request(
            method, url, params=params, json=json_body, timeout=(10, 45)
        )
        if response.status_code in allow_status:
            return response
        if not response.ok:
            detail = (response.text or "").replace("\n", " ")[:500]
            raise FirestoreRestError(
                f"Firestore REST request failed ({response.status_code}): {detail or 'No response details'}"
            )
        return response

    def collection(self, collection_id: str) -> "CollectionReference":
        if not collection_id or "/" in collection_id:
            raise ValueError("Invalid Firestore collection name.")
        return CollectionReference(self, collection_id)

    def _document_url(self, collection_id: str, document_id: str) -> str:
        if not document_id or "/" in document_id:
            raise ValueError("Invalid Firestore document ID.")
        return f"{self._base_url}/{quote(collection_id, safe='')}/{quote(document_id, safe='')}"

    def _list_collection(self, collection_id: str) -> Iterator[DocumentSnapshot]:
        url = f"{self._base_url}/{quote(collection_id, safe='')}"
        page_token = None
        while True:
            params = {"pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            response = self._request("GET", url, params=params)
            payload = response.json()
            for raw in payload.get("documents", []):
                name = raw.get("name", "")
                yield DocumentSnapshot(name.rsplit("/", 1)[-1], raw)
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

    def _run_query(self, collection_id: str, *, filters=None, orderings=None, limit=None) -> Iterator[DocumentSnapshot]:
        structured: dict[str, Any] = {"from": [{"collectionId": collection_id}]}
        if filters:
            clauses = []
            for field_path, operator, value in filters:
                op_map = {"==": "EQUAL", "!=": "NOT_EQUAL", "<": "LESS_THAN", "<=": "LESS_THAN_OR_EQUAL", ">": "GREATER_THAN", ">=": "GREATER_THAN_OR_EQUAL"}
                if operator not in op_map:
                    raise ValueError(f"Unsupported Firestore query operator: {operator}")
                clauses.append({
                    "fieldFilter": {
                        "field": {"fieldPath": field_path},
                        "op": op_map[operator],
                        "value": _encode_value(value),
                    }
                })
            structured["where"] = clauses[0] if len(clauses) == 1 else {"compositeFilter": {"op": "AND", "filters": clauses}}
        if orderings:
            structured["orderBy"] = [
                {"field": {"fieldPath": field}, "direction": direction}
                for field, direction in orderings
            ]
        if limit is not None:
            structured["limit"] = int(limit)
        response = self._request("POST", f"{self._base_url}:runQuery", json_body={"structuredQuery": structured})
        for item in response.json():
            if "error" in item:
                detail = str(item["error"])[:500]
                raise FirestoreRestError(f"Firestore query failed: {detail}")
            raw = item.get("document")
            if raw:
                name = raw.get("name", "")
                yield DocumentSnapshot(name.rsplit("/", 1)[-1], raw)


class DocumentReference:
    def __init__(self, client: FirestoreRestClient, collection_id: str, document_id: str):
        self._client = client
        self._collection_id = collection_id
        self.id = document_id
        self._url = client._document_url(collection_id, document_id)

    def get(self) -> DocumentSnapshot:
        response = self._client._request("GET", self._url, allow_status=(404,))
        if response.status_code == 404:
            return DocumentSnapshot(self.id, None)
        return DocumentSnapshot(self.id, response.json())

    def set(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise TypeError("Firestore document data must be a dictionary.")
        existing = self.get()
        keys = list(dict.fromkeys([*(existing.to_dict() or {}).keys(), *data.keys()]))
        params = [("updateMask.fieldPaths", key) for key in keys]
        self._client._request("PATCH", self._url, params=params or None, json_body={"fields": _encode_fields(data)})

    def update(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict) or not data:
            raise ValueError("Firestore update requires at least one field.")
        params = [("updateMask.fieldPaths", key) for key in data]
        params.append(("currentDocument.exists", "true"))
        self._client._request("PATCH", self._url, params=params, json_body={"fields": _encode_fields(data)})

    def delete(self) -> None:
        self._client._request("DELETE", self._url, allow_status=(404,))


class CollectionReference:
    def __init__(self, client: FirestoreRestClient, collection_id: str):
        self._client = client
        self.id = collection_id

    def document(self, document_id: str) -> DocumentReference:
        return DocumentReference(self._client, self.id, document_id)

    def stream(self) -> Iterator[DocumentSnapshot]:
        return self._client._list_collection(self.id)

    def where(self, field_path: str, op_string: str, value: Any) -> "Query":
        return Query(self._client, self.id).where(field_path, op_string, value)

    def order_by(self, field_path: str, direction: str = "ASCENDING") -> "Query":
        return Query(self._client, self.id).order_by(field_path, direction=direction)

    def limit(self, count: int) -> "Query":
        return Query(self._client, self.id).limit(count)


class Query:
    def __init__(self, client: FirestoreRestClient, collection_id: str):
        self._client = client
        self._collection_id = collection_id
        self._filters: list[tuple[str, str, Any]] = []
        self._orderings: list[tuple[str, str]] = []
        self._limit: int | None = None

    def where(self, field_path: str, op_string: str, value: Any) -> "Query":
        self._filters.append((field_path, op_string, value))
        return self

    def order_by(self, field_path: str, direction: str = "ASCENDING") -> "Query":
        normalized = str(direction).upper()
        if normalized not in {"ASCENDING", "DESCENDING"}:
            raise ValueError("Firestore order direction must be ASCENDING or DESCENDING.")
        self._orderings.append((field_path, normalized))
        return self

    def limit(self, count: int) -> "Query":
        if int(count) < 0:
            raise ValueError("Firestore query limit cannot be negative.")
        self._limit = int(count)
        return self

    def stream(self) -> Iterator[DocumentSnapshot]:
        if not self._filters and not self._orderings and self._limit is None:
            return self._client._list_collection(self._collection_id)
        return self._client._run_query(
            self._collection_id,
            filters=self._filters,
            orderings=self._orderings,
            limit=self._limit,
        )
