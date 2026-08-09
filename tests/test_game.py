from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from marjapussi.actions import ActionCardPlayed, ActionNewBid, ActionPass
from marjapussi.events import GameAction, GameEvent
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards
from marjapussi.state import GameFinishedInfo
from marjapussi.types import Card, PlaceAtTable

EXAMPLES_PATH = Path(__file__).resolve().parent / "examples.json"

FIXED_TIME = "2026-02-15 13:05:17"


def _fixed_time() -> str:
    return FIXED_TIME


def _deal(
    seed: int = 42,
) -> tuple[
    tuple[str, str, str, str],
    tuple[list[Card], list[Card], list[Card], list[Card]],
]:
    rng = random.Random(seed)
    cards = deck()
    rng.shuffle(cards)
    hands: list[list[Card]] = [[], [], [], []]
    for i, card in enumerate(cards):
        hands[i % 4].append(card)
    return (
        ("Alice", "Bob", "Charlie", "Diana"),
        tuple(sorted_cards(h) for h in hands),
    )


def _play_random_game(
    seed: int = 42,
) -> MarjapussiGame:
    names, cards = _deal(seed)
    game = MarjapussiGame(
        player_names=names,
        start_cards=cards,
        time_fn=_fixed_time,
    )
    rng = random.Random(seed + 1000)
    while not game.finished:
        actions = game.legal_actions()
        action = rng.choice(actions)
        game.apply_action(action)
    return game


class TestRandomGame:
    def test_game_finishes(self) -> None:
        game = _play_random_game(seed=1)
        assert game.finished

    def test_to_finished_info_valid(self) -> None:
        game = _play_random_game(seed=2)
        info = game.to_finished_info()
        assert isinstance(info, GameFinishedInfo)
        assert len(info.tricks) == 9
        assert len(info.all_events) > 0

    @pytest.mark.parametrize("seed", range(10))
    def test_multiple_seeds(self, seed: int) -> None:
        game = _play_random_game(seed=seed)
        info = game.to_finished_info()
        assert len(info.tricks) == 9

    def test_nine_tricks_36_cards(self) -> None:
        game = _play_random_game(seed=5)
        info = game.to_finished_info()
        all_cards_played = []
        for trick in info.tricks:
            all_cards_played.extend(trick.cards)
        assert len(all_cards_played) == 36
        assert len(set(all_cards_played)) == 36


class TestReplayDeterminism:
    def test_replay_produces_same_state(self) -> None:
        game = _play_random_game(seed=7)
        info = game.to_finished_info()

        replayed = MarjapussiGame.replay(
            info.info,
            game.actions,
            time_fn=_fixed_time,
        )
        assert replayed.finished
        replayed_info = replayed.to_finished_info()

        assert replayed_info.game_value == info.game_value
        assert replayed_info.won == info.won
        assert replayed_info.no_one_played == info.no_one_played
        assert replayed_info.schwarz_game == info.schwarz_game
        assert replayed_info.playing_party == info.playing_party
        assert len(replayed_info.tricks) == len(info.tricks)
        for i, (t1, t2) in enumerate(
            zip(replayed_info.tricks, info.tricks, strict=True)
        ):
            assert t1.cards == t2.cards, f"Trick {i} mismatch"
            assert t1.winner == t2.winner, f"Winner {i} mismatch"
            assert t1.points == t2.points, f"Points {i} mismatch"

    @pytest.mark.parametrize("seed", range(5))
    def test_replay_round_trip_json(self, seed: int) -> None:
        game = _play_random_game(seed=seed)
        info = game.to_finished_info()
        json1 = info.model_dump(mode="json")

        replayed = MarjapussiGame.replay(
            info.info,
            game.actions,
            time_fn=_fixed_time,
        )
        json2 = replayed.to_finished_info().model_dump(mode="json")

        assert json1 == json2


class TestActionLogImmutability:
    def test_actions_returns_tuple(self) -> None:
        names, cards = _deal()
        game = MarjapussiGame(
            player_names=names,
            start_cards=cards,
            time_fn=_fixed_time,
        )
        assert isinstance(game.actions, tuple)

    def test_actions_cannot_mutate_internal(self) -> None:
        game = _play_random_game(seed=3)
        actions = game.actions
        n = len(actions)
        # Tuple is immutable so this should not affect the game
        _ = actions + (
            GameAction(
                action_type="Start",
                player=PlaceAtTable(root=0),
            ),
        )
        assert len(game.actions) == n


class TestIllegalAction:
    def test_raises_on_illegal_action(self) -> None:
        names, cards = _deal()
        game = MarjapussiGame(
            player_names=names,
            start_cards=cards,
            time_fn=_fixed_time,
        )
        with pytest.raises(ValueError, match="Illegal action"):
            game.apply_action(
                GameAction(
                    action_type=ActionCardPlayed(CardPlayed=Card.model_validate("r-A")),
                    player=PlaceAtTable(root=0),
                )
            )


class TestPlayerViews:
    def test_last_event_is_hidden_for_other_party_on_pass(self) -> None:
        names, cards = _deal()
        game = MarjapussiGame(
            player_names=names,
            start_cards=cards,
            time_fn=_fixed_time,
        )

        for i in range(4):
            game.apply_action(
                GameAction(action_type="Start", player=PlaceAtTable(root=i))
            )

        game.apply_action(
            GameAction(
                action_type=ActionNewBid(NewBid=120),
                player=PlaceAtTable(root=0),
            )
        )
        game.apply_action(
            GameAction(action_type="StopBidding", player=PlaceAtTable(root=1))
        )
        game.apply_action(
            GameAction(action_type="StopBidding", player=PlaceAtTable(root=2))
        )
        game.apply_action(
            GameAction(action_type="StopBidding", player=PlaceAtTable(root=3))
        )

        pass_action = next(
            a for a in game.legal_actions() if isinstance(a.action_type, ActionPass)
        )
        game.apply_action(pass_action)

        views = game.to_player_views()

        assert isinstance(views[0].last_event, GameEvent)
        assert isinstance(views[2].last_event, GameEvent)
        assert views[1].last_event == "HiddenEvent"
        assert views[3].last_event == "HiddenEvent"

    def test_last_non_pass_event_is_public_for_all_players(self) -> None:
        names, cards = _deal()
        game = MarjapussiGame(
            player_names=names,
            start_cards=cards,
            time_fn=_fixed_time,
        )

        game.apply_action(GameAction(action_type="Start", player=PlaceAtTable(root=0)))
        views = game.to_player_views()

        for i in range(4):
            assert isinstance(views[i].last_event, GameEvent)


class TestExamplesReplay:
    @pytest.fixture
    def examples(self) -> list[dict]:
        with open(EXAMPLES_PATH) as f:
            return json.load(f)

    def test_parse_and_validate_examples(self, examples: list[dict]) -> None:
        for i, raw in enumerate(examples):
            info = GameFinishedInfo.model_validate(raw)
            assert info.info.player_names is not None, f"Example {i}"
            assert len(info.tricks) == 9, f"Example {i}"
            assert len(info.all_events) > 0, f"Example {i}"
