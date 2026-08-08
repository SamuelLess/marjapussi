from __future__ import annotations

import random

import pytest

from marjapussi.actions import ActionNewBid, ActionPass
from marjapussi.agentic.agent import Agent
from marjapussi.agentic.runner import play_game
from marjapussi.events import GameAction, GameEvent
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards
from marjapussi.state import GameFinishedInfo, GameInfoPlayer
from marjapussi.types import Card


class RandomAgent(Agent):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.views: list[GameInfoPlayer] = []

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        return self.rng.choice(view.legal_actions)

    def observe(self, view: GameInfoPlayer) -> None:
        self.views.append(view)


class MutatingRandomAgent(RandomAgent):
    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self.last_action: GameAction | None = None

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        self.last_action = super().select_action(view)
        return self.last_action

    def observe(self, view: GameInfoPlayer) -> None:
        view.meta_info.name = "corrupted"
        view.own_cards.clear()
        action_type = self.last_action.action_type if self.last_action else None
        if isinstance(action_type, ActionPass):
            action_type.Pass.clear()
        if isinstance(action_type, ActionNewBid):
            action_type.NewBid = -1


class StopBiddingAgent(Agent):
    def select_action(self, view: GameInfoPlayer) -> GameAction:
        return GameAction(action_type="StopBidding", player=self.place)


def _deal(seed: int) -> tuple[list[Card], list[Card], list[Card], list[Card]]:
    rng = random.Random(seed)
    cards = deck()
    rng.shuffle(cards)
    hands: list[list[Card]] = [[], [], [], []]
    for i, card in enumerate(cards):
        hands[i % 4].append(card)
    return tuple(sorted_cards(h) for h in hands)


def _play_random_game(
    seed: int,
) -> tuple[GameFinishedInfo, tuple[RandomAgent, RandomAgent, RandomAgent, RandomAgent]]:
    game = MarjapussiGame(
        player_names=("Alice", "Bob", "Charlie", "Diana"),
        start_cards=_deal(seed),
    )
    rng = random.Random(seed + 1000)
    agents = tuple(RandomAgent(rng) for _ in range(4))
    return play_game(agents, game), agents


class TestRandomAgentGame:
    def test_game_finishes(self) -> None:
        info, _ = _play_random_game(seed=1)
        assert isinstance(info, GameFinishedInfo)
        assert len(info.tricks) == 9

    def test_default_game_creation(self) -> None:
        random.seed(7)
        rng = random.Random(7)
        info = play_game(tuple(RandomAgent(rng) for _ in range(4)))
        assert info.info.player_names == ("Agent0", "Agent1", "Agent2", "Agent3")
        assert len(info.tricks) == 9

    @pytest.mark.parametrize("seed", range(10))
    def test_multiple_seeds(self, seed: int) -> None:
        info, _ = _play_random_game(seed)
        assert len(info.tricks) == 9


class TestAgentInterface:
    def test_runner_assigns_places(self) -> None:
        _, agents = _play_random_game(seed=3)
        assert [agent.place.root for agent in agents] == [0, 1, 2, 3]

    def test_observe_called_for_initial_state_and_every_action(self) -> None:
        info, agents = _play_random_game(seed=4)
        for agent in agents:
            assert len(agent.views) == len(info.all_events) + 1

    def test_views_only_contain_own_legal_actions(self) -> None:
        _, agents = _play_random_game(seed=5)
        for agent in agents:
            for view in agent.views:
                assert all(a.player == agent.place for a in view.legal_actions)

    def test_pass_events_hidden_from_opponents(self) -> None:
        info, agents = _play_random_game(seed=6)
        assert info.passed_cards is not None
        assert info.playing_party is not None
        for agent in agents:
            passing_partnership = agent.place.party() == info.playing_party
            pass_views = [
                view
                for view in agent.views
                if isinstance(view.last_event, GameEvent)
                and isinstance(view.last_event.last_action.action_type, ActionPass)
            ]
            hidden_views = [
                view for view in agent.views if view.last_event == "HiddenEvent"
            ]
            if passing_partnership:
                assert len(pass_views) == 2
                assert not hidden_views
            else:
                assert not pass_views
                assert len(hidden_views) == 2

    def test_views_hide_other_hands(self) -> None:
        info, agents = _play_random_game(seed=8)
        for agent in agents:
            own = agent.place.root
            for view in agent.views:
                start_cards = view.meta_info.player_start_cards
                assert start_cards[own] == info.info.player_start_cards[own]
                assert all(not start_cards[i] for i in range(4) if i != own)

    def test_view_mutation_does_not_corrupt_game(self) -> None:
        game = MarjapussiGame(
            player_names=("Alice", "Bob", "Charlie", "Diana"),
            start_cards=_deal(seed=9),
        )
        rng = random.Random(9)
        agents = tuple(MutatingRandomAgent(rng) for _ in range(4))
        info = play_game(agents, game)
        assert info.info.name == ""
        replayed = MarjapussiGame.replay(
            info.info, [event.last_action for event in info.all_events]
        )
        assert replayed.finished

    def test_illegal_action_raises(self) -> None:
        random.seed(10)
        agents = tuple(StopBiddingAgent() for _ in range(4))
        with pytest.raises(ValueError, match="illegal action"):
            play_game(agents)
