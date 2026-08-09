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
from marjapussi.agentic.beliefs import BeliefAgent
from marjapussi.events import (
    CallbackNewTrump,
    CallbackStillTrump,
    GameAction,
    GameEvent,
)
from marjapussi.rules import card_points, high_card, suit_points
from marjapussi.state import GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable, Suit, Value

_RANK: dict[Value, int] = {value: rank for rank, value in enumerate(Value)}
_HALVES = (Value.King, Value.Ober)


class CountingAgent(BeliefAgent):
    """Plays on card-counting inferences from the belief state, no simulation."""

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self.rng = rng
        self._game_value = 115
        self._party_points = [0, 0]
        self._called: set[tuple[int, Suit]] = set()

    def on_view(self, view: GameInfoPlayer) -> None:
        event = view.last_event
        if not isinstance(event, GameEvent):
            return
        seat = event.last_action.player
        action_type = event.last_action.action_type
        if isinstance(action_type, ActionNewBid):
            self._game_value = action_type.NewBid
        callback = event.callback
        if isinstance(callback, CallbackNewTrump | CallbackStillTrump):
            suit = (
                callback.NewTrump
                if isinstance(callback, CallbackNewTrump)
                else callback.StillTrump
            )
            if (seat.root, suit) not in self._called:
                self._called.add((seat.root, suit))
                self._party_points[seat.root % 2] += suit_points(suit)
        if isinstance(action_type, ActionCardPlayed) and not view.current_trick:
            trick = view.last_trick
            if trick is not None:
                self._party_points[trick.winner.root % 2] += trick.points.root

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        actions = view.legal_actions
        if len(actions) == 1:
            return actions[0]
        phase = view.game_phase
        if phase == "Bidding":
            return self._bid_action(view, actions)
        if phase == "PassingForth":
            return self._pass_action(actions, view.own_cards or [], forth=True)
        if phase == "PassingBack":
            return self._pass_action(actions, view.own_cards or [], forth=False)
        if phase == "Raising":
            return self._raise_action(view, actions)
        if phase == "AnsweringPair":
            return self._answer_pair_action(actions)
        if phase == "StartTrick":
            question = self._question_action(view, actions)
            if question is not None:
                return question
            return self._card_action(view, actions)
        if phase == "Trick":
            return self._card_action(view, actions)
        return actions[0]

    def _bid_action(
        self, view: GameInfoPlayer, actions: list[GameAction]
    ) -> GameAction:
        stop = next(a for a in actions if a.action_type == "StopBidding")
        highest_bidder = self._playing_seat(view)
        if highest_bidder is not None and highest_bidder == self.place.partner():
            return stop
        budget = self._hand_strength(view.own_cards or [], potential=True) + 25
        target = self._game_value + 5
        if target <= budget:
            bid = self._find_bid(actions, target)
            if bid is not None:
                return bid
        return stop

    def _raise_action(
        self, view: GameInfoPlayer, actions: list[GameAction]
    ) -> GameAction:
        stop = next(a for a in actions if a.action_type == "StopBidding")
        estimate = self._hand_strength(view.own_cards or [], potential=False)
        target = (estimate - 15) // 5 * 5
        if target > self._game_value:
            bid = self._find_bid(actions, target)
            if bid is not None:
                return bid
        return stop

    def _find_bid(self, actions: list[GameAction], value: int) -> GameAction | None:
        for action in actions:
            if (
                isinstance(action.action_type, ActionNewBid)
                and action.action_type.NewBid == value
            ):
                return action
        return None

    def _pass_action(
        self, actions: list[GameAction], hand: list[Card], *, forth: bool
    ) -> GameAction:
        if forth:
            ranked = sorted(
                hand,
                key=lambda c: (-self._give_score(c, hand), self.rng.random()),
            )
        else:
            ranked = sorted(
                hand,
                key=lambda c: (self._keep_score(c, hand), self.rng.random()),
            )
        chosen = frozenset(ranked[:4])
        return next(
            a
            for a in actions
            if isinstance(a.action_type, ActionPass)
            and frozenset(a.action_type.Pass) == chosen
        )

    def _give_score(self, card: Card, hand: list[Card]) -> int:
        values = {c.value for c in hand if c.suit == card.suit}
        if card.value == Value.Ace:
            return 100
        if card.value in _HALVES:
            base = 60 if all(v in values for v in _HALVES) else 40
            return base + suit_points(card.suit) // 10
        if card.value == Value.Ten:
            return 55 if Value.Ace in values else 30
        return card_points(card)

    def _keep_score(self, card: Card, hand: list[Card]) -> int:
        values = {c.value for c in hand if c.suit == card.suit}
        if card.value == Value.Ace:
            return 100
        if card.value in _HALVES:
            if all(v in values for v in _HALVES):
                return 90 + suit_points(card.suit) // 10
            return 50
        if card.value == Value.Ten:
            return 70 if Value.Ace in values else 45
        return _RANK[card.value]

    def _answer_pair_action(self, actions: list[GameAction]) -> GameAction:
        def pair_value(action: GameAction) -> int:
            action_type = action.action_type
            if isinstance(action_type, ActionAnswer) and isinstance(
                action_type.Answer, AnswerYesPair
            ):
                return suit_points(action_type.Answer.YesPair)
            return -1

        return max(actions, key=pair_value)

    def _question_action(
        self, view: GameInfoPlayer, actions: list[GameAction]
    ) -> GameAction | None:
        announcements = [
            a for a in actions if isinstance(a.action_type, ActionAnnounceTrump)
        ]
        if announcements:
            return max(
                announcements,
                key=lambda a: suit_points(a.action_type.AnnounceTrump),  # type: ignore[union-attr]
            )
        partner = self.place.partner()
        partner_possible = self.beliefs.possible_cards(partner)
        called_suits = {suit for _, suit in self._called}
        speculate = not self._contract_safe()

        yours = self._find_question(actions, "Yours")
        if yours is not None:
            possible_pair = any(
                suit not in called_suits and self._has_pair(partner_possible, suit)
                for suit in Suit
            )
            if possible_pair and speculate:
                return yours

        hand = view.own_cards or []
        for suit in sorted(Suit, key=suit_points, reverse=True):
            if suit in called_suits:
                continue
            mine = [v for v in _HALVES if Card(suit=suit, value=v) in hand]
            if len(mine) != 1:
                continue
            other = Card(suit=suit, value=_HALVES[1 - _HALVES.index(mine[0])])
            if other not in partner_possible:
                continue
            partner_has_it = not any(
                other in self.beliefs.possible_cards(opp) for opp in self._opponents()
            )
            if partner_has_it or speculate:
                half = self._find_question(actions, QuestionYourHalf(YourHalf=suit))
                if half is not None:
                    return half
        return None

    def _find_question(
        self, actions: list[GameAction], question: str | QuestionYourHalf
    ) -> GameAction | None:
        for action in actions:
            if (
                isinstance(action.action_type, ActionQuestion)
                and action.action_type.Question == question
            ):
                return action
        return None

    def _card_action(
        self, view: GameInfoPlayer, actions: list[GameAction]
    ) -> GameAction:
        by_card = {
            a.action_type.CardPlayed: a
            for a in actions
            if isinstance(a.action_type, ActionCardPlayed)
        }
        cards = list(by_card)
        if view.current_trick:
            card = self._follow_card(view, cards)
        else:
            card = self._lead_card(view, cards)
        return by_card[card]

    def _lead_card(self, view: GameInfoPlayer, cards: list[Card]) -> Card:
        sure = [c for c in cards if self._sure_lead_winner(c)]
        if sure:
            return max(sure, key=lambda c: (card_points(c), self.rng.random()))
        trump = self.beliefs.trump
        partner = self.place.partner()
        partner_certain = self.beliefs.certain_cards(partner)
        partner_possible = self.beliefs.possible_cards(partner)
        speculate = not self._contract_safe()

        def score(card: Card) -> tuple[float, float]:
            value = -float(card_points(card)) - _RANK[card.value] * 0.1
            if any(
                p.suit == card.suit
                and self._beats(p, card)
                and not any(self._can_beat(opp, p) for opp in self._opponents())
                for p in partner_certain
            ):
                value += 40.0
            for opp in self._opponents():
                possible = self.beliefs.possible_cards(opp)
                opp_void = not any(c.suit == card.suit for c in possible)
                opp_trump = (
                    trump is not None
                    and card.suit != trump
                    and any(c.suit == trump for c in possible)
                )
                if opp_void and opp_trump:
                    value -= 8.0
            if speculate and trump is not None and card.suit != trump:
                partner_void = not any(c.suit == card.suit for c in partner_possible)
                partner_trump = any(c.suit == trump for c in partner_possible)
                if partner_void and partner_trump:
                    value += 6.0
            return value, self.rng.random()

        return max(cards, key=score)

    def _follow_card(self, view: GameInfoPlayer, cards: list[Card]) -> Card:
        trick = view.current_trick
        trump = self.beliefs.trump
        best = high_card(trick, trump=trump)
        leader_root = (self.place.root - len(trick)) % 4
        winner_root = (leader_root + trick.index(best)) % 4
        partner_winning = winner_root == self.place.partner().root
        remaining_opponents = [
            PlaceAtTable(root=(self.place.root + offset) % 4)
            for offset in range(1, 4 - len(trick))
            if (self.place.root + offset) % 2 != self.place.root % 2
        ]
        partner_safe = partner_winning and not any(
            self._can_beat(opp, best) for opp in remaining_opponents
        )
        beaters = [c for c in cards if high_card([*trick, c], trump=trump) == c]
        if beaters:
            if partner_safe:
                return min(
                    beaters,
                    key=lambda c: (card_points(c), _RANK[c.value], self.rng.random()),
                )
            unbeatable = [
                c
                for c in beaters
                if not any(self._can_beat(opp, c) for opp in remaining_opponents)
            ]
            if unbeatable:
                return min(
                    unbeatable, key=lambda c: (_RANK[c.value], self.rng.random())
                )
            return min(
                beaters,
                key=lambda c: (card_points(c), _RANK[c.value], self.rng.random()),
            )
        if partner_safe:
            pool = [c for c in cards if not self._sure_lead_winner(c)] or cards
            return max(
                pool,
                key=lambda c: (card_points(c), -_RANK[c.value], self.rng.random()),
            )
        return min(
            cards, key=lambda c: (card_points(c), _RANK[c.value], self.rng.random())
        )

    def _sure_lead_winner(self, card: Card) -> bool:
        return not any(self._can_beat(opp, card) for opp in self._opponents())

    def _can_beat(self, seat: PlaceAtTable, target: Card) -> bool:
        return any(
            self._beats(candidate, target)
            for candidate in self.beliefs.possible_cards(seat)
        )

    def _beats(self, card: Card, target: Card) -> bool:
        if card.suit == target.suit:
            return _RANK[card.value] > _RANK[target.value]
        trump = self.beliefs.trump
        return trump is not None and card.suit == trump and target.suit != trump

    def _opponents(self) -> tuple[PlaceAtTable, PlaceAtTable]:
        return self.place.next(), self.place.prev()

    def _playing_seat(self, view: GameInfoPlayer) -> PlaceAtTable | None:
        for action_type, seat in reversed(view.bidding_history):
            if isinstance(action_type, ActionNewBid):
                return seat
        return None

    def _contract_safe(self) -> bool:
        return self._party_points[self.place.root % 2] >= self._game_value

    def _has_pair(self, cards: set[Card], suit: Suit) -> bool:
        return all(Card(suit=suit, value=v) in cards for v in _HALVES)

    def _hand_strength(self, hand: list[Card], *, potential: bool) -> int:
        total = 0
        for suit in Suit:
            values = {c.value for c in hand if c.suit == suit}
            if all(v in values for v in _HALVES):
                total += suit_points(suit)
            elif potential and any(v in values for v in _HALVES):
                total += suit_points(suit) // 3
            if Value.Ace in values:
                total += 20 if potential else 15
                if Value.Ten in values:
                    total += 10
            elif Value.Ten in values and len(values) >= 3:
                total += 5
            if len(values) >= 4:
                total += 5 * (len(values) - 3)
        return total
