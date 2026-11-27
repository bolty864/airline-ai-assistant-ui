"""Where the internal enterprise repository lives: local folder or Azure Blob Storage."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .config import Settings


class LocalSource:
    def __init__(self, root: str):
        self.root = Path(root)

    async def list(self) -> list[str]:
        return [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()]

    async def read(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def blob_path(self, path: str) -> str:
        return f"local://{(self.root / path).as_posix()}"


class BlobSource:
    """Expects the layout: policies/, sops/, control_registers/, audit_procedures/, security_standards/"""

    def __init__(self, connection_string: str, container: str, prefix: str = ""):
        from azure.storage.blob import BlobServiceClient

        self.container = BlobServiceClient.from_connection_string(connection_string).get_container_client(container)
        self.container_name = container
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""

    async def list(self) -> list[str]:
        def _list():
            return [b.name[len(self.prefix):] for b in self.container.list_blobs(name_starts_with=self.prefix or None)]

        return await asyncio.to_thread(_list)

    async def read(self, path: str) -> bytes:
        return await asyncio.to_thread(lambda: self.container.download_blob(self.prefix + path).readall())

    def blob_path(self, path: str) -> str:
        return f"{self.container_name}/{self.prefix}{path}"


def make_source(s: Settings):
    if s.enterprise_source == "blob":
        if not s.blob_connection_string:
            raise RuntimeError("ENTERPRISE_SOURCE=blob needs AZURE_STORAGE_CONNECTION_STRING")
        return BlobSource(s.blob_connection_string, s.blob_container, s.blob_prefix)
    return LocalSource(s.enterprise_local_path)
