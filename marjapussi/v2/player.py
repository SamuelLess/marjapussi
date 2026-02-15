from __future__ import annotations

from pydantic import BaseModel, Field

from marjapussi.v2.rules import (
    CARD_POINTS,
    LAST_TRICK_BONUS,
    sorted_cards,
    suit_points,
)
from marjapussi.v2.types import Card, PlaceAtTable, Suit


class PlayerState(BaseModel):
    place: PlaceAtTable
    name: str
    hand: list[Card]
    tricks_won: list[list[Card]] = Field(default_factory=list)
    points: int = 0
    still_bidding: bool = True
    trump_calls: list[Suit] = Field(default_factory=list)
    asking_level: int = 0

    def give_card(self, card: Card) -> None:
        self.hand.append(card)
        self.hand = sorted_cards(self.hand)

    def remove_card(self, card: Card) -> None:
        self.hand = [c for c in self.hand if c != card]

    def take_trick(self, trick: list[Card], *, last: bool = False) -> None:
        self.tricks_won.append(trick)
        self.points += sum(CARD_POINTS[c.value] for c in trick)
        if last:
            self.points += LAST_TRICK_BONUS

    def call_trump(self, suit: Suit) -> None:
        if suit in self.trump_calls:
            return
        self.trump_calls.append(suit)
        self.points += suit_points(suit)
