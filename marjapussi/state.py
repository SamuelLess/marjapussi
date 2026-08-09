from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from marjapussi.actions import ActionType
from marjapussi.events import GameAction, GameEvent, GameEventPlayer
from marjapussi.types import Card, PlaceAtTable, Points, Suit


class FinishedTrick(BaseModel):
    cards: tuple[Card, Card, Card, Card]
    winner: PlaceAtTable
    points: Points


class GamePhaseAnsweringHalf(BaseModel):
    AnsweringHalf: Suit


class GamePhasePendingUndo(BaseModel):
    PendingUndo: GamePhase  # forward ref resolved below


GamePhase = (
    Literal[
        "WaitingForStart",
        "Bidding",
        "PassingForth",
        "PassingBack",
        "Raising",
        "Trick",
        "StartTrick",
        "AnsweringPair",
        "Ended",
    ]
    | GamePhaseAnsweringHalf
    | GamePhasePendingUndo
)

GamePhasePendingUndo.model_rebuild()


class GameMetaInfo(BaseModel):
    name: str
    create_time: str
    start_time: str | None = None
    end_time: str | None = None
    player_names: tuple[str, str, str, str]
    player_start_cards: tuple[list[Card], list[Card], list[Card], list[Card]]


class GameFinishedInfo(BaseModel):
    info: GameMetaInfo
    game_value: Points
    won: bool | None = None
    no_one_played: bool
    schwarz_game: bool
    playing_party: PlaceAtTable | None = None
    after_passing: tuple[list[Card], list[Card], list[Card], list[Card]] | None = None
    passed_cards: tuple[list[Card], list[Card]] | None = None
    bidding_history: list[tuple[ActionType, PlaceAtTable]]
    tricks: list[FinishedTrick]
    all_events: list[GameEvent]


class PlayerTrumpPossibilities(StrEnum):
    Own = "Own"
    Yours = "Yours"
    Ours = "Ours"


class GameError(StrEnum):
    IllegalAction = "IllegalAction"
    CannotUndo = "CannotUndo"


class Player(BaseModel):
    name: str
    partner: PlaceAtTable
    next_player: PlaceAtTable
    place_at_table: PlaceAtTable
    cards: list[Card]
    last_played: Card | None = None
    tricks: list[list[Card]] = Field(default_factory=list)
    trump: PlayerTrumpPossibilities = PlayerTrumpPossibilities.Own
    bidding: bool = True


class GameState(BaseModel):
    phase: GamePhase
    started: bool = False
    players_started: list[PlaceAtTable] = Field(default_factory=list)
    players_accept_undo: list[PlaceAtTable] = Field(default_factory=list)
    bidding_players: int = 4
    bidding_history: list[tuple[ActionType, PlaceAtTable]] = Field(default_factory=list)
    trump: Suit | None = None
    trump_called: list[Suit] = Field(default_factory=list)
    player_at_turn: PlaceAtTable
    players: tuple[Player, Player, Player, Player]
    value: Points
    all_tricks: list[FinishedTrick] = Field(default_factory=list)
    current_trick: list[Card] = Field(default_factory=list)


class GameInfoPlayer(BaseModel):
    meta_info: GameMetaInfo
    players_pressed_start: list[str]
    players_from_perspective: tuple[str, str, str, str]
    player_at_turn: str
    own_cards: list[Card] | None = None
    players_cards_number_perspective: tuple[int, int, int, int]
    game_phase: GamePhase
    bidding_history: list[tuple[ActionType, PlaceAtTable]]
    current_trick: list[Card]
    last_trick: FinishedTrick | None = None
    last_event: GameEventPlayer | None = None
    legal_actions: list[GameAction]


class Game(BaseModel):
    info: GameMetaInfo
    state: GameState
    legal_actions: list[GameAction]
    last_state: GameState | None = None
    all_events: list[GameEvent] = Field(default_factory=list)
