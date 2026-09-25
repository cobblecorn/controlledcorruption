"""Binary file loading, hashing and safe output writing.

Core rule: **the original file is never modified**. Loading returns an
immutable ``bytes`` object; mutation always works on a private copy; output is
written to a *new* path unless the caller explicitly forces an overwrite.
"""

from __future__ import annotations

import binascii
import hashlib
import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class BinaryFile:
    """An immutable view of a loaded binary plus its identifying hashes."""

    path: Optional[str]
    data: bytes
    hashes: Dict[str, str]

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def sha256(self) -> str:
        return self.hashes["sha256"]

    @property
    def filename(self) -> Optional[str]:
        return os.path.basename(self.path) if self.path else None


def compute_hashes(data: bytes, algorithms=("sha256", "md5", "sha1", "crc32")) -> Dict[str, str]:
    """Compute the requested hashes for ``data``.

    SHA-256 is always the canonical identifier. CRC32 is included because some
    ROM communities index by it.
    """
    result: Dict[str, str] = {}
    for algo in algorithms:
        if algo == "crc32":
            result["crc32"] = f"{binascii.crc32(data) & 0xFFFFFFFF:08x}"
        else:
            h = hashlib.new(algo)
            h.update(data)
            result[algo] = h.hexdigest()
    return result


def load_binary(path: str, algorithms=("sha256", "md5", "sha1", "crc32")) -> BinaryFile:
    """Read a file from disk and hash it. Does not keep the file open."""
    with open(path, "rb") as fh:
        data = fh.read()
    return BinaryFile(path=path, data=data, hashes=compute_hashes(data, algorithms))


def from_bytes(data: bytes, path: Optional[str] = None,
               algorithms=("sha256", "md5", "sha1", "crc32")) -> BinaryFile:
    """Wrap in-memory bytes as a :class:`BinaryFile` (used by tests / pipes)."""
    return BinaryFile(path=path, data=bytes(data), hashes=compute_hashes(data, algorithms))


def write_output(path: str, data: bytes, *, overwrite: bool = False) -> str:
    """Write ``data`` to ``path``.

    Refuses to clobber an existing file unless ``overwrite=True``. Writes to a
    temporary file first and renames, so a failed/partial write never leaves a
    corrupt half-written output where a valid file used to be.
    """
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing file: {path} (pass overwrite=True)"
        )
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.cctmp.{os.getpid()}"
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return path


def suggest_output_name(source_path: str, seed: object, ext: Optional[str] = None) -> str:
    """Build a non-destructive output name like ``game_corrupt_CODY3491281.z64``."""
    base, orig_ext = os.path.splitext(source_path)
    ext = ext or orig_ext or ".bin"
    seed_tag = "".join(ch for ch in str(seed) if ch.isalnum()) or "seed"
    return f"{base}_corrupt_{seed_tag}{ext}"
