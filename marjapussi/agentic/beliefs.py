from __future__ import annotations

from marjapussi.actions import (
    ActionAnnounceTrump,
    ActionAnswer,
    ActionCardPlayed,
    ActionPass,
    AnswerYesPair,
)
from marjapussi.agentic.agent import Agent
from marjapussi.events import (
    CallbackNewTrump,
    CallbackNoHalf,
    CallbackOnlyHalf,
    CallbackStillTrump,
    GameEvent,
)
from marjapussi.rules import deck, high_card
from marjapussi.state import GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable, Suit, Value


class BeliefState:
    """Tracks which cards each seat can or must hold.

    Feed every view of one seat exactly once and in order, starting with the
    initial view; only inferences that follow strictly from the rules are made.
    """

    def __init__(self) -> None:
        self.trump: Suit | None = None
        self._seat: int | None = None
        self._possible: list[set[Card]] = [set() for _ in range(4)]
        self._secure: list[set[Card]] = [set() for _ in range(4)]
        self._tricks_done = 0

    def possible_cards(self, seat: PlaceAtTable) -> set[Card]:
        """All cards the seat could currently hold."""
        return self._possible[seat.root] | self._secure[seat.root]

    def certain_cards(self, seat: PlaceAtTable) -> set[Card]:
        """Cards the seat is known to currently hold."""
        return set(self._secure[seat.root])

    def update(self, view: GameInfoPlayer) -> None:
        if self._seat is None:
            self._initialise(view)
        event = view.last_event
        if isinstance(event, GameEvent):
            self._apply_event(event, view)
        elif event == "HiddenEvent":
            self._apply_hidden_pass()
        self._sync_own_hand(view)

    def _initialise(self, view: GameInfoPlayer) -> None:
        starts = view.meta_info.player_start_cards
        self._seat = next(i for i in range(4) if starts[i])
        own = set(view.own_cards or [])
        rest = set(deck()) - own
        for i in range(4):
            if i != self._seat:
                self._possible[i] = set(rest)

    def _apply_event(self, event: GameEvent, view: GameInfoPlayer) -> None:
        action = event.last_action
        seat = action.player
        action_type = action.action_type

        callback = event.callback
        if isinstance(callback, CallbackNewTrump):
            self.trump = callback.NewTrump
        elif isinstance(callback, CallbackStillTrump):
            self.trump = callback.StillTrump
        elif isinstance(callback, CallbackNoHalf):
            self._remove_halves(seat, callback.NoHalf)
        elif isinstance(callback, CallbackOnlyHalf):
            self._remove_halves(seat.partner(), callback.OnlyHalf)

        if isinstance(action_type, ActionAnnounceTrump):
            self._mark_pair(seat, action_type.AnnounceTrump)
        elif isinstance(action_type, ActionAnswer) and isinstance(
            action_type.Answer, AnswerYesPair
        ):
            self._mark_pair(seat, action_type.Answer.YesPair)
        elif isinstance(action_type, ActionPass):
            self._apply_pass(seat, action_type.Pass)
        elif isinstance(action_type, ActionCardPlayed):
            self._infer_from_play(seat, action_type.CardPlayed, view)
            self._remove_everywhere(action_type.CardPlayed)
            if not view.current_trick:
                self._tricks_done += 1

    def _apply_hidden_pass(self) -> None:
        assert self._seat is not None
        left = (self._seat + 1) % 4
        right = (self._seat + 3) % 4
        union = self._possible[left] | self._possible[right]
        self._possible[left] = set(union)
        self._possible[right] = union

    def _apply_pass(self, sender: PlaceAtTable, cards: list[Card]) -> None:
        receiver = sender.partner()
        for card in cards:
            self._remove_everywhere(card)
            self._secure[receiver.root].add(card)

    def _mark_pair(self, seat: PlaceAtTable, suit: Suit) -> None:
        for value in (Value.King, Value.Ober):
            card = Card(suit=suit, value=value)
            self._remove_everywhere(card)
            self._secure[seat.root].add(card)

    def _remove_halves(self, seat: PlaceAtTable, suit: Suit) -> None:
        for value in (Value.King, Value.Ober):
            self._possible[seat.root].discard(Card(suit=suit, value=value))

    def _infer_from_play(
        self, seat: PlaceAtTable, card: Card, view: GameInfoPlayer
    ) -> None:
        if view.current_trick:
            trick_before = list(view.current_trick[:-1])
        else:
            assert view.last_trick is not None
            trick_before = list(view.last_trick.cards[:3])
        poss = self._possible[seat.root]
        first_trick = self._tricks_done == 0

        if not trick_before:
            if first_trick and card.value != Value.Ace:
                poss.difference_update({c for c in poss if c.value == Value.Ace})
                if card.suit != Suit.Green:
                    poss.difference_update({c for c in poss if c.suit == Suit.Green})
            return

        lead = trick_before[0].suit
        lead_ace = Card(suit=lead, value=Value.Ace)
        if first_trick and card != lead_ace:
            poss.discard(lead_ace)

        if card.suit != lead:
            poss.difference_update({c for c in poss if c.suit == lead})
            if self.trump is not None and card.suit != self.trump:
                poss.difference_update({c for c in poss if c.suit == self.trump})

        forced_pool = card.suit == lead or card.suit == self.trump
        if forced_pool and card != high_card([*trick_before, card], trump=self.trump):
            poss.difference_update(
                {
                    c
                    for c in poss
                    if c.suit == card.suit
                    and c == high_card([*trick_before, c], trump=self.trump)
                }
            )

    def _remove_everywhere(self, card: Card) -> None:
        for i in range(4):
            self._possible[i].discard(card)
            self._secure[i].discard(card)

    def _sync_own_hand(self, view: GameInfoPlayer) -> None:
        assert self._seat is not None
        own = set(view.own_cards or [])
        self._secure[self._seat] = own
        self._possible[self._seat] = set()
        for i in range(4):
            if i != self._seat:
                self._possible[i] -= own


class BeliefAgent(Agent):
    """Agent with belief tracking built in; override on_view instead of observe."""

    def __init__(self) -> None:
        self.beliefs = BeliefState()

    def observe(self, view: GameInfoPlayer) -> None:
        self.beliefs.update(view)
        self.on_view(view)

    def on_view(self, view: GameInfoPlayer) -> None:  # noqa: B027 - optional hook
        """Override instead of observe to keep belief updates intact."""
