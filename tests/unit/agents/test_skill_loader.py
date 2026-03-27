"""Tests for Phase 8 skill loading and activation."""
from __future__ import annotations

from pathlib import Path

import pytest

from breqy.agents.skills import SkillActivationError, SkillLoader


def _write_skill(
    root: Path,
    *,
    skill_id: str,
    instructions_file: str = "instructions.md",
    description: str = "Skill description",
    required_tools: list[str] | None = None,
    instructions: str = "Follow the skill instructions.",
) -> Path:
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    manifest_lines = [
        f"id: {skill_id}",
        f"description: {description}",
        f"instructions_file: {instructions_file}",
    ]
    if required_tools is not None:
        manifest_lines.append("required_tools:")
        manifest_lines.extend(f"  - {tool}" for tool in required_tools)
    (skill_dir / "skill.yaml").write_text("\n".join(manifest_lines) + "\n")
    (skill_dir / instructions_file).write_text(instructions)
    return skill_dir


def test_skill_loader_discovers_skills_from_top_level_root(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    compatibility_root = tmp_path / "system" / "skills"
    _write_skill(skills_root, skill_id="plan")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=compatibility_root)

    skills = loader.discover_allowed(
        skill_permissions=["plan"],
        tool_permissions=[],
    )

    assert list(skills) == ["plan"]
    assert skills["plan"].instructions == "Follow the skill instructions."
    assert skills["plan"].source_root == skills_root


def test_skill_loader_uses_compatibility_root_when_top_level_skill_missing(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    compatibility_root = tmp_path / "system" / "skills"
    _write_skill(compatibility_root, skill_id="review")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=compatibility_root)

    skills = loader.discover_allowed(
        skill_permissions=["review"],
        tool_permissions=[],
    )

    assert list(skills) == ["review"]
    assert skills["review"].source_root == compatibility_root


def test_skill_loader_prefers_top_level_root_over_compatibility_root(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    compatibility_root = tmp_path / "system" / "skills"
    _write_skill(skills_root, skill_id="review", instructions="top-level")
    _write_skill(compatibility_root, skill_id="review", instructions="compatibility")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=compatibility_root)

    skills = loader.discover_allowed(
        skill_permissions=["review"],
        tool_permissions=[],
    )

    assert skills["review"].instructions == "top-level"
    assert skills["review"].source_root == skills_root


def test_skill_loader_rejects_invalid_manifest_shape(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.yaml").write_text("description: missing-id\n")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="id"):
        loader.discover_allowed(skill_permissions=["broken"], tool_permissions=[])


def test_skill_loader_rejects_instructions_file_outside_skill_directory(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="escape", instructions_file="../outside.md")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="within the skill directory"):
        loader.discover_allowed(skill_permissions=["escape"], tool_permissions=[])


def test_skill_loader_rejects_non_markdown_instructions_file(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="text-skill", instructions_file="instructions.txt")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="Markdown"):
        loader.discover_allowed(skill_permissions=["text-skill"], tool_permissions=[])


def test_skill_loader_rejects_absolute_instructions_file_path(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    absolute_path = tmp_path / "outside.md"
    _write_skill(skills_root, skill_id="absolute", instructions_file=str(absolute_path))

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="within the skill directory"):
        loader.discover_allowed(skill_permissions=["absolute"], tool_permissions=[])


def test_skill_loader_rejects_missing_instructions_file(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = _write_skill(skills_root, skill_id="missing")
    (skill_dir / "instructions.md").unlink()

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="instructions file is missing"):
        loader.discover_allowed(skill_permissions=["missing"], tool_permissions=[])


def test_skill_loader_rejects_manifest_id_mismatch(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = _write_skill(skills_root, skill_id="plan")
    (skill_dir / "skill.yaml").write_text("id: review\ndescription: bad\ninstructions_file: instructions.md\n")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="id mismatch"):
        loader.discover_allowed(skill_permissions=["plan"], tool_permissions=[])


def test_skill_loader_unknown_allowed_skill_raises_structured_error(tmp_path) -> None:
    loader = SkillLoader(skills_root=tmp_path / "skills", compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(SkillActivationError) as exc_info:
        loader.discover_allowed(skill_permissions=["missing"], tool_permissions=[])

    assert exc_info.value.payload.details == {"invalid_skill_ids": ["missing"]}


def test_skill_loader_rejects_skill_when_required_tools_are_disallowed(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="shell-plan", required_tools=["shell"])

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(ValueError, match="required tools"):
        loader.discover_allowed(skill_permissions=["shell-plan"], tool_permissions=["filesystem"])


def test_skill_loader_allows_wildcard_skill_permissions(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="plan")
    _write_skill(skills_root, skill_id="review")

    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    skills = loader.discover_allowed(skill_permissions=["*"], tool_permissions=[])

    assert set(skills) == {"plan", "review"}


def test_skill_loader_rejects_unknown_active_skill_ids_with_structured_error(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="plan")
    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(SkillActivationError) as exc_info:
        loader.resolve_active(
            active_skill_ids=["unknown-skill"],
            skill_permissions=["plan"],
            tool_permissions=[],
        )

    assert exc_info.value.payload.code == "invalid_skill_activation"
    assert exc_info.value.payload.details == {"invalid_skill_ids": ["unknown-skill"]}


def test_skill_loader_rejects_disallowed_active_skill_ids_with_structured_error(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="plan")
    _write_skill(skills_root, skill_id="review")
    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    with pytest.raises(SkillActivationError) as exc_info:
        loader.resolve_active(
            active_skill_ids=["review"],
            skill_permissions=["plan"],
            tool_permissions=[],
        )

    assert exc_info.value.payload.code == "invalid_skill_activation"
    assert exc_info.value.payload.details == {"invalid_skill_ids": ["review"]}


def test_skill_loader_resolves_only_requested_active_skills(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(skills_root, skill_id="plan")
    _write_skill(skills_root, skill_id="review")
    loader = SkillLoader(skills_root=skills_root, compatibility_root=tmp_path / "system" / "skills")

    active_skills = loader.resolve_active(
        active_skill_ids=["review"],
        skill_permissions=["*"],
        tool_permissions=[],
    )

    assert [skill.id for skill in active_skills] == ["review"]
