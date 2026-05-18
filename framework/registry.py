"""
SkillRegistry — discovers and caches all skills in the skills/ directory.

Responsibilities (S in SOLID):
  - Scan a directory for valid skill packages (folders containing SKILL.md)
  - Cache loaded skills by id
  - Provide thread-safe read access

The registry does not execute skills, validate prompts, or build graphs.
Those concerns belong to the engine and validator respectively.

Usage:
    registry = SkillRegistry(Path("backend/skills"))
    registry.load_all()
    skill = registry.get("architect")
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from framework.loader import LoadedSkill, SkillLoadError, SkillLoader

logger = logging.getLogger(__name__)


class SkillNotFoundError(KeyError):
    """Raised when a requested skill id is not in the registry."""


class SkillRegistry:
    """
    Thread-safe catalogue of all available skills.

    Skills are loaded eagerly via load_all() at startup.
    Individual skills can be reloaded at runtime via reload().
    """

    def __init__(
        self,
        skills_dir: Path,
        loader: SkillLoader | None = None,
    ) -> None:
        self._skills_dir = skills_dir.resolve()
        self._loader     = loader or SkillLoader()
        self._skills:    dict[str, LoadedSkill] = {}
        self._lock       = threading.RLock()

    # ── Public API ────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        """
        Discover and load every skill package under skills_dir.
        Logs a warning for packages that fail to load; does not raise.
        """
        if not self._skills_dir.is_dir():
            logger.warning("Skills directory not found: %s", self._skills_dir)
            return

        candidates = [p for p in sorted(self._skills_dir.iterdir())
                      if p.is_dir() and (p / "SKILL.md").exists()]

        with self._lock:
            for skill_dir in candidates:
                self._load_one(skill_dir)

        logger.info(
            "Skill registry ready — %d skill(s) loaded: %s",
            len(self._skills),
            list(self._skills.keys()),
        )

    def get(self, skill_id: str) -> LoadedSkill:
        """Return a loaded skill by id.  Raises SkillNotFoundError if absent."""
        with self._lock:
            if skill_id not in self._skills:
                available = sorted(self._skills)
                raise SkillNotFoundError(
                    f"Skill '{skill_id}' not found. Available: {available}"
                )
            return self._skills[skill_id]

    def list_all(self) -> list[LoadedSkill]:
        """Return all loaded skills, sorted by id."""
        with self._lock:
            return sorted(self._skills.values(), key=lambda s: s.manifest.id)

    def reload(self, skill_id: str) -> LoadedSkill:
        """
        Force-reload a single skill from disk.
        Useful after publishing new prompt versions or editing SKILL.md.
        """
        skill_dir = self._skills_dir / skill_id
        if not skill_dir.is_dir():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")

        with self._lock:
            skill = self._loader.load(skill_dir)
            self._skills[skill_id] = skill
            logger.info("Reloaded skill '%s'", skill_id)
            return skill

    def __contains__(self, skill_id: str) -> bool:
        with self._lock:
            return skill_id in self._skills

    def __len__(self) -> int:
        with self._lock:
            return len(self._skills)

    # ── Private ───────────────────────────────────────────────────────────────

    def _load_one(self, skill_dir: Path) -> None:
        try:
            skill = self._loader.load(skill_dir)
            self._skills[skill.manifest.id] = skill
            logger.debug(
                "Loaded skill '%s' v%d from %s",
                skill.manifest.id,
                skill.manifest.version,
                skill_dir.name,
            )
        except SkillLoadError as exc:
            logger.error("Skill load failed [%s]: %s", skill_dir.name, exc)
