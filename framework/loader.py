"""
SkillLoader — reads a skill directory from disk into an immutable LoadedSkill.

Responsibilities (S in SOLID):
  - Parse SKILL.md (frontmatter + stage sections)
  - Read agents/, references/, assets/ files into memory
  - Validate completeness (every stage has an agent file)
  - Return a frozen value object; never write to disk

The loader knows nothing about LangGraph, LLMs, or sessions.
It only knows how to turn a directory into a data structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from framework.schema import SkillManifest, StageConfig, FanoutBranch


# ── Value object ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LoadedSkill:
    """
    Immutable snapshot of a skill package loaded from disk.

    Frozen so the engine and strategies can hold references without risk
    of mutation.  All collections are plain dicts/strings — no live file handles.
    """

    manifest:   SkillManifest
    skill_dir:  Path
    agents:     dict[str, str]  # agent_key → prompt content
    references: dict[str, str]  # filename stem → content
    assets:     dict[str, str]  # filename stem → content

    # ── Convenience accessors ─────────────────────────────────────────────────

    def agent_prompt(self, key: str, fallback: str = "") -> str:
        """Return the prompt for an agent key."""
        return self.agents.get(key, fallback)

    def reference(self, name: str, fallback: str = "") -> str:
        """Return the content of a reference document."""
        return self.references.get(name, fallback)

    def asset(self, name: str, fallback: str = "") -> str:
        """Return the content of an asset file."""
        return self.assets.get(name, fallback)

    @property
    def all_agent_prompts(self) -> dict[str, str]:
        """All agent prompts keyed by agent_key — used for DB seeding."""
        return dict(self.agents)


# ── Exceptions ────────────────────────────────────────────────────────────────

class SkillLoadError(ValueError):
    """Raised when a skill directory cannot be loaded or validated."""


# ── Loader ────────────────────────────────────────────────────────────────────

class SkillLoader:
    """
    Loads a skill from a directory that follows the standard layout:

        skills/<id>/
            SKILL.md          ← required — manifest + pipeline definition
            agents/           ← required — one .md per agent
            references/       ← optional — curated knowledge documents
            assets/           ← optional — templates, CSS, output formats

    Usage:
        skill = SkillLoader().load(Path("skills/architect"))
    """

    def load(self, skill_dir: Path) -> LoadedSkill:
        skill_dir = skill_dir.resolve()

        if not skill_dir.is_dir():
            raise SkillLoadError(f"Skill directory not found: {skill_dir}")

        manifest   = self._parse_manifest(skill_dir / "SKILL.md")
        agents     = self._read_directory(skill_dir / "agents",     "*.md")
        references = self._read_directory(skill_dir / "references", "*.md")
        assets     = self._read_directory(skill_dir / "assets",     "*")

        self._assert_agents_present(manifest, agents, skill_dir)

        return LoadedSkill(
            manifest   = manifest,
            skill_dir  = skill_dir,
            agents     = agents,
            references = references,
            assets     = assets,
        )

    # ── Manifest parsing ──────────────────────────────────────────────────────

    def _parse_manifest(self, path: Path) -> SkillManifest:
        if not path.exists():
            raise SkillLoadError(f"SKILL.md not found at {path}")

        text = path.read_text(encoding="utf-8")

        meta     = self._parse_frontmatter(text, path)
        pipeline = self._parse_pipeline(text, path)
        stages   = self._parse_stages(text, path)

        try:
            return SkillManifest(pipeline=pipeline, stages=stages, **meta)
        except Exception as exc:
            raise SkillLoadError(f"SKILL.md at {path} failed validation: {exc}") from exc

    @staticmethod
    def _parse_frontmatter(text: str, path: Path) -> dict:
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not match:
            raise SkillLoadError(f"SKILL.md at {path} is missing YAML frontmatter (--- ... ---)")
        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise SkillLoadError(f"Invalid frontmatter YAML in {path}: {exc}") from exc

    @staticmethod
    def _parse_pipeline(text: str, path: Path) -> list[str]:
        match = re.search(
            r"^## Pipeline\s*\n(.+?)(?=\n##|\Z)", text, re.DOTALL | re.MULTILINE
        )
        if not match:
            raise SkillLoadError(f"SKILL.md at {path} is missing a '## Pipeline' section")

        # First non-blank line: "intake → discovery → research → review → approval"
        line = next(
            (l.strip() for l in match.group(1).splitlines() if l.strip()),
            "",
        )
        stages = [s.strip() for s in line.split("→") if s.strip()]
        if not stages:
            raise SkillLoadError(f"## Pipeline section in {path} is empty")
        return stages

    @staticmethod
    def _parse_stages(text: str, path: Path) -> dict[str, StageConfig]:
        stages  = {}
        pattern = re.compile(
            r"^## Stage:\s*(\S+)\s*\n(.*?)(?=\n## |\Z)",
            re.DOTALL | re.MULTILINE,
        )
        for match in pattern.finditer(text):
            stage_id = match.group(1).strip()
            body     = match.group(2).strip()
            try:
                config = yaml.safe_load(body) or {}
            except yaml.YAMLError as exc:
                raise SkillLoadError(
                    f"Invalid YAML in '## Stage: {stage_id}' in {path}: {exc}"
                ) from exc
            try:
                stages[stage_id] = StageConfig(id=stage_id, **config)
            except Exception as exc:
                raise SkillLoadError(
                    f"Stage '{stage_id}' in {path} failed validation: {exc}"
                ) from exc

        return stages

    # ── File loading ──────────────────────────────────────────────────────────

    @staticmethod
    def _read_directory(directory: Path, pattern: str) -> dict[str, str]:
        if not directory.is_dir():
            return {}
        return {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(directory.glob(pattern))
            if p.is_file()
        }

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _assert_agents_present(
        manifest: SkillManifest,
        agents: dict[str, str],
        skill_dir: Path,
    ) -> None:
        """Every agent key referenced by the manifest must have an agents/*.md file."""
        for stage in manifest.stages.values():
            if stage.execution == "fanout_merge":
                # Check all fanout branches and the merge agent
                for branch in (stage.fanout or []):
                    if branch.agent not in agents:
                        raise SkillLoadError(
                            f"Fanout branch references agent '{branch.agent}' "
                            f"but agents/{branch.agent}.md not found in {skill_dir}"
                        )
                if stage.merge and stage.merge.agent not in agents:
                    raise SkillLoadError(
                        f"Merge step references agent '{stage.merge.agent}' "
                        f"but agents/{stage.merge.agent}.md not found in {skill_dir}"
                    )
            elif stage.execution == "intake":
                for key in (stage.agents or {}).values():
                    if key not in agents:
                        raise SkillLoadError(
                            f"Intake stage references agent '{key}' "
                            f"but agents/{key}.md not found in {skill_dir}"
                        )
            else:
                key = stage.agent_key
                if key not in agents:
                    raise SkillLoadError(
                        f"Stage '{stage.id}' references agent '{key}' "
                        f"but agents/{key}.md not found in {skill_dir}"
                    )
