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
from marjapussi.rules import VALUE_ORDER, card_points, high_card, suit_points
from marjapussi.state import GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable, Suit, Value

START_VALUE = 115
MAX_VALUE = 420
BID_MARGIN = 10
RAISE_MARGIN = 30
TRICK_BASE = 45
RAISE_TRICK_BASE = 35
TRICK_CAP = 130
PARTNER_EXTRA_CAP = 80
TRUMP_FIT_POINTS = 6


def _rank(value: Value) -> int:
    return VALUE_ORDER.index(value)


class ExpertAgent(BeliefAgent):
    """Valuation-driven agent focused on bidding, passing, and announcements."""

    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self.rng = rng
        self._game_value = START_VALUE
        self._trump_called: set[Suit] = set()
        self._trump_ours = False
        self._partner_no_pair = False

    def on_view(self, view: GameInfoPlayer) -> None:
        event = view.last_event
        if not isinstance(event, GameEvent):
            return
        action = event.last_action
        action_type = action.action_type
        if isinstance(action_type, ActionNewBid):
            self._game_value = action_type.NewBid
        callback = event.callback
        if isinstance(callback, CallbackNewTrump):
            self._register_trump(callback.NewTrump, action.player)
        elif isinstance(callback, CallbackStillTrump):
            self._register_trump(callback.StillTrump, action.player)
        if (
            isinstance(action_type, ActionAnswer)
            and action_type.Answer == "NoPair"
            and action.player == self.place.partner()
        ):
            self._partner_no_pair = True

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        actions = view.legal_actions
        if len(actions) == 1:
            return actions[0]
        phase = view.game_phase
        if phase == "Bidding":
            return self._bid(view)
        if phase == "PassingForth":
            return self._pass_action(view, self._pass_forth_selection(view))
        if phase == "PassingBack":
            return self._pass_action(view, self._pass_back_selection(view))
        if phase == "Raising":
            return self._raise(view)
        if phase == "AnsweringPair":
            return self._answer_pair(view)
        communication = self._communication(view)
        if communication is not None:
            return communication
        return self._play_card(view)

    def _register_trump(self, suit: Suit, caller: PlaceAtTable) -> None:
        self._trump_called.add(suit)
        self._trump_ours = caller.party() == self.place.party()

    @staticmethod
    def _suit_cards(cards: list[Card], suit: Suit) -> list[Card]:
        return [c for c in cards if c.suit == suit]

    @staticmethod
    def _has(cards: list[Card], suit: Suit, value: Value) -> bool:
        return Card(suit=suit, value=value) in cards

    def _pair_suits(self, cards: list[Card]) -> list[Suit]:
        return [
            s
            for s in Suit
            if s not in self._trump_called
            and self._has(cards, s, Value.King)
            and self._has(cards, s, Value.Ober)
        ]

    def _half_suits(self, cards: list[Card]) -> list[Suit]:
        return [
            s
            for s in Suit
            if s not in self._trump_called
            and self._has(cards, s, Value.King) != self._has(cards, s, Value.Ober)
        ]

    def _keepable_half(self, card: Card, hand: list[Card]) -> bool:
        if card.suit in self._trump_called:
            return False
        other_value = Value.Ober if card.value == Value.King else Value.King
        other = Card(suit=card.suit, value=other_value)
        if other in hand:
            return True
        return other in self.beliefs.possible_cards(self.place.partner())

    def _pick[T](self, candidates: list[T], score: dict[T, int]) -> T:
        best = max(score[c] for c in candidates)
        top = [c for c in candidates if score[c] == best]
        if len(top) == 1:
            return top[0]
        return self.rng.choice(top)

    def _hand_estimate(self, hand: list[Card]) -> int:
        pairs = self._pair_suits(hand)
        halves = self._half_suits(hand)
        aces = sum(1 for c in hand if c.value == Value.Ace)
        backed_tens = sum(
            1
            for s in Suit
            if self._has(hand, s, Value.Ten) and self._has(hand, s, Value.Ace)
        )
        estimate = TRICK_BASE + 13 * aces + 9 * backed_tens
        if pairs:
            best_len = max(len(self._suit_cards(hand, s)) for s in pairs)
            estimate += 4 * max(0, best_len - 2)
        estimate += sum(suit_points(s) for s in pairs)
        estimate += sum(suit_points(s) // 3 for s in halves)
        return estimate

    def _bid(self, view: GameInfoPlayer) -> GameAction:
        me = self.place.root
        partner = self.place.partner().root
        stopped: set[int] = set()
        top_bidder: int | None = None
        my_top = 0
        partner_top = 0
        my_top_before_partner = 0
        for action_type, player in view.bidding_history:
            if action_type == "StopBidding":
                stopped.add(player.root)
            elif isinstance(action_type, ActionNewBid):
                top_bidder = player.root
                if player.root == me:
                    my_top = action_type.NewBid
                elif player.root == partner:
                    partner_top = action_type.NewBid
                    my_top_before_partner = my_top
        opponents_out = {(me + 1) % 4, (me + 3) % 4} <= stopped
        if opponents_out and top_bidder is not None and top_bidder % 2 == me % 2:
            return self._stop_action(view)
        limit = self._hand_estimate(list(view.own_cards or [])) - BID_MARGIN
        if partner in stopped and partner_top > START_VALUE:
            extra = (partner_top - START_VALUE) - max(
                0, my_top_before_partner - START_VALUE
            )
            limit += min(max(extra, 0), PARTNER_EXTRA_CAP)
        next_bid = self._game_value + 5
        if next_bid <= limit:
            return self._bid_action(view, next_bid)
        return self._stop_action(view)

    @staticmethod
    def _stop_action(view: GameInfoPlayer) -> GameAction:
        return next(a for a in view.legal_actions if a.action_type == "StopBidding")

    def _bid_action(self, view: GameInfoPlayer, value: int) -> GameAction:
        for action in view.legal_actions:
            if (
                isinstance(action.action_type, ActionNewBid)
                and action.action_type.NewBid == value
            ):
                return action
        return self._stop_action(view)

    def _pass_action(self, view: GameInfoPlayer, chosen: set[Card]) -> GameAction:
        return next(
            a
            for a in view.legal_actions
            if isinstance(a.action_type, ActionPass)
            and set(a.action_type.Pass) == chosen
        )

    def _pass_forth_selection(self, view: GameInfoPlayer) -> set[Card]:
        hand = list(view.own_cards or [])
        pair_suits = [
            s
            for s in Suit
            if self._has(hand, s, Value.King) and self._has(hand, s, Value.Ober)
        ]
        pair_cards = {
            Card(suit=s, value=v) for s in pair_suits for v in (Value.King, Value.Ober)
        }
        score = {c: self._give_forth_score(c, hand) for c in hand}
        free = sorted(
            (c for c in hand if c not in pair_cards),
            key=lambda c: score[c],
            reverse=True,
        )
        if len(free) >= 4:
            return set(free[:4])
        chosen = list(free)
        needed_pairs = (4 - len(free) + 1) // 2
        for s in sorted(pair_suits, key=suit_points)[:needed_pairs]:
            chosen.append(Card(suit=s, value=Value.King))
            chosen.append(Card(suit=s, value=Value.Ober))
        while len(chosen) > 4:
            worst = min(
                (c for c in chosen if c not in pair_cards), key=lambda c: score[c]
            )
            chosen.remove(worst)
        return set(chosen)

    def _give_forth_score(self, card: Card, hand: list[Card]) -> int:
        suit_len = len(self._suit_cards(hand, card.suit))
        if card.value == Value.Ace:
            return 100 - suit_len
        if card.value in (Value.King, Value.Ober):
            return 70 + suit_points(card.suit) // 10
        if card.value == Value.Ten:
            return 55
        return 20 - 4 * suit_len - card_points(card)

    def _pass_back_selection(self, view: GameInfoPlayer) -> set[Card]:
        hand = list(view.own_cards or [])
        pair_suits = [
            s
            for s in Suit
            if self._has(hand, s, Value.King) and self._has(hand, s, Value.Ober)
        ]
        trump_suit: Suit | None = None
        if pair_suits:
            trump_suit = max(
                pair_suits,
                key=lambda s: (len(self._suit_cards(hand, s)), suit_points(s)),
            )
        partner_possible = self.beliefs.possible_cards(self.place.partner())
        scored = sorted(
            hand,
            key=lambda c: self._give_back_score(c, hand, trump_suit, partner_possible),
            reverse=True,
        )
        return set(scored[:4])

    def _give_back_score(
        self,
        card: Card,
        hand: list[Card],
        trump_suit: Suit | None,
        partner_possible: set[Card],
    ) -> int:
        suit_len = len(self._suit_cards(hand, card.suit))
        value = card.value
        if value in (Value.King, Value.Ober):
            other_value = Value.Ober if value == Value.King else Value.King
            if Card(suit=card.suit, value=other_value) in hand:
                return 0
            if card.suit in self._trump_called:
                return 55
            if Card(suit=card.suit, value=other_value) in partner_possible:
                return 12
            return 50
        if card.suit == trump_suit:
            return 1
        if value == Value.Ten:
            return 2 if self._has(hand, card.suit, Value.Ace) else 25
        if value == Value.Ace:
            return 3
        if value == Value.Unter:
            return 60 - 3 * suit_len
        return 80 - 5 * suit_len - card_points(card)

    def _raise(self, view: GameInfoPlayer) -> GameAction:
        hand = list(view.own_cards or [])
        partner = self.place.partner()
        certain_partner = self.beliefs.certain_cards(partner)
        pair_suits = self._pair_suits(hand)
        announce = sum(suit_points(s) for s in pair_suits)
        for s in Suit:
            if s in self._trump_called or s in pair_suits:
                continue
            king = Card(suit=s, value=Value.King)
            ober = Card(suit=s, value=Value.Ober)
            if {king, ober} <= certain_partner:
                announce += suit_points(s)
                continue
            mine = [c for c in (king, ober) if c in hand]
            if len(mine) != 1:
                continue
            other = ober if mine[0] == king else king
            if other in certain_partner:
                announce += suit_points(s)
        aces = sum(1 for c in hand if c.value == Value.Ace)
        backed_tens = sum(
            1
            for s in Suit
            if self._has(hand, s, Value.Ten) and self._has(hand, s, Value.Ace)
        )
        tricks = RAISE_TRICK_BASE + 12 * aces + 8 * backed_tens
        if pair_suits:
            best_len = max(len(self._suit_cards(hand, s)) for s in pair_suits)
            tricks += 4 * max(0, best_len - 2)
        target = announce + min(tricks, TRICK_CAP) - RAISE_MARGIN
        target = min(5 * (target // 5), MAX_VALUE)
        if target > self._game_value:
            return self._bid_action(view, target)
        return self._stop_action(view)

    def _answer_pair(self, view: GameInfoPlayer) -> GameAction:
        hand = list(view.own_cards or [])
        options = [
            a
            for a in view.legal_actions
            if isinstance(a.action_type, ActionAnswer)
            and isinstance(a.action_type.Answer, AnswerYesPair)
        ]
        if not options:
            return view.legal_actions[0]

        def score(action: GameAction) -> int:
            assert isinstance(action.action_type, ActionAnswer)
            assert isinstance(action.action_type.Answer, AnswerYesPair)
            suit = action.action_type.Answer.YesPair
            return suit_points(suit) + 6 * len(self._suit_cards(hand, suit))

        return max(options, key=score)

    def _trump_cost(self, suit: Suit, hand: list[Card]) -> int:
        trump = self.beliefs.trump
        if trump is None or trump == suit or not self._trump_ours:
            return 0
        certain_partner = self.beliefs.certain_cards(self.place.partner())

        def fit(s: Suit) -> int:
            own = len(self._suit_cards(hand, s))
            return own + sum(1 for c in certain_partner if c.suit == s)

        return TRUMP_FIT_POINTS * max(0, fit(trump) - fit(suit))

    def _communication(self, view: GameInfoPlayer) -> GameAction | None:
        legals = view.legal_actions
        hand = list(view.own_cards or [])
        announce_options = [
            a for a in legals if isinstance(a.action_type, ActionAnnounceTrump)
        ]
        if announce_options:

            def announce_gain(action: GameAction) -> int:
                assert isinstance(action.action_type, ActionAnnounceTrump)
                suit = action.action_type.AnnounceTrump
                return suit_points(suit) - self._trump_cost(suit, hand)

            best = max(announce_options, key=announce_gain)
            if announce_gain(best) > 0:
                return best
            return None
        partner = self.place.partner()
        partner_possible = self.beliefs.possible_cards(partner)
        yours = next(
            (
                a
                for a in legals
                if isinstance(a.action_type, ActionQuestion)
                and a.action_type.Question == "Yours"
            ),
            None,
        )
        partner_pair_possible = any(
            s not in self._trump_called
            and Card(suit=s, value=Value.King) in partner_possible
            and Card(suit=s, value=Value.Ober) in partner_possible
            for s in Suit
        )
        if yours is not None and partner_pair_possible and not self._partner_no_pair:
            return yours
        certain_partner = self.beliefs.certain_cards(partner)
        best_half: GameAction | None = None
        best_gain = 0
        for action in legals:
            if not isinstance(action.action_type, ActionQuestion):
                continue
            question = action.action_type.Question
            if not isinstance(question, QuestionYourHalf):
                continue
            suit = question.YourHalf
            if suit in self._trump_called:
                continue
            king = Card(suit=suit, value=Value.King)
            ober = Card(suit=suit, value=Value.Ober)
            mine = [c for c in (king, ober) if c in hand]
            if len(mine) != 1:
                continue
            other = ober if mine[0] == king else king
            if other in certain_partner:
                chance = 10
            elif other in partner_possible:
                chance = 4
            else:
                continue
            gain = suit_points(suit) * chance // 10 - self._trump_cost(suit, hand)
            if gain > best_gain:
                best_gain = gain
                best_half = action
        return best_half

    def _play_card(self, view: GameInfoPlayer) -> GameAction:
        card_actions = {
            a.action_type.CardPlayed: a
            for a in view.legal_actions
            if isinstance(a.action_type, ActionCardPlayed)
        }
        cards = list(card_actions)
        trick = list(view.current_trick)
        if trick:
            chosen = self._follow_choice(view, cards, trick)
        else:
            chosen = self._lead_choice(view, cards)
        return card_actions[chosen]

    def _lead_choice(self, view: GameInfoPlayer, cards: list[Card]) -> Card:
        hand = list(view.own_cards or [])
        trump = self.beliefs.trump
        if view.last_trick is None:
            aces = [c for c in cards if c.value == Value.Ace]
            if aces:
                backed = [c for c in aces if self._has(hand, c.suit, Value.Ten)]
                pool = backed or aces
                return max(pool, key=lambda c: len(self._suit_cards(hand, c.suit)))
            return min(cards, key=lambda c: self._sluff_score(c, hand))
        opponents = [self.place.next(), self.place.prev()]
        sure = [c for c in cards if not self._opponents_can_beat([c], opponents)]
        if sure:
            if (
                trump is not None
                and any(c.suit == trump for c in sure)
                and self._opponents_hold_suit(trump, opponents)
            ):
                trump_sure = [c for c in sure if c.suit == trump]
                return max(trump_sure, key=lambda c: _rank(c.value))
            score = {c: 10 * card_points(c) + _rank(c.value) for c in sure}
            return self._pick(sure, score)
        certain_partner = self.beliefs.certain_cards(self.place.partner())
        for suit in Suit:
            if suit == trump:
                continue
            mine = self._suit_cards(cards, suit)
            if not mine:
                continue
            master = self._master_of_suit(suit)
            if master is not None and master in certain_partner:
                return min(mine, key=lambda c: _rank(c.value))
        return min(cards, key=lambda c: self._sluff_score(c, hand))

    def _follow_choice(
        self, view: GameInfoPlayer, cards: list[Card], trick: list[Card]
    ) -> Card:
        hand = list(view.own_cards or [])
        trump = self.beliefs.trump
        position = len(trick)
        remaining = [
            PlaceAtTable(root=(self.place.root + i) % 4) for i in range(1, 4 - position)
        ]
        remaining_opponents = [s for s in remaining if s.party() != self.place.party()]
        lead_seat = PlaceAtTable(root=(self.place.root - position) % 4)
        winning_card = high_card(trick, trump=trump)
        winner_offset = trick.index(winning_card)
        winner_seat = PlaceAtTable(root=(lead_seat.root + winner_offset) % 4)
        partner_winning = winner_seat == self.place.partner()
        winners = [c for c in cards if c == high_card([*trick, c], trump=trump)]
        others = [c for c in cards if c not in winners]
        if partner_winning:
            threat = self._opponents_can_beat(trick, remaining_opponents)
            if not threat and others:
                score = {c: self._dump_score(c, hand) for c in others}
                return self._pick(others, score)
            if others:
                return min(others, key=lambda c: self._sluff_score(c, hand))
            return min(winners, key=lambda c: _rank(c.value))
        if winners:
            sure = [
                c
                for c in winners
                if not self._opponents_can_beat([*trick, c], remaining_opponents)
            ]
            if sure:
                return min(sure, key=lambda c: (card_points(c), _rank(c.value)))
            if not others:
                return min(winners, key=lambda c: _rank(c.value))
            trick_value = sum(card_points(c) for c in trick)
            if trick_value >= 10:
                return min(winners, key=lambda c: _rank(c.value))
            return min(others, key=lambda c: self._sluff_score(c, hand))
        return min(cards, key=lambda c: self._sluff_score(c, hand))

    def _opponents_can_beat(self, trick: list[Card], seats: list[PlaceAtTable]) -> bool:
        trump = self.beliefs.trump
        for seat in seats:
            for card in self.beliefs.possible_cards(seat):
                if card == high_card([*trick, card], trump=trump):
                    return True
        return False

    def _opponents_hold_suit(self, suit: Suit, seats: list[PlaceAtTable]) -> bool:
        return any(
            card.suit == suit
            for seat in seats
            for card in self.beliefs.possible_cards(seat)
        )

    def _master_of_suit(self, suit: Suit) -> Card | None:
        remaining = [
            card
            for seat in range(4)
            for card in self.beliefs.possible_cards(PlaceAtTable(root=seat))
            if card.suit == suit
        ]
        if not remaining:
            return None
        return max(remaining, key=lambda c: _rank(c.value))

    def _dump_score(self, card: Card, hand: list[Card]) -> int:
        if card.value == Value.Ten:
            return 100
        if card.value in (Value.King, Value.Ober):
            return 4 if self._keepable_half(card, hand) else 60
        if card.suit == self.beliefs.trump:
            return 3
        if card.value == Value.Ace:
            return 6
        if card.value == Value.Unter:
            return 20
        return 10 - _rank(card.value)

    def _sluff_score(self, card: Card, hand: list[Card]) -> int:
        score = 4 * card_points(card) + _rank(card.value)
        if card.value in (Value.King, Value.Ober) and self._keepable_half(card, hand):
            score += 40
        if self.beliefs.trump is not None and card.suit == self.beliefs.trump:
            score += 25
        if card.value == Value.Ace:
            score += 30
        return score
