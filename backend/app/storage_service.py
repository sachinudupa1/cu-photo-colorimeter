"""Supabase Storage adapter with a small Google-Cloud-Storage-compatible interface.

The Supabase secret key is sent only in the `apikey` header. New `sb_secret_...`
keys are not JWTs and must not be sent as `Authorization: Bearer` tokens.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from . import settings


def _new_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=True)


class SupabaseStorageError(RuntimeError):
    pass


class SupabaseBlob:
    def __init__(self, bucket_name: str, object_path: str):
        self.bucket_name = bucket_name
        self.object_path = object_path.strip("/")
        if not self.object_path or any(part in {".", ".."} for part in self.object_path.split("/")):
            raise ValueError("Invalid Storage object path.")

    @property
    def _url(self) -> str:
        bucket = quote(self.bucket_name, safe="")
        path = "/".join(quote(part, safe="") for part in self.object_path.split("/"))
        return f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{path}"

    @property
    def _headers(self) -> dict[str, str]:
        settings.validate_supabase_config()
        # New Supabase secret keys are API keys, not JWTs. Send them via apikey only.
        return {"apikey": settings.SUPABASE_SECRET_KEY}

    @staticmethod
    def _raise_for_storage_error(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = response.text[:400].replace("\n", " ")
        raise SupabaseStorageError(
            f"Supabase Storage request failed ({response.status_code}): {detail or 'No response details'}"
        )

    def exists(self) -> bool:
        """Return False when the object is absent.

        Supabase Storage's HEAD object endpoint can return either 400 or 404
        for a missing object, with an empty response body. The official
        supabase-js Storage exists() implementation treats both statuses as
        "not present". Upload/download errors remain strict in their own paths.
        """
        with _new_client() as client:
            response = client.head(self._url, headers=self._headers)
        if response.status_code in {400, 404}:
            return False
        self._raise_for_storage_error(response)
        return True

    def download_as_bytes(self) -> bytes:
        with _new_client() as client:
            response = client.get(self._url, headers=self._headers)
        if response.status_code in {400, 404} and "not found" in response.text.lower():
            raise FileNotFoundError(f"Stored file does not exist: {self.object_path}")
        self._raise_for_storage_error(response)
        return response.content

    def download_as_text(self, encoding: str = "utf-8") -> str:
        return self.download_as_bytes().decode(encoding)

    def upload_from_string(self, data: str | bytes, content_type: str = "application/octet-stream", **_: object) -> None:
        content = data.encode("utf-8") if isinstance(data, str) else data
        headers = {**self._headers, "Content-Type": content_type, "x-upsert": "true"}
        with _new_client() as client:
            response = client.post(self._url, headers=headers, content=content)
        self._raise_for_storage_error(response)

    def upload_from_filename(self, filename: str, content_type: str = "application/octet-stream", **kwargs: object) -> None:
        self.upload_from_string(Path(filename).read_bytes(), content_type=content_type, **kwargs)

    def delete(self) -> None:
        with _new_client() as client:
            response = client.delete(self._url, headers=self._headers)
        if response.status_code == 404:
            return
        self._raise_for_storage_error(response)


class SupabaseStorageBucket:
    def __init__(self, bucket_name: str):
        self.name = bucket_name

    def blob(self, object_path: str) -> SupabaseBlob:
        return SupabaseBlob(self.name, object_path)


def storage_bucket() -> SupabaseStorageBucket:
    settings.validate_supabase_config()
    return SupabaseStorageBucket(settings.SUPABASE_BUCKET_NAME)
