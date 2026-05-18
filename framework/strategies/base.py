"""
ExecutionStrategy — the extension point for all agent execution patterns.

SOLID applied here:
  O (Open/Closed):   new patterns are added by subclassing, not editing
  L (Liskov):        any strategy can replace any other in the engine
  I (Interface Seg): the interface is minimal — name + build_node only
  D (Dep. Inversion): engine depends on this abstraction, not concretions

Registering a new strategy:
    from framework.strategies.base import StrategyRegistry, ExecutionStrategy

    class MyStrategy(ExecutionStrategy):
        @property
        def name(self) -> str:
            return "my_strategy"

        def build_node(self, stage, skill):
            def node(state):
                ...
            return node

    StrategyRegistry.register(MyStrategy())
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from framework.loader import LoadedSkill
    from framework.schema import StageConfig
    from state import AgentState

logger = logging.getLogger(__name__)


# ── Abstract base ─────────────────────────────────────────────────────────────

class ExecutionStrategy(ABC):
    """
    Abstract base for all pipeline execution strategies.

    Implementations produce a LangGraph node function (a plain callable that
    takes AgentState and returns a partial state update dict).  The strategy
    itself holds no mutable state — it is instantiated once and reused across
    all sessions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique strategy identifier.
        Must match the value used in SKILL.md  execution: <name>  fields.
        """
        ...

    @abstractmethod
    def build_node(
        self,
        stage: "StageConfig",
        skill: "LoadedSkill",
    ) -> Callable[["AgentState"], dict]:
        """
        Return a LangGraph node function for this stage.

        The returned callable:
          - receives the current AgentState (read-only by convention)
          - returns a partial state update dict (LangGraph merges it)
          - may call LangGraph interrupt() to pause execution
          - must not mutate state in place
        """
        ...


# ── Registry ──────────────────────────────────────────────────────────────────

class StrategyRegistry:
    """
    Maps strategy names → strategy instances.

    Populated at import time when strategy modules register themselves.
    The engine depends on this registry, not on individual strategy classes
    (Dependency Inversion Principle).
    """

    _strategies: dict[str, ExecutionStrategy] = {}

    @classmethod
    def register(cls, strategy: ExecutionStrategy) -> None:
        """Register a strategy.  Raises if a strategy with the same name exists."""
        if strategy.name in cls._strategies:
            raise ValueError(
                f"Strategy '{strategy.name}' is already registered. "
                "Use a unique name or unregister the existing one first."
            )
        cls._strategies[strategy.name] = strategy
        logger.debug("Registered execution strategy '%s'", strategy.name)

    @classmethod
    def get(cls, name: str) -> ExecutionStrategy:
        """Return the strategy for the given name.  Raises ValueError if absent."""
        if name not in cls._strategies:
            available = sorted(cls._strategies)
            raise ValueError(
                f"Unknown execution strategy '{name}'. "
                f"Available strategies: {available}"
            )
        return cls._strategies[name]

    @classmethod
    def available(cls) -> list[str]:
        """Return all registered strategy names."""
        return sorted(cls._strategies)
