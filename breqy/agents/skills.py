"""Skill discovery and activation helpers for agent runtime."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from breqy.domain.models import StructuredErrorPayload


class SkillDefinition(BaseModel):
    id: str
    description: str
    instructions_file: str
    required_tools: list[str] = Field(default_factory=list)


class LoadedSkill(BaseModel):
    id: str
    description: str
    instructions: str
    required_tools: list[str] = Field(default_factory=list)
    source_root: Path
    skill_dir: Path


class SkillActivationError(Exception):
    def __init__(self, payload: StructuredErrorPayload) -> None:
        super().__init__(payload.message)
        self.payload = payload


class SkillLoader:
    def __init__(self, *, skills_root: Path, compatibility_root: Path) -> None:
        self._skills_root = skills_root
        self._compatibility_root = compatibility_root

    def discover_allowed(
        self,
        *,
        skill_permissions: list[str],
        tool_permissions: list[str],
    ) -> dict[str, LoadedSkill]:
        requested_skill_ids = self._discoverable_skill_ids(skill_permissions)
        allowed_tools = set(tool_permissions)
        loaded: dict[str, LoadedSkill] = {}

        for skill_id in sorted(requested_skill_ids):
            skill = self._load_skill(skill_id)
            missing_tools = [tool for tool in skill.required_tools if tool not in allowed_tools]
            if missing_tools:
                raise ValueError(
                    f"skill {skill_id!r} requires required tools that are not permitted: {missing_tools}"
                )
            loaded[skill_id] = skill

        return loaded

    def resolve_active(
        self,
        *,
        active_skill_ids: list[str],
        skill_permissions: list[str],
        tool_permissions: list[str],
    ) -> list[LoadedSkill]:
        allowed = self.discover_allowed(
            skill_permissions=skill_permissions,
            tool_permissions=tool_permissions,
        )
        invalid_skill_ids = [skill_id for skill_id in active_skill_ids if skill_id not in allowed]
        if invalid_skill_ids:
            raise SkillActivationError(
                StructuredErrorPayload(
                    code="invalid_skill_activation",
                    message="One or more requested skills are unknown or disallowed for this agent",
                    details={"invalid_skill_ids": invalid_skill_ids},
                )
            )
        return [allowed[skill_id] for skill_id in active_skill_ids]

    def _discoverable_skill_ids(self, skill_permissions: list[str]) -> set[str]:
        if skill_permissions == ["*"]:
            return self._all_skill_ids()
        return set(skill_permissions)

    def _all_skill_ids(self) -> set[str]:
        skill_ids: set[str] = set()
        for root in (self._compatibility_root, self._skills_root):
            if not root.exists():
                continue
            for manifest_path in root.glob("*/skill.yaml"):
                skill_ids.add(manifest_path.parent.name)
        return skill_ids

    def _load_skill(self, skill_id: str) -> LoadedSkill:
        skill_dir, source_root = self._resolve_skill_dir(skill_id)
        manifest_path = skill_dir / "skill.yaml"
        with open(manifest_path) as manifest_file:
            manifest_data = yaml.safe_load(manifest_file) or {}
        definition = SkillDefinition.model_validate(manifest_data)
        if definition.id != skill_id:
            raise ValueError(f"skill manifest id mismatch: expected {skill_id!r}, got {definition.id!r}")
        instructions_path = self._resolve_instructions_path(skill_dir, definition.instructions_file)
        if not instructions_path.exists() or instructions_path.is_dir():
            raise ValueError(f"skill {skill_id!r} instructions file is missing: {instructions_path}")
        with open(instructions_path) as instructions_file:
            instructions = instructions_file.read()
        return LoadedSkill(
            id=definition.id,
            description=definition.description,
            instructions=instructions,
            required_tools=definition.required_tools,
            source_root=source_root,
            skill_dir=skill_dir,
        )

    def _resolve_skill_dir(self, skill_id: str) -> tuple[Path, Path]:
        primary_dir = self._skills_root / skill_id
        if (primary_dir / "skill.yaml").exists():
            return primary_dir, self._skills_root

        compatibility_dir = self._compatibility_root / skill_id
        if (compatibility_dir / "skill.yaml").exists():
            return compatibility_dir, self._compatibility_root

        raise SkillActivationError(
            StructuredErrorPayload(
                code="invalid_skill_activation",
                message="One or more requested skills are unknown or disallowed for this agent",
                details={"invalid_skill_ids": [skill_id]},
            )
        )

    def _resolve_instructions_path(self, skill_dir: Path, instructions_file: str) -> Path:
        instructions_relative_path = Path(instructions_file)
        if instructions_relative_path.is_absolute():
            raise ValueError("instructions_file must stay within the skill directory")
        if instructions_relative_path.suffix.lower() != ".md":
            raise ValueError("instructions_file must reference a Markdown file")

        instructions_path = (skill_dir / instructions_relative_path).resolve()
        try:
            instructions_path.relative_to(skill_dir.resolve())
        except ValueError as exc:
            raise ValueError("instructions_file must stay within the skill directory") from exc
        return instructions_path
