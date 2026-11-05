"""Privacy-conscious source inventory and digest-bound architecture citations.

An inventory only lists allowlisted local file paths, sizes, line counts and
SHA-256 digests. A source citation proves only that the *bytes* match the
cited snapshot; it does NOT prove that an authored architecture claim is true.
No source bytes, secrets, or absolute host paths are exported.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import ArchitectureSpec, Identifier, NonEmptyText, SchemaModel

SOURCE_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".cs", ".rb", ".php",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".sql", ".sh", ".proto",
    ".graphql", ".gql", ".tf", ".vue", ".svelte", ".md", ".rst",
    ".yml", ".yaml", ".toml",
}
SAFE_JSON_NAMES = {"package.json", "tsconfig.json", "openapi.json", "swagger.json"}
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "vendor",
    "dist", "build", "out", "__pycache__", ".pytest_cache", "coverage",
    "private", "secrets", "secret", "credentials", "fixtures-private",
}
SENSITIVE_WORDS = (
    "secret", "credential", "password", "passwd", "private_key",
    "access_key", "token", "id_rsa", "id_ed25519", "pem", "pfx",
    "keystore", "client_key", "prod_data",
)
MAX_SCAN_FILES = 10_000
MAX_SOURCE_BYTES = 5_000_000


def safe_source_path(path: str) -> str:
    """Accept only safe canonical POSIX paths relative to the selected source root."""
    if (not path or len(path) > 512 or "\\" in path or
            any(ord(char) < 32 or ord(char) == 127 for char in path)):
        raise ValueError("Source path must be a short, clean relative POSIX path")
    p = PurePosixPath(path)
    if (p.is_absolute() or path != p.as_posix() or
            any(part in {"", ".", ".."} for part in path.split("/"))):
        raise ValueError("Source path must be canonical, relative and without traversal")
    parts = path.split("/")
    if any(part.startswith(".") or part.lower() in EXCLUDED_DIRS or
           any(word in part.lower() for word in SENSITIVE_WORDS)
           for part in parts):
        raise ValueError("Source path is excluded by privacy policy")
    if _file_kind(path) is None:
        raise ValueError("Source path is not an allowed source/document/config file")
    return path


def _file_kind(path: str) -> str | None:
    p = PurePosixPath(path)
    suffix = p.suffix.lower()
    if suffix == ".json" and p.name.lower() not in SAFE_JSON_NAMES:
        return None
    if suffix not in SOURCE_SUFFIXES and p.name.lower() not in SAFE_JSON_NAMES:
        return None
    if p.name.lower().startswith("test_") or "tests" in p.parts or "__tests__" in p.parts:
        return "test"
    if suffix in {".md", ".rst"}:
        return "documentation"
    if suffix in {".yml", ".yaml", ".toml", ".json", ".tf"}:
        return "configuration"
    if suffix in {".sql", ".proto", ".graphql", ".gql"}:
        return "schema"
    return "source"


def read_safe_source_bytes(root: Path, name: str, *, byte_limit: int) -> bytes:
    """Read allowlisted source without executing it, with existing privacy bounds."""
    safe_source_path(name)
    parts = name.split("/")
    path = root.joinpath(*parts)
    if any(root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)):
        raise ValueError("Source path traverses a symbolic link")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Source path resolves outside the selected project")
    if not path.is_file():
        raise FileNotFoundError(name)
    # The pathname and symlink checks are best effort on all platforms.
    # O_NOFOLLOW additionally closes the last-component symlink race on POSIX.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not os.path.isfile(path):
            raise ValueError("Source path is not a regular file")
        if before.st_size > byte_limit:
            raise ValueError("Source file exceeds size limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, byte_limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > byte_limit:
                raise ValueError("Source file exceeds size limit")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("Source file changed while reading")
    finally:
        os.close(fd)
    return b"".join(chunks)


def _file_snapshot(root: Path, name: str, *, byte_limit: int) -> tuple[str, int, int]:
    data = read_safe_source_bytes(root, name, byte_limit=byte_limit)
    return hashlib.sha256(data).hexdigest(), len(data), len(data.splitlines())


class SourceFile(SchemaModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    line_count: int = Field(ge=0)
    kind: Literal["source", "test", "documentation", "configuration", "schema"]

    @field_validator("path")
    @classmethod
    def canonical_path(cls, value: str) -> str:
        return safe_source_path(value)


class SourceInventory(SchemaModel):
    schema_version: Literal[1] = 1
    files: list[SourceFile]
    skipped_oversized: int = Field(default=0, ge=0)
    caveat: str = (
        "Metadata only. Files excluded by privacy filters or size limits are "
        "not inventoried. File hashes do not establish architecture semantics "
        "or guarantee absence of secrets in allowed source files."
    )

    @model_validator(mode="after")
    def no_duplicate_paths(self) -> SourceInventory:
        names = [item.path for item in self.files]
        if names != sorted(set(names)):
            raise ValueError("Source inventory paths must be unique and sorted")
        return self


def scan_sources(
    project_root: str | Path, *, max_files: int = 2000, max_bytes: int = 1_000_000,
) -> SourceInventory:
    if not 1 <= max_files <= MAX_SCAN_FILES:
        raise ValueError("max_files must be between 1 and 10000")
    if not 1 <= max_bytes <= MAX_SOURCE_BYTES:
        raise ValueError("max_bytes must be between 1 and 5000000")
    root = Path(project_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source root must be an existing real directory, not a symlink")
    files: list[SourceFile] = []
    skipped_oversized = 0
    for directory, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = sorted(
            name for name in dirs
            if not name.startswith(".") and name.lower() not in EXCLUDED_DIRS
            and not any(word in name.lower() for word in SENSITIVE_WORDS)
            and not (Path(directory) / name).is_symlink()
        )
        for filename in sorted(filenames):
            full_path = Path(directory) / filename
            if full_path.is_symlink() or not full_path.is_file():
                continue
            name = full_path.relative_to(root).as_posix()
            try:
                safe_source_path(name)
            except ValueError:
                continue
            if len(files) >= max_files:
                raise ValueError("Source inventory file limit reached; narrow the project or raise --max-files")
            try:
                sha, byte_count, line_count = _file_snapshot(root, name, byte_limit=max_bytes)
            except ValueError as exc:
                if "size limit" in str(exc):
                    skipped_oversized += 1
                    continue
                raise
            files.append(SourceFile(
                path=name, sha256=sha, byte_count=byte_count,
                line_count=line_count, kind=_file_kind(name),
            ))
    return SourceInventory(files=sorted(files, key=lambda item: item.path),
                           skipped_oversized=skipped_oversized)


def save_inventory(inventory: SourceInventory, destination: str | Path) -> Path:
    path = Path(destination)
    if path.is_symlink() or path.exists():
        raise ValueError("Source inventory output must be a new file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


class SourceClaim(SchemaModel):
    architecture_id: Identifier
    source_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertion: NonEmptyText
    basis: Literal["observed", "inferred", "proposed"]
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @field_validator("source_path")
    @classmethod
    def canonical_source_path(cls, value: str) -> str:
        return safe_source_path(value)

    @model_validator(mode="after")
    def line_span(self) -> SourceClaim:
        if (self.line_start is None) != (self.line_end is None):
            raise ValueError("Source line_start and line_end must both be specified")
        if (self.line_start is not None and self.line_start > self.line_end):
            raise ValueError("Source line range is reversed")
        return self


class SourceEvidence(SchemaModel):
    schema_version: Literal[1] = 1
    claims: list[SourceClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_claims(self) -> SourceEvidence:
        keys = [(x.architecture_id, x.source_path, x.line_start, x.line_end)
                for x in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate source claims for architecture ID/path/line span")
        return self


class SourceCheck(SchemaModel):
    architecture_id: Identifier
    source_path: str
    assertion: NonEmptyText
    basis: Literal["observed", "inferred", "proposed"]
    line_start: int | None
    line_end: int | None
    expected_sha256: str
    actual_sha256: str | None
    status: Literal["matching_snapshot", "changed", "missing", "line_out_of_range", "unreadable"]


class SourceAssessment(SchemaModel):
    checks: list[SourceCheck]
    unlinked_mandatory_requirements: list[str]
    unlinked_components: list[str]
    caveat: str = (
        "matching_snapshot means the cited local file bytes match a SHA-256 "
        "snapshot, NOT that the claim is true or independently verified. "
        "Observed/inferred/proposed classifications are authored descriptions."
    )

    @property
    def requires_review(self) -> bool:
        return (
            bool(self.unlinked_mandatory_requirements or self.unlinked_components) or
            any(c.status != "matching_snapshot" or c.basis != "observed" for c in self.checks)
        )


def assess_sources(
    spec: ArchitectureSpec, evidence: SourceEvidence, source_root: str | Path,
    *, max_bytes: int = 1_000_000,
) -> SourceAssessment:
    root = Path(source_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source root must be an existing real directory, not a symlink")
    if not 1 <= max_bytes <= MAX_SOURCE_BYTES:
        raise ValueError("Invalid source file size limit")
    valid_ids = (
        spec.brief.requirement_ids() |
        {x.id for group in (spec.components, spec.relationships, spec.decisions,
                            spec.findings, spec.verification_cases) for x in group}
    )
    for claim in evidence.claims:
        if claim.architecture_id not in valid_ids:
            raise ValueError(f"Source claim refers to unknown architecture ID: {claim.architecture_id}")
    snapshots: dict[str, tuple[str | None, int | None, str]] = {}
    checks = []
    for claim in sorted(evidence.claims, key=lambda x: (
        x.architecture_id, x.source_path, x.line_start or 0, x.line_end or 0
    )):
        if claim.source_path not in snapshots:
            try:
                sha, _size, lines = _file_snapshot(root, claim.source_path, byte_limit=max_bytes)
                snapshots[claim.source_path] = sha, lines, "read"
            except FileNotFoundError:
                snapshots[claim.source_path] = None, None, "missing"
            except (OSError, ValueError):
                snapshots[claim.source_path] = None, None, "unreadable"
        current, lines, read_status = snapshots[claim.source_path]
        if read_status != "read":
            status = read_status
        elif current != claim.sha256:
            status = "changed"
        elif claim.line_end is not None and claim.line_end > lines:
            status = "line_out_of_range"
        else:
            status = "matching_snapshot"
        checks.append(SourceCheck(
            architecture_id=claim.architecture_id,
            source_path=claim.source_path, assertion=claim.assertion,
            basis=claim.basis, line_start=claim.line_start,
            line_end=claim.line_end, expected_sha256=claim.sha256,
            actual_sha256=current, status=status,
        ))
    matched = {x.architecture_id for x in checks
               if x.status == "matching_snapshot" and x.basis == "observed"}
    return SourceAssessment(
        checks=checks,
        unlinked_mandatory_requirements=sorted(
            spec.brief.mandatory_requirement_ids() - matched
        ),
        unlinked_components=sorted(
            {x.id for x in spec.components} - matched
        ),
    )
