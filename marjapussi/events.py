from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from marjapussi.actions import ActionType
from marjapussi.types import PlaceAtTable, Suit


class CallbackNewTrump(BaseModel):
    NewTrump: Suit


class CallbackStillTrump(BaseModel):
    StillTrump: Suit


class CallbackNoHalf(BaseModel):
    NoHalf: Suit


class CallbackOnlyHalf(BaseModel):
    OnlyHalf: Suit


GameCallback = CallbackNewTrump | CallbackStillTrump | CallbackNoHalf | CallbackOnlyHalf


class GameAction(BaseModel):
    action_type: ActionType
    player: PlaceAtTable


class GameEvent(BaseModel):
    last_action: GameAction
    callback: GameCallback | None = None
    player_at_turn: PlaceAtTable
    time: str


class GameEventPublic(BaseModel):
    PublicEvent: GameEvent


GameEventPlayer = Literal["HiddenEvent"] | GameEventPublic
