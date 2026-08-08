from __future__ import annotations

from abc import ABC, abstractmethod

from marjapussi.events import GameAction
from marjapussi.state import GameInfoPlayer
from marjapussi.types import PlaceAtTable


class Agent(ABC):
    """Plays one seat; the runner sets place before the first observe call."""

    place: PlaceAtTable

    @abstractmethod
    def select_action(self, view: GameInfoPlayer) -> GameAction:
        """Pick one action from view.legal_actions."""

    def observe(self, view: GameInfoPlayer) -> None:  # noqa: B027 - optional hook
        """Receive this agent's view of the initial state and after every action."""
