from __future__ import annotations

import random

from marjapussi.actions import (
    ActionAnnounceTrump,
    ActionAnswer,
    ActionCardPlayed,
    ActionNewBid,
    ActionPass,
    ActionQuestion,
    AnswerYesPair,
    QuestionYourHalf,
)
from marjapussi.agentic.agent import Agent
from marjapussi.events import (
    CallbackNewTrump,
    CallbackStillTrump,
    GameAction,
    GameEvent,
)
from marjapussi.rules import card_points, contains_pair, high_card, suit_points
from marjapussi.state import GameInfoPlayer
from marjapussi.types import Card, Suit, Value

_RANK: dict[Value, int] = {value: i for i, value in enumerate(Value)}
_HALF_VALUES = (Value.King, Value.Ober)


def _hand_strength(hand: list[Card]) -> tuple[int, int]:
    """Split hand value into fairly certain points and speculative points."""
    certain = 0
    speculative = 0
    best_pair_bonus = 0
    for suit in Suit:
        values = {c.value for c in hand if c.suit == suit}
        if Value.Ace in values:
            certain += 16
            if Value.Ten in values:
                certain += 8
        elif Value.Ten in values:
            speculative += 6
        if Value.King in values and Value.Ober in values:
            certain += suit_points(suit)
            best_pair_bonus = max(best_pair_bonus, 10 + 4 * max(0, len(values) - 2))
        elif Value.King in values or Value.Ober in values:
            speculative += suit_points(suit) // 3
    certain += best_pair_bonus
    if certain:
        speculative += 22
    return certain, speculative


def _bid_ceiling(hand: list[Card]) -> int:
    certain, speculative = _hand_strength(hand)
    return certain + speculative // 2


def _stop_action(view: GameInfoPlayer) -> GameAction:
    for action in view.legal_actions:
        if action.action_type == "StopBidding":
            return action
    return view.legal_actions[0]


def _bid_value(action: GameAction) -> int:
    action_type = action.action_type
    assert isinstance(action_type, ActionNewBid)
    return action_type.NewBid


def _bid_actions(view: GameInfoPlayer) -> list[GameAction]:
    return [a for a in view.legal_actions if isinstance(a.action_type, ActionNewBid)]


def _current_bid_holder(view: GameInfoPlayer) -> int | None:
    for action_type, place in reversed(view.bidding_history):
        if isinstance(action_type, ActionNewBid):
            return place.root
    return None


def _forth_units(hand: list[Card]) -> list[tuple[float, list[Card]]]:
    """Group the hand into pass units, best-for-the-playing-partner first."""
    units: list[tuple[float, list[Card]]] = []
    for suit in Suit:
        values = {c.value for c in hand if c.suit == suit}
        ace = Card(suit=suit, value=Value.Ace)
        ten = Card(suit=suit, value=Value.Ten)
        king = Card(suit=suit, value=Value.King)
        ober = Card(suit=suit, value=Value.Ober)
        if Value.Ace in values:
            if Value.Ten in values:
                units.append((145.0, [ace, ten]))
            else:
                units.append((100.0, [ace]))
        elif Value.Ten in values:
            units.append((25.0, [ten]))
        if Value.King in values and Value.Ober in values:
            units.append((0.8 * suit_points(suit), [king, ober]))
        elif Value.King in values:
            units.append((0.35 * suit_points(suit), [king]))
        elif Value.Ober in values:
            units.append((0.35 * suit_points(suit), [ober]))
        for value in (Value.Unter, Value.Nine, Value.Eight, Value.Seven, Value.Six):
            if value in values:
                units.append((float(_RANK[value]), [Card(suit=suit, value=value)]))
    units.sort(key=lambda unit: -unit[0] / len(unit[1]))
    return units


def _pass_action(view: GameInfoPlayer, cards: list[Card]) -> GameAction:
    target = set(cards)
    for action in view.legal_actions:
        action_type = action.action_type
        if isinstance(action_type, ActionPass) and set(action_type.Pass) == target:
            return action
    return view.legal_actions[0]


def _back_keep_value(hand: list[Card], trump_plan: Suit | None, card: Card) -> float:
    if card.value == Value.Ace:
        return 100.0
    suit_values = {c.value for c in hand if c.suit == card.suit}
    if card.value in _HALF_VALUES:
        if Value.King in suit_values and Value.Ober in suit_values:
            return 60.0 + suit_points(card.suit) / 10
        return 40.0
    if card.value == Value.Ten:
        return 55.0 if Value.Ace in suit_values else 30.0
    base = float(_RANK[card.value])
    if trump_plan is not None and card.suit == trump_plan:
        base += 25.0
    return base


