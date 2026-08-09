from __future__ import annotations

from pydantic import BaseModel, Field

from marjapussi.state import Game


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
