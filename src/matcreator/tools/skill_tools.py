from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from google.adk.skills import load_skill_from_dir

from matcreator import skill

_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _validate_name(name: str) -> str:
    normalized = (name or "").strip()
    if not _SKILL_NAME_RE.match(normalized):
        raise ValueError(
            "Skill name must be 1-64 lowercase letters, digits, hyphens, or underscores, "
            "and start with a letter or digit."
        )
    if normalized in skill.get_default_skill_names():
        raise ValueError(f"Cannot use built-in skill name '{normalized}'.")
    return normalized


def _skill_dir(name: str) -> Path:
    return skill.user_skills_dir().expanduser().resolve() / name


def _frontmatter(
    name: str,
    description: str,
    allowed_tools: list[str] | None,
    dependent_skills: list[str] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "name": name,
        "description": description.strip(),
    }
    if allowed_tools:
        fm["allowed_tools"] = ", ".join(allowed_tools)
    merged_metadata = dict(metadata or {})
    if dependent_skills is not None:
        merged_metadata["dependent_skills"] = dependent_skills
    if merged_metadata:
        fm["metadata"] = merged_metadata
    return fm


def _skill_content(
    name: str,
    description: str,
    instructions: str,
    allowed_tools: list[str] | None,
    dependent_skills: list[str] | None,
    metadata: dict[str, Any] | None,
) -> str:
    fm = yaml.safe_dump(
        _frontmatter(name, description, allowed_tools, dependent_skills, metadata),
        sort_keys=False,
        allow_unicode=False,
    ).strip()
    return f"---\n{fm}\n---\n{instructions.strip()}\n"


def _write_and_validate(
    target_dir: Path,
    content: str,
    *,
    refresh: bool,
) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_file = target_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    load_skill_from_dir(target_dir)
    refresh_result = skill.refresh_skills() if refresh else None
    return {
        "status": "ok",
        "path": str(skill_file.resolve()),
        "refresh": refresh_result,
    }


def create_user_skill(
    name: str,
    description: str,
    instructions: str,
    allowed_tools: list[str] | None = None,
    dependent_skills: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    refresh: bool = True,
) -> dict:
    """Create an ADK skill bundle under the user-global skill root.

    This helper is intentionally not exposed as an agent tool; agents should
    follow the skill-creation guide and use general execution tools for writes.
    """
    try:
        normalized = _validate_name(name)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    target_dir = _skill_dir(normalized)
    skill_file = target_dir / "SKILL.md"
    if skill_file.exists():
        return {
            "status": "error",
            "message": f"Skill '{normalized}' already exists at {skill_file}.",
        }

    content = _skill_content(
        normalized,
        description,
        instructions,
        allowed_tools,
        dependent_skills,
        metadata,
    )
    return _write_and_validate(target_dir, content, refresh=refresh)


def update_user_skill(
    name: str,
    description: str,
    instructions: str,
    allowed_tools: list[str] | None = None,
    dependent_skills: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    refresh: bool = True,
) -> dict:
    """Replace an existing user-global ADK skill bundle's ``SKILL.md``."""
    try:
        normalized = _validate_name(name)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    target_dir = _skill_dir(normalized)
    content = _skill_content(
        normalized,
        description,
        instructions,
        allowed_tools,
        dependent_skills,
        metadata,
    )
    return _write_and_validate(target_dir, content, refresh=refresh)
