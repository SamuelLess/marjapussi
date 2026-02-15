from __future__ import annotations

from marjapussi.v2.types import Card, PlaceAtTable, Suit, Value

VALUE_ORDER: list[Value] = list(Value)

CARD_POINTS: dict[Value, int] = {
    Value.Ace: 11,
    Value.Ten: 10,
    Value.King: 4,
    Value.Ober: 3,
    Value.Unter: 2,
    Value.Nine: 0,
    Value.Eight: 0,
    Value.Seven: 0,
    Value.Six: 0,
}

SUIT_POINTS: dict[Suit, int] = {
    Suit.Red: 100,
    Suit.Bells: 80,
    Suit.Acorns: 60,
    Suit.Green: 40,
}

LAST_TRICK_BONUS = 20


def card_points(card: Card) -> int:
    return CARD_POINTS[card.value]


def suit_points(suit: Suit) -> int:
    return SUIT_POINTS[suit]


def deck() -> list[Card]:
    return [
        Card(suit=s, value=v)
        for s in [Suit.Red, Suit.Bells, Suit.Acorns, Suit.Green]
        for v in VALUE_ORDER
    ]


def sorted_cards(cards: list[Card]) -> list[Card]:
    canonical = deck()
    card_set = set(cards)
    return [c for c in canonical if c in card_set]


def _value_rank(value: Value) -> int:
    return VALUE_ORDER.index(value)


def higher_value(base: Value, candidate: Value) -> bool:
    return _value_rank(candidate) > _value_rank(base)


def high_card(cards: list[Card], trump: Suit | None = None) -> Card:
    """Find the winning card in a trick."""
    if not cards:
        raise ValueError("Empty card list")
    lead_suit = cards[0].suit
    best = cards[0]
    for c in cards[1:]:
        if c.suit == lead_suit and higher_value(best.value, c.value):
            best = c

    if trump and trump != lead_suit:
        trump_cards = [c for c in cards if c.suit == trump]
        if trump_cards:
            best_trump = trump_cards[0]
            for c in trump_cards[1:]:
                if higher_value(best_trump.value, c.value):
                    best_trump = c
            return best_trump

    return best


def trick_winner(
    trick: list[Card],
    trump: Suit | None,
    lead_player: PlaceAtTable,
) -> PlaceAtTable:
    winning_card = high_card(trick, trump=trump)
    idx = trick.index(winning_card)
    seat = lead_player.root
    for _ in range(idx):
        seat = (seat + 1) % 4
    return PlaceAtTable(root=seat)


def trick_points(trick: list[Card], *, last: bool = False) -> int:
    pts = sum(CARD_POINTS[c.value] for c in trick)
    if last:
        pts += LAST_TRICK_BONUS
    return pts


def contains_pair(cards: list[Card], suit: Suit) -> bool:
    has_king = any(c.suit == suit and c.value == Value.King for c in cards)
    has_ober = any(c.suit == suit and c.value == Value.Ober for c in cards)
    return has_king and has_ober


def contains_half(cards: list[Card], suit: Suit) -> bool:
    return any(c.suit == suit and c.value in (Value.King, Value.Ober) for c in cards)


def allowed_first_trick(hand: list[Card]) -> list[Card]:
    aces = [c for c in hand if c.value == Value.Ace]
    if aces:
        return aces
    greens = [c for c in hand if c.suit == Suit.Green]
    if greens:
        return greens
    return list(hand)


def allowed_cards(
    trick: list[Card],
    hand: list[Card],
    trump: Suit | None,
    *,
    first_trick: bool = False,
) -> list[Card]:
    if not trick and first_trick:
        return allowed_first_trick(hand)
    if not trick:
        return list(hand)

    lead_suit = trick[0].suit

    if first_trick:
        ace = Card(suit=lead_suit, value=Value.Ace)
        if ace in hand:
            return [ace]

    follow = [c for c in hand if c.suit == lead_suit]
    if not follow:
        follow = [c for c in hand if c.suit == trump] if trump else []

    beaters = [c for c in follow if c == high_card(trick + [c], trump=trump)]
    if beaters:
        return beaters

    return follow if follow else list(hand)
