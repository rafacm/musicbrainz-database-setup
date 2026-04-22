"""Parse SHA256SUMS / MD5SUMS files. Optionally verify GPG signatures."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from musicbrainz_db_setup.errors import ChecksumError

_LINE_RE = re.compile(r"^([0-9a-fA-F]{32,128})\s+\*?(\S+)\s*$")


@dataclass(frozen=True, slots=True)
class Checksums:
    """filename → lowercase hex digest."""

    entries: dict[str, str]
    algo: str  # "sha256" | "md5"

    def digest_for(self, filename: str) -> str | None:
        return self.entries.get(filename)


def parse(text: str, algo: str) -> Checksums:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        digest, name = m.group(1).lower(), m.group(2)
        entries[name] = digest
    return Checksums(entries=entries, algo=algo)


def hash_file(path: Path, algo: str, *, chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def verify_file(path: Path, expected_hex: str, algo: str) -> None:
    actual = hash_file(path, algo)
    if actual.lower() != expected_hex.lower():
        raise ChecksumError(
            f"{algo} mismatch for {path.name}: expected {expected_hex}, got {actual}"
        )
