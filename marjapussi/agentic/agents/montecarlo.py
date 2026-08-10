from __future__ import annotations

import random

from marjapussi.actions import (
    ActionCardPlayed,
    ActionNewBid,
    ActionPass,
    ActionQuestion,
)
from marjapussi.agentic.beliefs import BeliefAgent
from marjapussi.events import (
    CallbackNewTrump,
    CallbackStillTrump,
    GameAction,
    GameEvent,
)
from marjapussi.game import MarjapussiGame
from marjapussi.rules import CARD_POINTS, sorted_cards, suit_points
from marjapussi.state import FinishedTrick, GameInfoPlayer, GamePhase
from marjapussi.types import Card, PlaceAtTable, Suit, Value

_STOP_PROBABILITY = 0.9
_ASSIGN_NODE_LIMIT = 10_000


def _pass_value(card: Card) -> int:
    bonus = 3 if card.value in (Value.King, Value.Ober) else 0
    return CARD_POINTS[card.value] + bonus


class MonteCarloAgent(BeliefAgent):
    """Determinized Monte Carlo agent: samples hidden hands and rolls out."""

    def __init__(
        self,
        rng: random.Random,
        *,
        simulations: int = 20,
        max_candidates: int = 12,
    ) -> None:
        super().__init__()
        self.rng = rng
        self.simulations = simulations
        self.max_candidates = max_candidates
        self._game_value = MarjapussiGame.START_VALUE
        self._playing: PlaceAtTable | None = None
        self._no_one_played = True
        self._trump_called: list[Suit] = []
        self._points = [0, 0, 0, 0]
        self._trump_calls: list[list[Suit]] = [[], [], [], []]
        self._asking = [0, 0, 0, 0]
        self._still_bidding = [True, True, True, True]
        self._tricks: list[FinishedTrick] = []
        self._prev_phase: GamePhase = "WaitingForStart"

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        legal = view.legal_actions
        if len(legal) == 1:
            return legal[0]
        candidates = self._candidates(view)
        if len(candidates) == 1:
            return candidates[0]
        totals = [0.0] * len(candidates)
        for _ in range(self.simulations):
            hands = self._sample_hands(view)
            for index, action in enumerate(candidates):
                game = self._clone(view, hands)
                game._apply_to_state(action)
                self._rollout(game)
                totals[index] += self._score(game)
        best = max(range(len(candidates)), key=lambda i: totals[i])
        return candidates[best]

    def on_view(self, view: GameInfoPlayer) -> None:
        event = view.last_event
        if isinstance(event, GameEvent):
            self._track_event(event, view)
        if (
            self._prev_phase == "Bidding"
            and view.game_phase != "Bidding"
            and self._game_value > MarjapussiGame.START_VALUE
        ):
            still = [s for s in range(4) if self._still_bidding[s]]
            self._playing = PlaceAtTable(root=still[0])
            self._no_one_played = False
        self._prev_phase = view.game_phase

    def _track_event(self, event: GameEvent, view: GameInfoPlayer) -> None:
        action = event.last_action
        seat = action.player.root
        action_type = action.action_type
        if isinstance(action_type, ActionNewBid):
            self._game_value = action_type.NewBid
        elif action_type == "StopBidding" and self._prev_phase == "Bidding":
            self._still_bidding[seat] = False
        elif isinstance(action_type, ActionQuestion):
            level = 1 if action_type.Question == "Yours" else 2
            self._asking[seat] = max(self._asking[seat], level)
        elif isinstance(action_type, ActionCardPlayed) and not view.current_trick:
            trick = view.last_trick
            assert trick is not None
            self._tricks.append(trick)
            self._points[trick.winner.root] += trick.points.root
        callback = event.callback
        if isinstance(callback, CallbackNewTrump | CallbackStillTrump):
            suit = (
                callback.NewTrump
                if isinstance(callback, CallbackNewTrump)
                else callback.StillTrump
            )
            self._trump_called.append(suit)
            if suit not in self._trump_calls[seat]:
                self._trump_calls[seat].append(suit)
                self._points[seat] += suit_points(suit)

    def _candidates(self, view: GameInfoPlayer) -> list[GameAction]:
        legal = view.legal_actions
        phase = view.game_phase
        if phase == "Bidding" or phase == "Raising":
            candidates = [a for a in legal if a.action_type == "StopBidding"]
            lowest: GameAction | None = None
            lowest_value = 0
            for action in legal:
                action_type = action.action_type
                if isinstance(action_type, ActionNewBid) and (
                    lowest is None or action_type.NewBid < lowest_value
                ):
                    lowest = action
                    lowest_value = action_type.NewBid
            if lowest is not None:
                candidates.append(lowest)
            return candidates
        if phase == "PassingForth" or phase == "PassingBack":
            return self._pass_candidates(legal, forth=phase == "PassingForth")
        if len(legal) <= self.max_candidates:
            return list(legal)
        return self.rng.sample(legal, self.max_candidates)

    def _pass_candidates(
        self, legal: list[GameAction], *, forth: bool
    ) -> list[GameAction]:
        def rank(action: GameAction) -> int:
            action_type = action.action_type
            assert isinstance(action_type, ActionPass)
            total = sum(_pass_value(card) for card in action_type.Pass)
            return -total if forth else total

        ranked = sorted(legal, key=rank)
        head = ranked[: (self.max_candidates + 1) // 2]
        rest = ranked[len(head) :]
        extra = self.rng.sample(rest, min(len(rest), self.max_candidates - len(head)))
        return head + extra

    def _sample_hands(
        self, view: GameInfoPlayer
    ) -> tuple[list[Card], list[Card], list[Card], list[Card]]:
        me = self.place.root
        counts = [0, 0, 0, 0]
        for offset, count in enumerate(view.players_cards_number_perspective):
            counts[(me + offset) % 4] = count
        assert view.own_cards is not None
        hands: list[list[Card]] = [[], [], [], []]
        hands[me] = list(view.own_cards)
        need: dict[int, int] = {}
        options: dict[Card, list[int]] = {}
        for seat in range(4):
            if seat == me:
                continue
            place = PlaceAtTable(root=seat)
            certain = self.beliefs.certain_cards(place)
            hands[seat] = list(certain)
            need[seat] = counts[seat] - len(certain)
            for card in self.beliefs.possible_cards(place) - certain:
                options.setdefault(card, []).append(seat)
        for card, seat in self._assign(options, need).items():
            hands[seat].append(card)
        return (
            sorted_cards(hands[0]),
            sorted_cards(hands[1]),
            sorted_cards(hands[2]),
            sorted_cards(hands[3]),
        )

    def _assign(
        self, options: dict[Card, list[int]], need: dict[int, int]
    ) -> dict[Card, int]:
        cards = sorted(options, key=lambda c: (len(options[c]), c))
        remaining = dict(need)
        result: dict[Card, int] = {}
        nodes = 0

        def backtrack(index: int) -> bool:
            nonlocal nodes
            if index == len(cards):
                return all(count == 0 for count in remaining.values())
            nodes += 1
            if nodes > _ASSIGN_NODE_LIMIT:
                return False
            card = cards[index]
            seats = [s for s in options[card] if remaining[s] > 0]
            self.rng.shuffle(seats)
            for seat in seats:
                remaining[seat] -= 1
                result[card] = seat
                if backtrack(index + 1):
                    return True
                remaining[seat] += 1
            result.pop(card, None)
            return False

        if backtrack(0):
            return result
        seats_left = [seat for seat, count in need.items() for _ in range(count)]
        self.rng.shuffle(seats_left)
        return dict(zip(sorted(options), seats_left, strict=False))

    def _clone(
        self,
        view: GameInfoPlayer,
        hands: tuple[list[Card], list[Card], list[Card], list[Card]],
    ) -> MarjapussiGame:
        game = MarjapussiGame(
            player_names=view.meta_info.player_names,
            start_cards=hands,
            time_fn=lambda: "",
        )
        game._phase = view.game_phase
        game._players_started = {0, 1, 2, 3}
        game._player_at_turn = PlaceAtTable(root=self.place.root)
        game._game_value = self._game_value
        game._trump = self.beliefs.trump
        game._trump_called = list(self._trump_called)
        game._playing_player = self._playing
        game._no_one_played = self._no_one_played
        game._current_trick = list(view.current_trick)
        game._trick_lead = PlaceAtTable(
            root=(self.place.root - len(view.current_trick)) % 4
        )
        game._all_tricks = list(self._tricks)
        game._first_trick_done = bool(self._tricks)
        for seat, player in enumerate(game._players):
            player.points = self._points[seat]
            player.still_bidding = self._still_bidding[seat]
            player.asking_level = self._asking[seat]
            player.trump_calls = list(self._trump_calls[seat])
        return game

    def _rollout(self, game: MarjapussiGame) -> None:
        rng = self.rng
        while not game.finished:
            phase = game.phase
            seat = game._player_at_turn
            if phase == "Bidding" or phase == "Raising":
                value = game._game_value
                if (
                    value + 5 > MarjapussiGame.MAX_VALUE
                    or rng.random() < _STOP_PROBABILITY
                ):
                    action = GameAction(action_type="StopBidding", player=seat)
                else:
                    action = GameAction(
                        action_type=ActionNewBid(NewBid=value + 5), player=seat
                    )
            elif phase == "PassingForth" or phase == "PassingBack":
                hand = game._players[seat.root].hand
                action = GameAction(
                    action_type=ActionPass(Pass=rng.sample(hand, 4)), player=seat
                )
            else:
                action = rng.choice(game.legal_actions())
            game._apply_to_state(action)

    def _score(self, game: MarjapussiGame) -> float:
        points = [player.points for player in game._players]
        us = self.place.root % 2
        score = float(points[us] + points[us + 2] - points[1 - us] - points[3 - us])
        if game._playing_player is not None and not game._no_one_played:
            playing = game._playing_player.root % 2
            made = points[playing] + points[playing + 2] >= game._game_value
            bonus = game._game_value if made else -game._game_value
            score += bonus if playing == us else -bonus
        return score
