from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    model_serializer,
    model_validator,
)


class Suit(StrEnum):
    Green = "Green"
    Acorns = "Acorns"
    Bells = "Bells"
    Red = "Red"


class Value(StrEnum):
    Six = "Six"
    Seven = "Seven"
    Eight = "Eight"
    Nine = "Nine"
    Unter = "Unter"
    Ober = "Ober"
    King = "King"
    Ten = "Ten"
    Ace = "Ace"


SUIT_TO_CHAR: dict[Suit, str] = {
    Suit.Green: "g",
    Suit.Acorns: "e",
    Suit.Bells: "s",
    Suit.Red: "r",
}
CHAR_TO_SUIT: dict[str, Suit] = {v: k for k, v in SUIT_TO_CHAR.items()}

VALUE_TO_CHAR: dict[Value, str] = {
    Value.Six: "6",
    Value.Seven: "7",
    Value.Eight: "8",
    Value.Nine: "9",
    Value.Unter: "U",
    Value.Ober: "O",
    Value.King: "K",
    Value.Ten: "Z",
    Value.Ace: "A",
}
CHAR_TO_VALUE: dict[str, Value] = {v: k for k, v in VALUE_TO_CHAR.items()}


class Card(BaseModel):
    model_config = ConfigDict(frozen=True)

    suit: Suit
    value: Value

    @model_serializer
    def _serialise(self) -> str:
        return f"{SUIT_TO_CHAR[self.suit]}-{VALUE_TO_CHAR[self.value]}"

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, data: Any) -> Any:
        if isinstance(data, str):
            if len(data) != 3 or data[1] != "-":
                raise ValueError(f"Invalid card format: {data!r}")
            suit = CHAR_TO_SUIT.get(data[0])
            value = CHAR_TO_VALUE.get(data[2])
            if suit is None or value is None:
                raise ValueError(f"Invalid card format: {data!r}")
            return {"suit": suit, "value": value}
        return data

    def __str__(self) -> str:
        return f"{SUIT_TO_CHAR[self.suit]}-{VALUE_TO_CHAR[self.value]}"

    def __repr__(self) -> str:
        return str(self)

    def __hash__(self) -> int:
        return hash((self.suit, self.value))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Card):
            return self.suit == other.suit and self.value == other.value
        return NotImplemented

    def __lt__(self, other: Card) -> bool:
        suits = list(Suit)
        values = list(Value)
        if self.suit != other.suit:
            return suits.index(self.suit) < suits.index(other.suit)
        return values.index(self.value) < values.index(other.value)

    def __le__(self, other: Card) -> bool:
        return self == other or self < other

    def __gt__(self, other: Card) -> bool:
        return not self <= other

    def __ge__(self, other: Card) -> bool:
        return not self < other


class PlaceAtTable(RootModel[int]):
    root: int = Field(ge=0, le=3)

    def partner(self) -> PlaceAtTable:
        return PlaceAtTable(root=(self.root + 2) % 4)

    def next(self) -> PlaceAtTable:
        return PlaceAtTable(root=(self.root + 1) % 4)

    def prev(self) -> PlaceAtTable:
        return PlaceAtTable(root=(self.root + 3) % 4)

    def party(self) -> PlaceAtTable:
        return PlaceAtTable(root=self.root % 2)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PlaceAtTable):
            return self.root == other.root
        if isinstance(other, int):
            return self.root == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.root)

    def __repr__(self) -> str:
        return f"Seat({self.root})"

    def __index__(self) -> int:
        return self.root


class Points(RootModel[int]):
    root: int

    def __add__(self, other: Points) -> Points:
        return Points(root=self.root + other.root)

    def __iadd__(self, other: Points) -> Points:
        return Points(root=self.root + other.root)

    def __sub__(self, other: Points) -> Points:
        return Points(root=self.root - other.root)

    def __ge__(self, other: Points) -> bool:
        return self.root >= other.root

    def __gt__(self, other: Points) -> bool:
        return self.root > other.root

    def __le__(self, other: Points) -> bool:
        return self.root <= other.root

    def __lt__(self, other: Points) -> bool:
        return self.root < other.root

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Points):
            return self.root == other.root
        if isinstance(other, int):
            return self.root == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.root)

    def __repr__(self) -> str:
        return f"Points({self.root})"
