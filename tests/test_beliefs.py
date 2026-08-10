from __future__ import annotations

import random

import pytest

from marjapussi.actions import (
    ActionAnnounceTrump,
    ActionAnswer,
    ActionCardPlayed,
    AnswerYesPair,
)
from marjapussi.agentic.beliefs import BeliefAgent, BeliefState
from marjapussi.agentic.runner import play_game
from marjapussi.events import GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, high_card, sorted_cards
from marjapussi.state import GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable, Value


class RandomBeliefAgent(BeliefAgent):
    def __init__(self, rng: random.Random) -> None:
        super().__init__()
        self.rng = rng
        self.on_view_calls = 0

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        return self.rng.choice(view.legal_actions)

    def on_view(self, view: GameInfoPlayer) -> None:
        self.on_view_calls += 1


def _deal(seed: int) -> tuple[list[Card], list[Card], list[Card], list[Card]]:
    rng = random.Random(seed)
    cards = deck()
    rng.shuffle(cards)
    hands: list[list[Card]] = [[], [], [], []]
    for i, card in enumerate(cards):
        hands[i % 4].append(card)
    return tuple(sorted_cards(h) for h in hands)


def _assert_sound(game: MarjapussiGame, beliefs: list[BeliefState]) -> None:
    hands = [set(view.own_cards) for view in game.to_player_views()]
    for belief in beliefs:
        for seat in range(4):
            place = PlaceAtTable(root=seat)
            assert belief.certain_cards(place) <= hands[seat]
            assert hands[seat] <= belief.possible_cards(place)


def _drive_game(seed: int) -> dict[str, int]:
    game = MarjapussiGame(
        player_names=("Alice", "Bob", "Charlie", "Diana"),
        start_cards=_deal(seed),
    )
    beliefs = [BeliefState() for _ in range(4)]
    for belief, view in zip(beliefs, game.to_player_views(), strict=True):
        belief.update(view)
    counters = dict.fromkeys(
        ("pair_known", "off_suit", "hidden_pass", "must_beat_lead", "must_beat_trump"),
        0,
    )
    rng = random.Random(seed + 1000)

    while not game.finished:
        pre_trick = list(game.to_player_views()[0].current_trick)
        action = rng.choice(game.legal_actions())
        game.apply_action(action)
        views = game.to_player_views()
        for belief, view in zip(beliefs, views, strict=True):
            belief.update(view)
            if view.last_event == "HiddenEvent":
                counters["hidden_pass"] += 1
        _assert_sound(game, beliefs)

        action_type = action.action_type
        pair_suit = None
        if isinstance(action_type, ActionAnnounceTrump):
            pair_suit = action_type.AnnounceTrump
        if isinstance(action_type, ActionAnswer) and isinstance(
            action_type.Answer, AnswerYesPair
        ):
            pair_suit = action_type.Answer.YesPair
        if pair_suit is not None:
            counters["pair_known"] += 1
            pair = {
                Card(suit=pair_suit, value=Value.King),
                Card(suit=pair_suit, value=Value.Ober),
            }
            for belief in beliefs:
                assert pair <= belief.certain_cards(action.player)
        if (
            isinstance(action_type, ActionCardPlayed)
            and pre_trick
            and action_type.CardPlayed.suit != pre_trick[0].suit
        ):
            counters["off_suit"] += 1
            lead = pre_trick[0].suit
            for belief in beliefs:
                assert not any(
                    c.suit == lead for c in belief.possible_cards(action.player)
                )
        if isinstance(action_type, ActionCardPlayed) and pre_trick:
            card = action_type.CardPlayed
            trump = beliefs[0].trump
            lead = pre_trick[0].suit
            forced_pool = card.suit == lead or card.suit == trump
            if forced_pool and card != high_card([*pre_trick, card], trump=trump):
                key = "must_beat_lead" if card.suit == lead else "must_beat_trump"
                counters[key] += 1
                for belief in beliefs:
                    assert not any(
                        c.suit == card.suit
                        and c == high_card([*pre_trick, c], trump=trump)
                        for c in belief.possible_cards(action.player)
                    )

    for belief in beliefs:
        for seat in range(4):
            assert not belief.possible_cards(PlaceAtTable(root=seat))
    return counters


class TestBeliefState:
    @pytest.mark.parametrize("seed", range(5))
    def test_sound_throughout_random_game(self, seed: int) -> None:
        _drive_game(seed)

    def test_inference_paths_covered(self) -> None:
        totals: dict[str, int] = {}
        for seed in range(12):
            for key, count in _drive_game(seed).items():
                totals[key] = totals.get(key, 0) + count
        assert all(count > 0 for count in totals.values()), totals


class TestBeliefAgent:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            BeliefAgent()

    def test_beliefs_updated_despite_on_view_override(self) -> None:
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=_deal(seed=20),
        )
        rng = random.Random(20)
        agents = tuple(RandomBeliefAgent(rng) for _ in range(4))
        info = play_game(agents, game)
        for agent in agents:
            assert agent.on_view_calls == len(info.all_events) + 1
            for seat in range(4):
                assert not agent.beliefs.possible_cards(PlaceAtTable(root=seat))
