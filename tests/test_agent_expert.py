from __future__ import annotations

import random
from statistics import mean

import pytest

from marjapussi.actions import ActionNewBid
from marjapussi.agentic.agent import Agent
from marjapussi.agentic.agents.expert import ExpertAgent
from marjapussi.agentic.runner import play_game
from marjapussi.events import CallbackNewTrump, CallbackStillTrump, GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards, suit_points
from marjapussi.state import GameFinishedInfo, GameInfoPlayer
from marjapussi.types import Card, Suit


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


def _fixed_deal(
    seat_zero: list[str],
) -> tuple[list[Card], list[Card], list[Card], list[Card]]:
    own = [Card.model_validate(c) for c in seat_zero]
    rest = [c for c in deck() if c not in own]
    hands: list[list[Card]] = [[], [], []]
    for i, card in enumerate(rest):
        hands[i % 3].append(card)
    return (
        sorted_cards(own),
        sorted_cards(hands[0]),
        sorted_cards(hands[1]),
        sorted_cards(hands[2]),
    )


def _play(
    agents: tuple[Agent, Agent, Agent, Agent],
    start_cards: tuple[list[Card], list[Card], list[Card], list[Card]],
) -> GameFinishedInfo:
    game = MarjapussiGame(
        player_names=("Alice", "Bob", "Charlie", "Diana"),
        start_cards=start_cards,
    )
    return play_game(agents, game)


def _party_points(info: GameFinishedInfo) -> tuple[int, int]:
    points = [0, 0]
    for trick in info.tricks:
        points[trick.winner.root % 2] += trick.points.root
    called: list[set[Suit]] = [set(), set(), set(), set()]
    for event in info.all_events:
        callback = event.callback
        if isinstance(callback, CallbackNewTrump):
            suit = callback.NewTrump
        elif isinstance(callback, CallbackStillTrump):
            suit = callback.StillTrump
        else:
            continue
        caller = event.last_action.player.root
        if suit not in called[caller]:
            called[caller].add(suit)
            points[caller % 2] += suit_points(suit)
    return points[0], points[1]


def _experts(seed: int, seats: tuple[int, ...]) -> dict[int, Agent]:
    return {seat: ExpertAgent(random.Random(seed * 10 + seat)) for seat in seats}


def _table(
    seed: int, expert_seats: tuple[int, ...]
) -> tuple[Agent, Agent, Agent, Agent]:
    experts = _experts(seed, expert_seats)
    random_rng = random.Random(seed + 5000)
    return tuple(experts.get(seat, RandomAgent(random_rng)) for seat in range(4))


class TestExpertGames:
    @pytest.mark.parametrize("seed", range(20))
    def test_full_expert_table_finishes(self, seed: int) -> None:
        info = _play(_table(seed, (0, 1, 2, 3)), _deal(seed))
        assert len(info.tricks) == 9

    @pytest.mark.parametrize("seed", range(8))
    def test_mixed_table_even_experts_finishes(self, seed: int) -> None:
        info = _play(_table(seed, (0, 2)), _deal(seed))
        assert len(info.tricks) == 9

    @pytest.mark.parametrize("seed", range(8))
    def test_mixed_table_odd_experts_finishes(self, seed: int) -> None:
        info = _play(_table(seed, (1, 3)), _deal(seed))
        assert len(info.tricks) == 9


class TestExpertEdge:
    def test_expert_pair_outscores_random_pair(self) -> None:
        margins: list[int] = []
        for seed in range(20):
            even, odd = _party_points(_play(_table(seed, (0, 2)), _deal(seed)))
            margins.append(even - odd)
            even, odd = _party_points(_play(_table(seed, (1, 3)), _deal(seed)))
            margins.append(odd - even)
        assert mean(margins) > 40


class TestExpertAuction:
    def test_strong_hand_wins_bidding_and_makes_contract(self) -> None:
        start_cards = _fixed_deal(
            ["r-A", "r-Z", "r-K", "r-O", "r-U", "e-A", "s-A", "g-A", "g-6"]
        )
        info = _play(_table(seed=1, expert_seats=(0, 1, 2, 3)), start_cards)
        assert any(
            isinstance(action_type, ActionNewBid) and player.root == 0
            for action_type, player in info.bidding_history
        )
        assert info.playing_party is not None
        assert info.playing_party.root == 0
        assert info.game_value.root >= 120
        assert info.won is True

    def test_weak_hand_stops_bidding_immediately(self) -> None:
        start_cards = _fixed_deal(
            ["r-6", "r-7", "r-8", "r-9", "s-6", "s-7", "s-8", "s-9", "e-6"]
        )
        info = _play(_table(seed=2, expert_seats=(0, 1, 2, 3)), start_cards)
        seat_zero_actions = [
            action_type
            for action_type, player in info.bidding_history
            if player.root == 0
        ]
        assert seat_zero_actions == ["StopBidding"]
        assert len(info.tricks) == 9
