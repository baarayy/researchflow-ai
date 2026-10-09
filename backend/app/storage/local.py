import asyncio
import re
from pathlib import Path

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,100}(\.[a-z0-9]{1,10})?$")


class LocalFileStorage:
    """Stores files under one base directory. Keys are server-generated (uuid + extension);
    user-supplied filenames are only ever kept as metadata, never used as paths."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.match(key):
            raise ValueError(f"Unsafe storage key: {key!r}")
        path = (self.base_dir / key).resolve()
        if not path.is_relative_to(self.base_dir):  # defence in depth against traversal
            raise ValueError("Storage key escapes base directory")
        return path

    async def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)
