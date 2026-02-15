from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from marjapussi.v2.types import Card, PlaceAtTable, Points, Suit

# ── QuestionType (Serde externally-tagged) ───────────────────────


class QuestionYourHalf(BaseModel):
    YourHalf: Suit


QuestionType = Literal["Yours"] | QuestionYourHalf


# ── AnswerType (Serde externally-tagged) ─────────────────────────


class AnswerYesPair(BaseModel):
    YesPair: Suit


class AnswerYesHalf(BaseModel):
    YesHalf: Suit


class AnswerNoHalf(BaseModel):
    NoHalf: Suit


AnswerType = Literal["NoPair"] | AnswerYesPair | AnswerYesHalf | AnswerNoHalf


# ── ActionType (Serde externally-tagged) ─────────────────────────


class ActionNewBid(BaseModel):
    NewBid: int


class ActionPass(BaseModel):
    Pass: list[Card]


class ActionCardPlayed(BaseModel):
    CardPlayed: Card


class ActionQuestion(BaseModel):
    Question: QuestionType


class ActionAnswer(BaseModel):
    Answer: AnswerType


class ActionAnnounceTrump(BaseModel):
    AnnounceTrump: Suit


ActionType = (
    Literal[
        "Start",
        "StopBidding",
        "UndoRequest",
        "UndoDecline",
        "UndoAccept",
    ]
    | ActionNewBid
    | ActionPass
    | ActionCardPlayed
    | ActionQuestion
    | ActionAnswer
    | ActionAnnounceTrump
)


# ── GameCallback (Serde externally-tagged) ───────────────────────


class CallbackNewTrump(BaseModel):
    NewTrump: Suit


class CallbackStillTrump(BaseModel):
    StillTrump: Suit


class CallbackNoHalf(BaseModel):
    NoHalf: Suit


class CallbackOnlyHalf(BaseModel):
    OnlyHalf: Suit


GameCallback = CallbackNewTrump | CallbackStillTrump | CallbackNoHalf | CallbackOnlyHalf


# ── GameAction / GameEvent ───────────────────────────────────────


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


# ── FinishedTrick ────────────────────────────────────────────────


class FinishedTrick(BaseModel):
    cards: tuple[Card, Card, Card, Card]
    winner: PlaceAtTable
    points: Points


# ── GamePhase (Serde externally-tagged) ──────────────────────────


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


# ── GameMetaInfo ─────────────────────────────────────────────────


class GameMetaInfo(BaseModel):
    name: str
    create_time: str
    start_time: str | None = None
    end_time: str | None = None
    player_names: tuple[str, str, str, str]
    player_start_cards: tuple[list[Card], list[Card], list[Card], list[Card]]


# ── GameFinishedInfo ─────────────────────────────────────────────


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


# ── Internal state models ────────────────────────────────────────


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


# ── Series ───────────────────────────────────────────────────────


class SeriesSettings(BaseModel):
    games: int = 4
    schwarzfactor_fifths: int = 10
    shuffle_players: bool = True
    bonus_at: int = 500
    bonus_value: int = 300
    diff_plus_minus: bool = True
    diff_divisor: int = 5


class Series(BaseModel):
    name: str
    created: str
    finished: str | None = None
    num_of_games: int
    games: list[Game]
    players_names: tuple[str, str, str, str]
    settings: SeriesSettings = Field(default_factory=SeriesSettings)


# ── LegacyGameFormat ─────────────────────────────────────────────


class LegacyGameFormat(BaseModel):
    model_config = {"populate_by_name": True}

    id: str = Field(alias="_id")
    name: str
    created: str
    started: str
    finished: str
    players: list[str]
    cards: dict[str, list[str]]
    game_value: int
    actions: list[str]
    players_sup: dict[str, list[str]]
    players_points: dict[str, int]
    tricks: list[list[str]]
    schwarz_game: bool = False
