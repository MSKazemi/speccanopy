"""Privacy-conscious source inventory and digest-bound architecture citations.

An inventory only lists allowlisted local file paths, sizes, line counts and
SHA-256 digests. A source citation proves only that the *bytes* match the
cited snapshot; it does NOT prove that an authored architecture claim is true.
No source bytes, secrets, or absolute host paths are exported.

An inventory may optionally carry a :class:`SourceRevision`: the commit hash and
branch ref read straight from `.git` files (no git executable is run). It is an
unauthenticated hint and says nothing about whether the working tree is clean.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
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
# Bump when the allowlist/exclusion semantics change in a way the constants
# above do not capture, so recorded inventory scopes stop comparing as equal.
INVENTORY_POLICY_VERSION = 1


def inventory_policy_digest() -> str:
    """SHA-256 of the current allowlist/privacy-exclusion policy (not of any file)."""
    policy = {
        "version": INVENTORY_POLICY_VERSION,
        "source_suffixes": sorted(SOURCE_SUFFIXES),
        "safe_json_names": sorted(SAFE_JSON_NAMES),
        "excluded_dirs": sorted(EXCLUDED_DIRS),
        "sensitive_words": sorted(SENSITIVE_WORDS),
    }
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


class InventoryScope(SchemaModel):
    """Scan bounds and policy that determined which files an inventory could see.

    Recorded so that comparing two inventories can detect differing coverage.
    It deliberately contains no host path: it cannot prove two inventories were
    taken from the same project.
    """

    max_files: int = Field(ge=1, le=MAX_SCAN_FILES)
    max_file_bytes: int = Field(ge=1, le=MAX_SOURCE_BYTES)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


_COMMIT_PATTERN = r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"
_COMMIT_RE = re.compile(_COMMIT_PATTERN)
_REF_PART_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._+-]{0,99}$")
MAX_GIT_META_BYTES = 65_536
MAX_PACKED_REFS_BYTES = 5_000_000


def _valid_ref_name(ref: str) -> bool:
    """A conservative `refs/...` name: no traversal, no URL, no whitespace."""
    parts = ref.split("/")
    return (
        len(ref) <= 200 and len(parts) >= 3 and parts[0] == "refs"
        and all(_REF_PART_RE.match(p) and ".." not in p and not p.endswith(".lock")
                for p in parts[1:])
    )


class SourceRevision(SchemaModel):
    """Optional, unauthenticated git revision hint for an inventory.

    Read from `.git` files only (no git executable, no network). It records the
    commit and branch ref at scan time. It does NOT state whether the working
    tree is clean or dirty: the per-file SHA-256 digests are the content binding.
    Remote URLs, user names and absolute paths are never recorded.
    """

    status: Literal["recorded", "unknown"]
    commit: str | None = Field(default=None, pattern=_COMMIT_PATTERN)
    ref: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=300)
    caveat: str = (
        "Read from .git metadata files only; no git command was run. Working-tree "
        "clean or dirty state is NOT recorded: the file SHA-256 digests are the "
        "content binding. The commit is an unauthenticated hint, not proof of "
        "project identity or provenance."
    )

    @field_validator("ref")
    @classmethod
    def safe_ref(cls, value: str | None) -> str | None:
        if value is not None and not _valid_ref_name(value):
            raise ValueError("Revision ref must be a safe refs/... name")
        return value

    @model_validator(mode="after")
    def status_matches_fields(self) -> SourceRevision:
        if self.status == "recorded":
            if self.commit is None or self.reason is not None:
                raise ValueError("A recorded revision needs a commit and no reason")
        elif self.commit is not None or self.ref is not None or self.reason is None:
            raise ValueError("An unknown revision needs a reason and no commit or ref")
        return self


class _RevisionUnknown(Exception):
    pass


def _read_git_file(git_dir: Path, parts: list[str], limit: int, *, missing_ok: bool = False) -> bytes | None:
    """Read a regular, non-symlink file below `git_dir` with a size bound."""
    current = git_dir
    for index, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise _RevisionUnknown("a required .git file was not found") from None
        except OSError:
            raise _RevisionUnknown("a .git file could not be read") from None
        if stat.S_ISLNK(st.st_mode):
            raise _RevisionUnknown("a .git path is a symbolic link; not followed")
        last = index == len(parts) - 1
        if (last and not stat.S_ISREG(st.st_mode)) or (not last and not stat.S_ISDIR(st.st_mode)):
            raise _RevisionUnknown("a .git path is not a regular file")
    try:
        fd = os.open(current, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise _RevisionUnknown("a .git file could not be opened") from None
    try:
        data = os.read(fd, limit + 1)
    finally:
        os.close(fd)
    if len(data) > limit:
        raise _RevisionUnknown("a .git file exceeds the size limit")
    return data


def _text(data: bytes) -> str:
    try:
        return data.decode("ascii")
    except UnicodeDecodeError:
        raise _RevisionUnknown("a .git file is not plain ASCII") from None


def _resolve_revision(root: Path) -> SourceRevision:
    git = root / ".git"
    if git.is_symlink():
        raise _RevisionUnknown("the .git entry is a symbolic link; not followed")
    if not git.exists():
        raise _RevisionUnknown("no .git entry at the project root")
    if git.is_file():
        raise _RevisionUnknown(
            "the .git entry is a file (gitdir pointer, e.g. a worktree or submodule); not followed")
    if not git.is_dir():
        raise _RevisionUnknown("the .git entry is not a directory")
    head = _text(_read_git_file(git, ["HEAD"], MAX_GIT_META_BYTES) or b"").strip()
    if _COMMIT_RE.match(head):
        return SourceRevision(status="recorded", commit=head)
    if not head.startswith("ref: "):
        raise _RevisionUnknown("HEAD is neither a commit hash nor a branch reference")
    ref = head[5:].strip()
    if not _valid_ref_name(ref):
        raise _RevisionUnknown("HEAD names an unsupported or unsafe reference")
    loose = _read_git_file(git, ref.split("/"), MAX_GIT_META_BYTES, missing_ok=True)
    if loose is not None:
        commit = _text(loose).strip()
        if not _COMMIT_RE.match(commit):
            raise _RevisionUnknown("the branch reference file does not hold a valid commit hash")
        return SourceRevision(status="recorded", commit=commit, ref=ref)
    packed = _read_git_file(git, ["packed-refs"], MAX_PACKED_REFS_BYTES, missing_ok=True)
    for line in _text(packed or b"").splitlines():
        if line.startswith(("#", "^")):
            continue
        commit, _, name = line.partition(" ")
        if name == ref:
            if not _COMMIT_RE.match(commit):
                raise _RevisionUnknown("packed-refs holds an invalid commit hash for the branch")
            return SourceRevision(status="recorded", commit=commit, ref=ref)
    raise _RevisionUnknown("the branch reference has no commit (unborn branch or missing ref)")


def read_git_revision(project_root: str | Path) -> SourceRevision:
    """Record the commit/ref from `<root>/.git` files; never executes git.

    Anything unusual (symlink, gitdir pointer file, malformed content, missing
    ref) yields an `unknown` revision with a generic reason; it never follows
    links and never includes host paths or file contents in the reason.
    """
    try:
        return _resolve_revision(Path(project_root))
    except _RevisionUnknown as exc:
        return SourceRevision(status="unknown", reason=str(exc))
    except OSError:
        return SourceRevision(status="unknown", reason="the .git metadata could not be read")


class SourceInventory(SchemaModel):
    schema_version: Literal[1] = 1
    files: list[SourceFile]
    skipped_oversized: int = Field(default=0, ge=0)
    # None for inventories written before scope recording existed; coverage of
    # such snapshots is unknown, not assumed complete.
    scope: InventoryScope | None = None
    # None unless the scan was asked to record it (`--record-git-revision`) and
    # for inventories written before revision recording existed.
    revision: SourceRevision | None = None
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
        if self.scope is not None and (
            len(self.files) > self.scope.max_files or
            any(item.byte_count > self.scope.max_file_bytes for item in self.files)
        ):
            raise ValueError("Source inventory files exceed its recorded scan scope")
        return self


def scan_sources(
    project_root: str | Path, *, max_files: int = 2000, max_bytes: int = 1_000_000,
    record_revision: bool = False,
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
    return SourceInventory(
        files=sorted(files, key=lambda item: item.path),
        skipped_oversized=skipped_oversized,
        scope=InventoryScope(
            max_files=max_files, max_file_bytes=max_bytes,
            policy_sha256=inventory_policy_digest(),
        ),
        revision=read_git_revision(root) if record_revision else None,
    )


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