class HeuristicAgent(Agent):
    """Fast rule-of-thumb agent: no belief tracking, no simulation."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._reset()

    def _reset(self) -> None:
        self._trump: Suit | None = None
        self._called: set[Suit] = set()
        self._played: set[Card] = set()
        self._asked_yours = False
        self._asked_halves: set[Suit] = set()
        self._ceiling: int | None = None

    def observe(self, view: GameInfoPlayer) -> None:
        event = view.last_event
        if event is None:
            self._reset()
            return
        if not isinstance(event, GameEvent):
            return
        callback = event.callback
        if isinstance(callback, CallbackNewTrump):
            self._trump = callback.NewTrump
            self._called.add(callback.NewTrump)
        elif isinstance(callback, CallbackStillTrump):
            self._trump = callback.StillTrump
            self._called.add(callback.StillTrump)
        action_type = event.last_action.action_type
        if isinstance(action_type, ActionCardPlayed):
            self._played.add(action_type.CardPlayed)
        elif (
            isinstance(action_type, ActionQuestion)
            and event.last_action.player == self.place
        ):
            if action_type.Question == "Yours":
                self._asked_yours = True
            elif isinstance(action_type.Question, QuestionYourHalf):
                self._asked_halves.add(action_type.Question.YourHalf)

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        actions = view.legal_actions
        if len(actions) == 1:
            return actions[0]
        phase = view.game_phase
        if phase == "Bidding":
            return self._bid(view)
        if phase == "PassingForth":
            return self._pass_forth(view)
        if phase == "PassingBack":
            return self._pass_back(view)
        if phase == "Raising":
            return self._raise(view)
        if phase == "AnsweringPair":
            return self._answer_pair(view)
        if phase == "StartTrick":
            return self._start_trick(view)
        return self._play_card_action(view)

    def _bid(self, view: GameInfoPlayer) -> GameAction:
        hand = view.own_cards or []
        if self._ceiling is None:
            self._ceiling = _bid_ceiling(hand)
        holder = _current_bid_holder(view)
        if holder is not None and holder == self.place.partner().root:
            return _stop_action(view)
        bids = _bid_actions(view)
        if bids:
            lowest = min(bids, key=_bid_value)
            if _bid_value(lowest) <= self._ceiling:
                return lowest
        return _stop_action(view)

    def _pass_forth(self, view: GameInfoPlayer) -> GameAction:
        hand = view.own_cards or []
        chosen: list[Card] = []
        units = _forth_units(hand)
        for _, cards in units:
            if len(chosen) + len(cards) <= 4:
                chosen.extend(cards)
            if len(chosen) == 4:
                break
        if len(chosen) < 4:
            rest = [c for _, cards in units for c in cards if c not in chosen]
            chosen.extend(rest[: 4 - len(chosen)])
        return _pass_action(view, chosen)

    def _pass_back(self, view: GameInfoPlayer) -> GameAction:
        hand = view.own_cards or []
        pair_suits = [suit for suit in Suit if contains_pair(hand, suit)]
        trump_plan = None
        if pair_suits:
            trump_plan = max(
                pair_suits,
                key=lambda s: (sum(1 for c in hand if c.suit == s), suit_points(s)),
            )
        chosen = sorted(hand, key=lambda c: _back_keep_value(hand, trump_plan, c))[:4]
        return _pass_action(view, chosen)

    def _raise(self, view: GameInfoPlayer) -> GameAction:
        hand = view.own_cards or []
        certain, _ = _hand_strength(hand)
        bids = _bid_actions(view)
        if not bids:
            return _stop_action(view)
        current = min(_bid_value(a) for a in bids) - 5
        target = certain - 20
        if target < current + 15:
            return _stop_action(view)
        eligible = [a for a in bids if _bid_value(a) <= target]
        if not eligible:
            return _stop_action(view)
        return max(eligible, key=_bid_value)

    def _answer_pair(self, view: GameInfoPlayer) -> GameAction:
        best: tuple[int, GameAction] | None = None
        for action in view.legal_actions:
            action_type = action.action_type
            if isinstance(action_type, ActionAnswer) and isinstance(
                action_type.Answer, AnswerYesPair
            ):
                points = suit_points(action_type.Answer.YesPair)
                if best is None or points > best[0]:
                    best = (points, action)
        if best is not None:
            return best[1]
        return view.legal_actions[0]

    def _start_trick(self, view: GameInfoPlayer) -> GameAction:
        best: tuple[int, GameAction] | None = None
        for action in view.legal_actions:
            action_type = action.action_type
            if isinstance(action_type, ActionAnnounceTrump):
                points = suit_points(action_type.AnnounceTrump)
                if best is None or points > best[0]:
                    best = (points, action)
        if best is not None:
            return best[1]
        question = self._question(view)
        if question is not None:
            return question
        return self._play_card_action(view)

    def _question(self, view: GameInfoPlayer) -> GameAction | None:
        hand = view.own_cards or []
        if not self._asked_yours:
            for action in view.legal_actions:
                action_type = action.action_type
                if (
                    isinstance(action_type, ActionQuestion)
                    and action_type.Question == "Yours"
                ):
                    return action
        candidates: list[Suit] = []
        for suit in Suit:
            if suit in self._called or suit in self._asked_halves:
                continue
            mine = [v for v in _HALF_VALUES if Card(suit=suit, value=v) in hand]
            if len(mine) != 1:
                continue
            other = Value.Ober if mine[0] == Value.King else Value.King
            if Card(suit=suit, value=other) in self._played:
                continue
            candidates.append(suit)
        if not candidates:
            return None
        wanted = max(candidates, key=suit_points)
        for action in view.legal_actions:
            action_type = action.action_type
            if (
                isinstance(action_type, ActionQuestion)
                and isinstance(action_type.Question, QuestionYourHalf)
                and action_type.Question.YourHalf == wanted
            ):
                return action
        return None

    def _play_card_action(self, view: GameInfoPlayer) -> GameAction:
        options: list[tuple[GameAction, Card]] = [
            (a, a.action_type.CardPlayed)
            for a in view.legal_actions
            if isinstance(a.action_type, ActionCardPlayed)
        ]
        hand = view.own_cards or []
        legal = [card for _, card in options]
        if view.current_trick:
            chosen = self._follow_card(view, hand, legal)
        else:
            chosen = self._lead_card(hand, legal)
        for action, card in options:
            if card == chosen:
                return action
        return options[0][0]

    def _lead_card(self, hand: list[Card], legal: list[Card]) -> Card:
        def score(card: Card) -> float:
            if self._is_boss(card, hand):
                seen_suit = sum(1 for c in self._played if c.suit == card.suit)
                trump_live = self._trump is not None and not self._trumps_gone(hand)
                risky = trump_live and card.suit != self._trump and seen_suit >= 4
                if not risky:
                    value = 60.0 + card_points(card) - 2 * seen_suit
                    ten = Card(suit=card.suit, value=Value.Ten)
                    if card.value == Value.Ace and ten in hand:
                        value += 4
                    if trump_live and card.suit == self._trump:
                        value += 6
                    return value
            return 20.0 - self._keep_value(card, hand)

        return max(legal, key=score)

    def _follow_card(
        self, view: GameInfoPlayer, hand: list[Card], legal: list[Card]
    ) -> Card:
        trick = view.current_trick
        trump = self._trump
        last = len(trick) == 3
        winning = high_card(trick, trump=trump)
        leader = (self.place.root - len(trick)) % 4
        winner_seat = (leader + trick.index(winning)) % 4
        partner_winning = winner_seat == (self.place.root + 2) % 4
        beaters = [c for c in legal if c == high_card([*trick, c], trump=trump)]
        if beaters:
            if last:
                return min(
                    beaters, key=lambda c: (self._win_cost(c, hand), _RANK[c.value])
                )
            secure = [c for c in beaters if self._secure(c, hand)]
            if secure:
                return min(
                    secure, key=lambda c: (self._win_cost(c, hand), _RANK[c.value])
                )
            trick_pts = sum(card_points(c) for c in trick)
            if not partner_winning and trick_pts >= 10:
                return max(beaters, key=lambda c: _RANK[c.value])
            return min(
                beaters, key=lambda c: (self._keep_value(c, hand), _RANK[c.value])
            )
        if partner_winning and (last or self._secure(winning, hand)):
            return max(
                legal, key=lambda c: (self._feed_score(c, hand), -_RANK[c.value])
            )
        return min(legal, key=lambda c: (self._keep_value(c, hand), _RANK[c.value]))

    def _is_boss(self, card: Card, hand: list[Card]) -> bool:
        for value in Value:
            if _RANK[value] <= _RANK[card.value]:
                continue
            higher = Card(suit=card.suit, value=value)
            if higher not in self._played and higher not in hand:
                return False
        return True

    def _trumps_gone(self, hand: list[Card]) -> bool:
        if self._trump is None:
            return True
        for value in Value:
            card = Card(suit=self._trump, value=value)
            if card not in self._played and card not in hand:
                return False
        return True

    def _secure(self, card: Card, hand: list[Card]) -> bool:
        if not self._is_boss(card, hand):
            return False
        if self._trump is None or card.suit == self._trump:
            return True
        return self._trumps_gone(hand)

    def _half_bonus(self, card: Card, hand: list[Card]) -> int:
        if card.value not in _HALF_VALUES or card.suit in self._called:
            return 0
        other = Value.Ober if card.value == Value.King else Value.King
        counterpart = Card(suit=card.suit, value=other)
        if counterpart in hand:
            return 16
        if counterpart in self._played:
            return 0
        return 10

    def _keep_value(self, card: Card, hand: list[Card]) -> int:
        value = card_points(card)
        if card.value == Value.Ace:
            value += 14
        elif card.value == Value.Ten:
            has_ace = Card(suit=card.suit, value=Value.Ace) in hand
            value += 6 if has_ace else 4
        value += self._half_bonus(card, hand)
        if self._trump is not None and card.suit == self._trump:
            value += 8
        elif card.value != Value.Ace and self._is_boss(card, hand):
            value += 5
        return value

    def _win_cost(self, card: Card, hand: list[Card]) -> int:
        return self._keep_value(card, hand) - card_points(card)

    def _feed_score(self, card: Card, hand: list[Card]) -> int:
        value = card_points(card)
        if card.value == Value.Ace:
            value -= 20
        value -= self._half_bonus(card, hand)
        if self._trump is not None and card.suit == self._trump:
            value -= 4
        return value
