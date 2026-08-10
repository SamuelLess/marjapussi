from __future__ import annotations

import random

import pytest

from marjapussi.agentic.agent import Agent
from marjapussi.agentic.agents.heuristic import HeuristicAgent
from marjapussi.agentic.runner import play_game
from marjapussi.events import GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards
from marjapussi.state import GameFinishedInfo, GameInfoPlayer
from marjapussi.types import Card


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


def _play(seed: int, agents: tuple[Agent, Agent, Agent, Agent]) -> GameFinishedInfo:
    game = MarjapussiGame(
        player_names=("Alice", "Bob", "Charlie", "Diana"),
        start_cards=_deal(seed),
    )
    return play_game(agents, game)


def _mixed_agents(
    seed: int, heuristic_seats: tuple[int, int]
) -> tuple[Agent, Agent, Agent, Agent]:
    rng = random.Random(seed)
    return tuple(
        HeuristicAgent(rng) if seat in heuristic_seats else RandomAgent(rng)
        for seat in range(4)
    )


class TestHeuristicGames:
    @pytest.mark.parametrize("seed", range(20))
    def test_full_heuristic_table_finishes(self, seed: int) -> None:
        rng = random.Random(seed + 100)
        info = _play(seed, tuple(HeuristicAgent(rng) for _ in range(4)))
        assert len(info.tricks) == 9

    def test_full_heuristic_table_is_reproducible(self) -> None:
        runs = []
        for _ in range(2):
            rng = random.Random(42)
            info = _play(7, tuple(HeuristicAgent(rng) for _ in range(4)))
            runs.append([event.last_action for event in info.all_events])
        assert runs[0] == runs[1]

    @pytest.mark.parametrize("seed", range(10))
    def test_mixed_table_even_seats_finishes(self, seed: int) -> None:
        info = _play(seed, _mixed_agents(seed + 200, heuristic_seats=(0, 2)))
        assert len(info.tricks) == 9

    @pytest.mark.parametrize("seed", range(10))
    def test_mixed_table_odd_seats_finishes(self, seed: int) -> None:
        info = _play(seed, _mixed_agents(seed + 300, heuristic_seats=(1, 3)))
        assert len(info.tricks) == 9


def _team_trick_points(info: GameFinishedInfo) -> tuple[int, int]:
    even = sum(t.points.root for t in info.tricks if t.winner.root % 2 == 0)
    odd = sum(t.points.root for t in info.tricks if t.winner.root % 2 == 1)
    return even, odd


class TestHeuristicVsRandom:
    def test_outperforms_random_team(self) -> None:
        seeds = range(30)
        edges: list[int] = []
        outcome_wins = 0
        decided = 0
        for seed in seeds:
            info = _play(seed, _mixed_agents(seed + 400, heuristic_seats=(0, 2)))
            heuristic_pts, random_pts = _team_trick_points(info)
            edges.append(heuristic_pts - random_pts)
            if info.playing_party is not None:
                decided += 1
                heuristic_playing = info.playing_party.root % 2 == 0
                if info.won == heuristic_playing:
                    outcome_wins += 1
        average_edge = sum(edges) / len(edges)
        assert average_edge >= 30
        assert decided > 0
        assert outcome_wins / decided >= 0.8
