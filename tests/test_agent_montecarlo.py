from __future__ import annotations

import random

import pytest

from marjapussi.agentic.agent import Agent
from marjapussi.agentic.agents.montecarlo import MonteCarloAgent
from marjapussi.agentic.runner import play_game
from marjapussi.events import CallbackNewTrump, CallbackStillTrump, GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards, suit_points
from marjapussi.state import GameFinishedInfo, GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable, Suit


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


def _small_agent(rng: random.Random) -> MonteCarloAgent:
    return MonteCarloAgent(rng, simulations=2, max_candidates=4)


def _party_points(info: GameFinishedInfo) -> tuple[int, int]:
    points = [0, 0, 0, 0]
    for trick in info.tricks:
        points[trick.winner.root] += trick.points.root
    called: list[set[Suit]] = [set(), set(), set(), set()]
    for event in info.all_events:
        callback = event.callback
        if isinstance(callback, CallbackNewTrump | CallbackStillTrump):
            suit = (
                callback.NewTrump
                if isinstance(callback, CallbackNewTrump)
                else callback.StillTrump
            )
            seat = event.last_action.player.root
            if suit not in called[seat]:
                called[seat].add(suit)
                points[seat] += suit_points(suit)
    return points[0] + points[2], points[1] + points[3]


def _play(seed: int, agents: tuple[Agent, Agent, Agent, Agent]) -> GameFinishedInfo:
    game = MarjapussiGame(
        player_names=("Alice", "Bob", "Charlie", "Diana"),
        start_cards=_deal(seed),
    )
    return play_game(agents, game)


class TestMonteCarloGames:
    @pytest.mark.parametrize("seed", range(5))
    def test_full_montecarlo_table_finishes(self, seed: int) -> None:
        agents = tuple(_small_agent(random.Random(seed * 10 + i)) for i in range(4))
        info = _play(seed, agents)
        assert len(info.tricks) == 9

    @pytest.mark.parametrize("seed", range(3))
    def test_mixed_table_finishes(self, seed: int) -> None:
        agents = tuple(
            _small_agent(random.Random(seed * 10 + i))
            if i % 2 == 0
            else RandomAgent(random.Random(seed * 10 + i))
            for i in range(4)
        )
        info = _play(seed, agents)
        assert len(info.tricks) == 9

    def test_outperforms_random_on_average(self) -> None:
        seeds = range(15)

        def _diff(seed: int, *, montecarlo: bool) -> int:
            agents = tuple(
                MonteCarloAgent(
                    random.Random(seed * 100 + i), simulations=6, max_candidates=8
                )
                if montecarlo and i % 2 == 0
                else RandomAgent(random.Random(seed * 100 + i))
                for i in range(4)
            )
            us, them = _party_points(_play(seed, agents))
            return us - them

        mc_edge = sum(_diff(seed, montecarlo=True) for seed in seeds) / len(seeds)
        base_edge = sum(_diff(seed, montecarlo=False) for seed in seeds) / len(seeds)
        assert mc_edge - base_edge > 40


class TestDeterminization:
    def _observing_agent(
        self, seed: int, seat: int, steps: int
    ) -> tuple[MarjapussiGame, MonteCarloAgent]:
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=_deal(seed),
        )
        agent = _small_agent(random.Random(seed))
        agent.place = PlaceAtTable(root=seat)
        agent.observe(game.to_player_views()[seat])
        rng = random.Random(seed + 500)
        for _ in range(steps):
            if game.finished:
                break
            game.apply_action(rng.choice(game.legal_actions()))
            agent.observe(game.to_player_views()[seat])
        return game, agent

    @pytest.mark.parametrize("steps", [4, 12, 20, 30])
    def test_samples_consistent_with_beliefs(self, steps: int) -> None:
        for seed in range(3):
            game, agent = self._observing_agent(seed, seat=1, steps=steps)
            view = game.to_player_views()[1]
            counts = [len(player.hand) for player in game._players]
            for _ in range(5):
                hands = agent._sample_hands(view)
                dealt = [card for hand in hands for card in hand]
                assert len(dealt) == len(set(dealt))
                assert hands[1] == view.own_cards
                for seat in range(4):
                    assert len(hands[seat]) == counts[seat]
                    if seat == 1:
                        continue
                    place = PlaceAtTable(root=seat)
                    hand = set(hands[seat])
                    assert agent.beliefs.certain_cards(place) <= hand
                    assert hand <= agent.beliefs.possible_cards(place)

    @pytest.mark.parametrize("seed", range(3))
    def test_clone_reconstructs_engine_state(self, seed: int) -> None:
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=_deal(seed),
        )
        agent = _small_agent(random.Random(seed))
        agent.place = PlaceAtTable(root=0)
        agent.observe(game.to_player_views()[0])
        rng = random.Random(seed + 500)
        checks = 0
        while not game.finished:
            if game.phase != "WaitingForStart" and game._player_at_turn == 0:
                view = game.to_player_views()[0]
                true_hands = tuple(list(player.hand) for player in game._players)
                clone = agent._clone(view, true_hands)
                assert clone.legal_actions() == game.legal_actions()
                assert [p.points for p in clone._players] == [
                    p.points for p in game._players
                ]
                assert clone._game_value == game._game_value
                assert clone._trump == game._trump
                assert clone._playing_player == game._playing_player
                assert clone._no_one_played == game._no_one_played
                checks += 1
            game.apply_action(rng.choice(game.legal_actions()))
            agent.observe(game.to_player_views()[0])
        assert checks > 0


class TestSelectAction:
    def test_single_legal_action_returned_without_simulation(self) -> None:
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=_deal(seed=0),
        )
        agent = MonteCarloAgent(random.Random(0), simulations=0)
        agent.place = PlaceAtTable(root=0)
        agent.observe(game.to_player_views()[0])
        view = game.to_player_views()[0]
        assert len(view.legal_actions) == 1
        assert agent.select_action(view) == view.legal_actions[0]

    def test_selected_actions_are_legal(self) -> None:
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=_deal(seed=2),
        )
        agents = tuple(_small_agent(random.Random(20 + i)) for i in range(4))
        for seat, agent in enumerate(agents):
            agent.place = PlaceAtTable(root=seat)
        for agent, view in zip(agents, game.to_player_views(), strict=True):
            agent.observe(view)
        while not game.finished:
            seat = game.legal_actions()[0].player
            view = game.to_player_views()[seat.root]
            action = agents[seat.root].select_action(view)
            assert action in view.legal_actions
            game.apply_action(action.model_copy(deep=True))
            for agent, new_view in zip(agents, game.to_player_views(), strict=True):
                agent.observe(new_view)
