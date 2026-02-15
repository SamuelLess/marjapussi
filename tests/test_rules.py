from __future__ import annotations

from marjapussi.rules import (
    allowed_cards,
    allowed_first_trick,
    card_points,
    contains_half,
    contains_pair,
    deck,
    high_card,
    sorted_cards,
    trick_points,
    trick_winner,
)
from marjapussi.types import Card, PlaceAtTable, Suit


def _c(s: str) -> Card:
    return Card.model_validate(s)


class TestDeck:
    def test_deck_has_36_cards(self) -> None:
        assert len(deck()) == 36

    def test_deck_unique(self) -> None:
        d = deck()
        assert len(set(d)) == 36


class TestCardPoints:
    def test_ace_is_11(self) -> None:
        assert card_points(_c("r-A")) == 11

    def test_ten_is_10(self) -> None:
        assert card_points(_c("s-Z")) == 10

    def test_six_is_0(self) -> None:
        assert card_points(_c("g-6")) == 0


class TestHighCard:
    def test_highest_in_lead_suit(self) -> None:
        cards = [_c("r-7"), _c("r-A"), _c("r-K")]
        assert high_card(cards) == _c("r-A")

    def test_trump_beats_lead(self) -> None:
        cards = [_c("r-A"), _c("g-6")]
        assert high_card(cards, trump=Suit.Green) == _c("g-6")

    def test_no_trump_off_suit_ignored(self) -> None:
        cards = [_c("r-7"), _c("g-A")]
        assert high_card(cards) == _c("r-7")


class TestTrickWinner:
    def test_simple_trick(self) -> None:
        trick = [_c("r-7"), _c("r-A"), _c("r-K"), _c("r-6")]
        winner = trick_winner(trick, None, PlaceAtTable(root=0))
        assert winner == PlaceAtTable(root=1)

    def test_trump_trick(self) -> None:
        trick = [_c("r-A"), _c("g-6"), _c("r-K"), _c("r-Z")]
        winner = trick_winner(trick, Suit.Green, PlaceAtTable(root=2))
        assert winner == PlaceAtTable(root=3)


class TestTrickPoints:
    def test_normal_trick(self) -> None:
        trick = [_c("r-A"), _c("r-Z"), _c("r-K"), _c("r-6")]
        assert trick_points(trick) == 25

    def test_last_trick_bonus(self) -> None:
        trick = [_c("g-6"), _c("g-7"), _c("g-8"), _c("g-9")]
        assert trick_points(trick, last=True) == 20


class TestContainsPair:
    def test_has_pair(self) -> None:
        hand = [_c("r-K"), _c("r-O"), _c("g-6")]
        assert contains_pair(hand, Suit.Red)

    def test_no_pair(self) -> None:
        hand = [_c("r-K"), _c("g-O"), _c("g-6")]
        assert not contains_pair(hand, Suit.Red)


class TestContainsHalf:
    def test_has_king(self) -> None:
        hand = [_c("r-K"), _c("g-6")]
        assert contains_half(hand, Suit.Red)

    def test_has_ober(self) -> None:
        hand = [_c("r-O"), _c("g-6")]
        assert contains_half(hand, Suit.Red)

    def test_no_half(self) -> None:
        hand = [_c("r-A"), _c("g-6")]
        assert not contains_half(hand, Suit.Red)


class TestAllowedFirstTrick:
    def test_must_play_ace(self) -> None:
        hand = [_c("r-A"), _c("g-7"), _c("s-K")]
        assert allowed_first_trick(hand) == [_c("r-A")]

    def test_no_ace_play_green(self) -> None:
        hand = [_c("g-7"), _c("s-K"), _c("r-9")]
        assert allowed_first_trick(hand) == [_c("g-7")]

    def test_no_ace_no_green_play_any(self) -> None:
        hand = [_c("s-K"), _c("r-9")]
        assert allowed_first_trick(hand) == hand


class TestAllowedCards:
    def test_must_follow_suit(self) -> None:
        trick = [_c("r-A")]
        hand = [_c("r-7"), _c("g-K"), _c("s-6")]
        result = allowed_cards(trick, hand, None)
        assert result == [_c("r-7")]

    def test_no_follow_play_trump(self) -> None:
        trick = [_c("r-A")]
        hand = [_c("g-K"), _c("s-6")]
        result = allowed_cards(trick, hand, Suit.Green)
        assert result == [_c("g-K")]

    def test_empty_trick_all_cards(self) -> None:
        hand = [_c("r-7"), _c("g-K")]
        result = allowed_cards([], hand, None)
        assert result == hand

    def test_first_trick_ace_of_lead(self) -> None:
        trick = [_c("r-7")]
        hand = [_c("r-A"), _c("r-K")]
        result = allowed_cards(trick, hand, None, first_trick=True)
        assert result == [_c("r-A")]


class TestSortedCards:
    def test_canonical_order(self) -> None:
        cards = [_c("g-A"), _c("r-6"), _c("s-K")]
        result = sorted_cards(cards)
        assert result[0] == _c("r-6")
        assert result[-1] == _c("g-A")
