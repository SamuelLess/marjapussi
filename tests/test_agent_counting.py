from __future__ import annotations

import random
import statistics

import pytest

from marjapussi.actions import ActionCardPlayed, ActionQuestion
from marjapussi.agentic.agent import Agent
from marjapussi.agentic.agents.counting import CountingAgent
from marjapussi.agentic.runner import play_game
from marjapussi.events import CallbackNewTrump, CallbackStillTrump, GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards, suit_points
from marjapussi.state import GameFinishedInfo, GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable


class RandomAgent(Agent):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        return self.rng.choice(view.legal_actions)


def _deal(seed: int) -> tuple[list[Card], list[Card], list[Card], list[Card]]:
    rng = random.Random(seed)
    cards = deck()
    rng.shuffle(cards)
    hands: list[list[Card]] = [[], [], [], []]
    for i, card in enumerate(cards):
        hands[i % 4].append(card)
    return tuple(sorted_cards(h) for h in hands)


def _play(agents: tuple[Agent, Agent, Agent, Agent], seed: int) -> GameFinishedInfo:
    game = MarjapussiGame(
        player_names=("Alice", "Bob", "Charlie", "Diana"),
        start_cards=_deal(seed),
    )
    return play_game(agents, game)


def _team_points(info: GameFinishedInfo, party: int) -> int:
    total = sum(t.points.root for t in info.tricks if t.winner.root % 2 == party)
    called: set[tuple[int, str]] = set()
    for event in info.all_events:
        callback = event.callback
        if isinstance(callback, CallbackNewTrump | CallbackStillTrump):
            suit = (
                callback.NewTrump
                if isinstance(callback, CallbackNewTrump)
                else callback.StillTrump
            )
            caller = event.last_action.player.root
            if (caller, suit) not in called:
                called.add((caller, suit))
                if caller % 2 == party:
                    total += suit_points(suit)
    return total


def _hand(spec: str) -> list[Card]:
    return [Card.model_validate(name) for name in spec.split()]


class TestFullGames:
    @pytest.mark.parametrize("seed", range(20))
    def test_counting_table_finishes(self, seed: int) -> None:
        agents = tuple(CountingAgent(random.Random(seed * 4 + i)) for i in range(4))
        info = _play(agents, seed)
        assert len(info.tricks) == 9


class TestMixedTables:
    @pytest.mark.parametrize("seed", range(6))
    @pytest.mark.parametrize("counting_party", (0, 1))
    def test_mixed_table_finishes(self, seed: int, counting_party: int) -> None:
        agents = tuple(
            CountingAgent(random.Random(seed * 10 + i))
            if i % 2 == counting_party
            else RandomAgent(random.Random(seed * 10 + i))
            for i in range(4)
        )
        info = _play(agents, seed)
        assert len(info.tricks) == 9


class TestHeadToHead:
    def test_counting_team_outperforms_random(self) -> None:
        diffs: list[int] = []
        for seed in range(30):
            counting_table = (
                CountingAgent(random.Random(seed * 10 + 1)),
                RandomAgent(random.Random(seed * 10 + 2)),
                CountingAgent(random.Random(seed * 10 + 3)),
                RandomAgent(random.Random(seed * 10 + 4)),
            )
            random_table = tuple(
                RandomAgent(random.Random(seed * 10 + i)) for i in range(1, 5)
            )
            counting_points = _team_points(_play(counting_table, seed), 0)
            random_points = _team_points(_play(random_table, seed), 0)
            diffs.append(counting_points - random_points)
        assert statistics.mean(diffs) > 20


class TestCountingDecision:
    def test_cashes_card_proven_unbeatable(self) -> None:
        start_cards = (
            _hand("r-Z r-K r-9 s-Z s-9 e-O e-7 g-A g-9"),
            _hand("r-A r-8 r-7 s-K s-8 s-7 e-Z e-9 e-8"),
            _hand("r-O r-6 s-O s-U e-K e-U g-U g-O g-8"),
            _hand("r-U s-A s-6 e-A e-6 g-Z g-K g-7 g-6"),
        )
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=start_cards,
        )
        agent = CountingAgent(random.Random(0))
        agent.place = PlaceAtTable(root=0)
        agent.observe(game.to_player_views()[0])

        def apply(action: GameAction) -> None:
            game.apply_action(action)
            agent.observe(game.to_player_views()[0])

        for seat in range(4):
            apply(GameAction(action_type="Start", player=PlaceAtTable(root=seat)))
        for seat in range(4):
            apply(GameAction(action_type="StopBidding", player=PlaceAtTable(root=seat)))
        for seat, name in ((0, "g-A"), (1, "r-A"), (2, "g-8"), (3, "g-7")):
            apply(
                GameAction(
                    action_type=ActionCardPlayed(CardPlayed=Card.model_validate(name)),
                    player=PlaceAtTable(root=seat),
                )
            )

        action = agent.select_action(game.to_player_views()[0])
        while isinstance(action.action_type, ActionQuestion):
            apply(action)
            apply(game.legal_actions()[0])
            action = agent.select_action(game.to_player_views()[0])

        assert action.action_type == ActionCardPlayed(
            CardPlayed=Card.model_validate("r-Z")
        )
