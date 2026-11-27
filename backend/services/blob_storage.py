"""Regulatory document storage: Azure Blob Storage, or a local folder in dev (LOCAL_STORAGE_ROOT).

blob_path may be:
  * a full https URL to the blob
  * "<container>/<path>"
  * "<path>" inside REGULATORY_BLOB_CONTAINER   (what Agent 1 writes: the filename)

Integrity checks are cheap: Agent 1 stores the file's sha256 in blob metadata on upload, so the
watchdog compares metadata instead of downloading every file on every scan. Blobs without
metadata (uploaded elsewhere) are downloaded and hashed once, then the metadata is written.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from settings import Settings

log = logging.getLogger(__name__)


class BlobNotFoundError(Exception):
    pass


@dataclass
class BlobState:
    exists: bool
    sha256: str | None = None      # verified content hash, None if unknown / missing

    def matches(self, expected: str) -> bool:
        return self.exists and self.sha256 == expected


class BlobStorageService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._service = None
        self._containers_ready: set[str] = set()

    @property
    def is_local(self) -> bool:
        return bool(self.settings.local_storage_root)

    # ------------------------------------------------------------------ public API

    async def download(self, blob_path: str) -> bytes:
        if self.is_local:
            return await asyncio.to_thread(self._local_read, blob_path)
        return await asyncio.to_thread(self._blob_read, blob_path)

    async def upload(self, blob_path: str, data: bytes, sha256: str, content_type: str | None = None) -> None:
        if self.is_local:
            await asyncio.to_thread(self._local_write, blob_path, data)
        else:
            await asyncio.to_thread(self._blob_write, blob_path, data, sha256, content_type)

    async def delete(self, blob_path: str) -> bool:
        if self.is_local:
            return await asyncio.to_thread(self._local_delete, blob_path)
        return await asyncio.to_thread(self._blob_delete, blob_path)

    async def state(self, blob_path: str, expected_sha256: str) -> BlobState:
        if self.is_local:
            return await asyncio.to_thread(self._local_state, blob_path)
        return await asyncio.to_thread(self._blob_state, blob_path, expected_sha256)

    async def healthy(self) -> bool:
        if self.is_local:
            return Path(self.settings.local_storage_root).exists()
        return await asyncio.to_thread(lambda: self._container_client(self.settings.regulatory_blob_container).exists())

    # ------------------------------------------------------------------ local

    def _local_path(self, blob_path: str) -> Path:
        root = Path(self.settings.local_storage_root).resolve()
        path = (root / blob_path.lstrip("/")).resolve()
        if root not in path.parents:
            raise BlobNotFoundError(f"Path escapes LOCAL_STORAGE_ROOT: {blob_path}")
        return path

    def _local_read(self, blob_path: str) -> bytes:
        path = self._local_path(blob_path)
        if not path.is_file():
            raise BlobNotFoundError(f"File not found: {path}")
        return path.read_bytes()

    def _local_write(self, blob_path: str, data: bytes) -> None:
        path = self._local_path(blob_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: a half-written file is never visible

    def _local_delete(self, blob_path: str) -> bool:
        path = self._local_path(blob_path)
        if path.is_file():
            path.unlink()
            return True
        return False

    def _local_state(self, blob_path: str) -> BlobState:
        path = self._local_path(blob_path)
        if not path.is_file():
            return BlobState(exists=False)
        return BlobState(exists=True, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    # ------------------------------------------------------------------ azure

    def _client(self):
        if self._service is None:
            from azure.storage.blob import BlobServiceClient

            if not self.settings.azure_storage_connection_string:
                raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set (or set LOCAL_STORAGE_ROOT for dev)")
            self._service = BlobServiceClient.from_connection_string(self.settings.azure_storage_connection_string)
        return self._service

    def _container_client(self, name: str):
        return self._client().get_container_client(name)

    def _split(self, blob_path: str) -> tuple[str, str]:
        path = blob_path.lstrip("/")
        default = self.settings.regulatory_blob_container
        first, _, rest = path.partition("/")
        if rest and first == default:
            return first, rest
        return default, path

    def _blob_client(self, blob_path: str):
        from azure.storage.blob import BlobClient

        if blob_path.startswith(("https://", "http://")):
            return BlobClient.from_blob_url(blob_path, credential=self._client().credential)
        container, name = self._split(blob_path)
        return self._client().get_blob_client(container=container, blob=name)

    def _ensure_container(self, blob_path: str) -> None:
        if blob_path.startswith(("https://", "http://")):
            return
        container, _ = self._split(blob_path)
        if container in self._containers_ready:
            return
        from azure.core.exceptions import ResourceExistsError

        try:
            self._container_client(container).create_container()
        except ResourceExistsError:
            pass
        self._containers_ready.add(container)

    def _blob_read(self, blob_path: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._blob_client(blob_path).download_blob(max_concurrency=4).readall()
        except ResourceNotFoundError as exc:
            raise BlobNotFoundError(f"Blob not found: {blob_path}") from exc

    def _blob_write(self, blob_path: str, data: bytes, sha256: str, content_type: str | None) -> None:
        from azure.storage.blob import ContentSettings

        self._ensure_container(blob_path)
        self._blob_client(blob_path).upload_blob(
            data, overwrite=True, metadata={"sha256": sha256},
            content_settings=ContentSettings(content_type=content_type) if content_type else None,
        )

    def _blob_delete(self, blob_path: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._blob_client(blob_path).delete_blob()
            return True
        except ResourceNotFoundError:
            return False

    def _blob_state(self, blob_path: str, expected_sha256: str) -> BlobState:
        from azure.core.exceptions import ResourceNotFoundError

        client = self._blob_client(blob_path)
        try:
            props = client.get_blob_properties()
        except ResourceNotFoundError:
            return BlobState(exists=False)
        meta_sha = (props.metadata or {}).get("sha256")
        if meta_sha:
            return BlobState(exists=True, sha256=meta_sha)
        # No metadata: hash once, then remember it so the next scan is cheap
        actual = hashlib.sha256(client.download_blob().readall()).hexdigest()
        if actual == expected_sha256:
            client.set_blob_metadata({**(props.metadata or {}), "sha256": actual})
        return BlobState(exists=True, sha256=actual)
