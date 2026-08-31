"""Read-only loader for versioned code-layer chapter writing contracts.

This module intentionally has no database imports and never writes to the
prompt table. The snapshot is an auditable source artifact for contract
changes; production prompt assembly remains unchanged until a separate,
explicit integration task wires a version into the pipeline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


_DEFAULT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "contracts"
    / "chapter_writing_contract.v1.md"
)
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_REQUIRED_METADATA = ("contract_id", "version", "kind")
_EXPECTED_KIND = "code-layer-writing-contract"


class ContractSnapshotError(ValueError):
    """Raised when a contract snapshot is not a valid versioned artifact."""


@dataclass(frozen=True, slots=True)
class ChapterWritingContractSnapshot:
    """Immutable, content-addressed view of one checked-in contract snapshot."""

    contract_id: str
    version: str
    metadata: Mapping[str, str]
    content: str
    sha256: str
    source_path: Path


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ContractSnapshotError("contract snapshot must start with YAML-like front matter")

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise ContractSnapshotError("contract snapshot front matter is not closed")

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            raise ContractSnapshotError(f"invalid front matter line: {stripped!r}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ContractSnapshotError("front matter keys and values must be non-empty")
        if key in metadata:
            raise ContractSnapshotError(f"duplicate front matter key: {key}")
        metadata[key] = value

    missing = [key for key in _REQUIRED_METADATA if not metadata.get(key)]
    if missing:
        raise ContractSnapshotError(
            "front matter missing required field(s): " + ", ".join(missing)
        )

    body = "".join(lines[closing_index + 1 :])
    if not body.strip():
        raise ContractSnapshotError("contract snapshot body must not be empty")
    return metadata, body


def load_chapter_writing_contract(
    path: str | Path | None = None,
) -> ChapterWritingContractSnapshot:
    """Read and validate a checked-in writing-contract snapshot.

    ``path`` is injectable for isolated regression tests. The default points
    to a nested prompt artifact so the legacy root-level DB prompt seeder does
    not treat this contract as the user's ``writing``/``writing_v2`` prompt.
    Reading this artifact never mutates it or any database state.
    """

    source_path = Path(path) if path is not None else _DEFAULT_CONTRACT_PATH
    raw = source_path.read_text(encoding="utf-8")
    metadata, content = _parse_front_matter(raw)
    if metadata["kind"] != _EXPECTED_KIND:
        raise ContractSnapshotError(
            f'kind must be {_EXPECTED_KIND!r}, got {metadata["kind"]!r}'
        )

    version = metadata["version"]
    if not _VERSION_RE.fullmatch(version):
        raise ContractSnapshotError(
            f"version must be MAJOR.MINOR.PATCH, got {version!r}"
        )

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return ChapterWritingContractSnapshot(
        contract_id=metadata["contract_id"],
        version=version,
        metadata=MappingProxyType(dict(metadata)),
        content=content,
        sha256=digest,
        source_path=source_path,
    )