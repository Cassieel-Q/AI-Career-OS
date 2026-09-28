from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class KnowledgePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern=r"^(resume_skill|interview_skill)$")
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=32)
    provenance: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    roles: list[str] = Field(default_factory=list, max_length=12)
    related_roles: list[str] = Field(default_factory=list, max_length=12)
    role_family: str | None = Field(default=None, max_length=64)
    competencies: list[str] = Field(default_factory=list, max_length=32)
    source_count: int = Field(default=0, ge=0, le=100_000)
    recency: str | None = Field(default=None, max_length=32)
    source_refs: list[str] = Field(default_factory=list, max_length=32)
    confidence: str | None = Field(default=None, max_length=32)
    body: str = ""
    path: str = ""
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeDiagnostic:
    path: str
    code: str
    message: str


class KnowledgePackLoader:
    def load_file(self, path: Path) -> tuple[KnowledgePack | None, KnowledgeDiagnostic | None]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return None, KnowledgeDiagnostic(str(path), "READ_FAILED", str(exc))
        if not text.startswith("---\n"):
            return None, KnowledgeDiagnostic(str(path), "FRONTMATTER_MISSING", "Markdown frontmatter must start with ---")
        closing = text.find("\n---", 4)
        if closing < 0:
            return None, KnowledgeDiagnostic(str(path), "FRONTMATTER_INVALID", "Markdown frontmatter is not closed")
        raw_meta = text[4:closing]
        body = text[closing + 4 :].lstrip("\r\n")
        try:
            metadata: Any = yaml.safe_load(raw_meta)
        except yaml.YAMLError as exc:
            return None, KnowledgeDiagnostic(str(path), "FRONTMATTER_INVALID", str(exc))
        if not isinstance(metadata, dict):
            return None, KnowledgeDiagnostic(str(path), "FRONTMATTER_INVALID", "Frontmatter must be a mapping")
        metadata = dict(metadata)
        # Accept the hand-authored contract used in the product brief while
        # keeping one normalized, strict model for the rest of the system.
        raw_kind = metadata.pop("kind", metadata.pop("type", None))
        if raw_kind in {"resume", "resume_skill"}:
            metadata["kind"] = "resume_skill"
        elif raw_kind in {"interview", "interview_skill"}:
            metadata["kind"] = "interview_skill"
        if not metadata.get("name") and metadata.get("id"):
            metadata["name"] = str(metadata["id"])
        if metadata.get("version") is not None and not isinstance(metadata["version"], str):
            metadata["version"] = str(metadata["version"])
        if not metadata.get("provenance"):
            metadata["provenance"] = metadata.pop("source_name", None) or "UNSPECIFIED"
        else:
            metadata.pop("source_name", None)
        source_refs = metadata.get("source_refs")
        if source_refs is None:
            source_refs = metadata.pop("source_urls", None)
            if source_refs is None and metadata.get("source_url"):
                source_refs = [metadata.pop("source_url")]
            metadata["source_refs"] = source_refs or []
        else:
            metadata.pop("source_urls", None)
            metadata.pop("source_url", None)
        if metadata.get("latest_source_date") is not None and metadata.get("recency") is None:
            metadata["recency"] = metadata.pop("latest_source_date")
        else:
            metadata.pop("latest_source_date", None)
        if metadata.get("recency") is not None and not isinstance(metadata["recency"], str):
            metadata["recency"] = str(metadata["recency"])
        metadata["body"] = body
        metadata["path"] = str(path)
        metadata["fingerprint"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            return KnowledgePack.model_validate(metadata), None
        except ValidationError as exc:
            fields = ", ".join(".".join(str(part) for part in error.get("loc", ())) for error in exc.errors())
            return None, KnowledgeDiagnostic(str(path), "SCHEMA_INVALID", f"Invalid fields: {fields or 'unknown'}")


class KnowledgePackRegistry:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.packs: list[KnowledgePack] = []
        self.errors: list[KnowledgeDiagnostic] = []
        self.reload()

    def reload(self) -> list[KnowledgePack]:
        loader = KnowledgePackLoader()
        packs: list[KnowledgePack] = []
        errors: list[KnowledgeDiagnostic] = []
        if self.root.exists():
            for path in sorted(self.root.rglob("*.md")):
                pack, diagnostic = loader.load_file(path)
                if pack is not None:
                    packs.append(pack)
                if diagnostic is not None:
                    errors.append(diagnostic)
        self.packs = packs
        self.errors = errors
        return list(self.packs)

    def by_kind(self, kind: str) -> list[KnowledgePack]:
        return [pack for pack in self.packs if pack.kind == kind]


def default_knowledge_root() -> Path:
    return Path(__file__).resolve().parents[3] / "knowledge"


def load_default_registry() -> KnowledgePackRegistry:
    return KnowledgePackRegistry(default_knowledge_root())


def sync_knowledge_packs(root: str | Path | None = None) -> dict[str, object]:
    registry = KnowledgePackRegistry(root or default_knowledge_root())
    return {
        "pack_count": len(registry.packs),
        "error_count": len(registry.errors),
        "fingerprints": {pack.id: pack.fingerprint for pack in registry.packs},
        "errors": [diagnostic.__dict__ for diagnostic in registry.errors],
    }
