from __future__ import annotations

import random

import pytest

from marjapussi.actions import ActionPass
from marjapussi.compat import v1_action_to_v2, v1_actions_to_v2, v2_action_to_v1
from marjapussi.events import GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.legacy.game import MarjaPussi
from marjapussi.types import Card, PlaceAtTable


def _play_and_compare(seed: int) -> None:
    """Play a game on both v1 and v2 and assert legal actions match at every step."""
    random.seed(seed)
    v1 = MarjaPussi(["Alice", "Bob", "Charlie", "Diana"], log=False)

    names = ("Alice", "Bob", "Charlie", "Diana")
    v2_cards = tuple(
        [Card.model_validate(c) for c in v1.original_cards[name]] for name in names
    )
    v2 = MarjapussiGame(
        player_names=names,
        start_cards=v2_cards,
        time_fn=lambda: "test",
    )

    for i in range(4):
        v2.apply_action(GameAction(action_type="Start", player=PlaceAtTable(root=i)))

    rng = random.Random(seed + 1000)
    step = 0

    while v1.phase != "DONE":
        v2_phase = v2.phase

        # Passing has different granularity: v1 picks one card at a time,
        # v2 picks a 4-card combination in a single action.
        if v1.phase in ("PASS", "PBCK"):
            v2_legal = v2.legal_actions()
            pass_cards_str: list[str] = []
            for _ in range(4):
                chosen = rng.choice(v1.legal_actions())
                v1.act_action(chosen)
                pass_cards_str.append(chosen.split(",")[2])

            pass_cards = [Card.model_validate(c) for c in pass_cards_str]
            v2_match = next(
                (
                    a
                    for a in v2_legal
                    if isinstance(a.action_type, ActionPass)
                    and set(a.action_type.Pass) == set(pass_cards)
                ),
                None,
            )
            assert v2_match is not None, (
                f"Seed {seed}, step {step}: "
                f"no matching v2 pass action for {pass_cards_str}"
            )
            v2.apply_action(v2_match)
            step += 1
            continue

        v1_legal = v1.legal_actions()
        v2_legal = v2.legal_actions()

        is_bidding = v2_phase == "Bidding"
        v1_set = set(v1_legal)
        v2_as_v1 = {
            s
            for a in v2_legal
            if (s := v2_action_to_v1(a, is_bidding=is_bidding)) is not None
        }

        assert v1_set == v2_as_v1, (
            f"Seed {seed}, step {step}: legal action mismatch\n"
            f"v1 phase={v1.phase}, v2 phase={v2_phase}\n"
            f"v1 only: {v1_set - v2_as_v1}\n"
            f"v2 only: {v2_as_v1 - v1_set}"
        )

        chosen_v1 = rng.choice(sorted(v1_legal))
        assert v1.act_action(chosen_v1)
        v2.apply_action(v1_action_to_v2(chosen_v1))

        step += 1

    assert v2.finished, f"Seed {seed}: v2 game not finished when v1 is DONE"


def _replay_v1_as_v2(seed: int) -> None:
    """Play a v1 game, replay its actions on v2, and compare results."""
    random.seed(seed)
    v1 = MarjaPussi(["Alice", "Bob", "Charlie", "Diana"], log=False)

    rng = random.Random(seed + 1000)
    while v1.phase != "DONE":
        action = rng.choice(v1.legal_actions())
        v1.act_action(action)

    info = v1.end_info()
    names = ("Alice", "Bob", "Charlie", "Diana")
    v2_cards = tuple(
        [Card.model_validate(c) for c in info["cards"][name]] for name in names
    )

    v2 = MarjapussiGame(
        player_names=names,
        start_cards=v2_cards,
        time_fn=lambda: "test",
    )
    for i in range(4):
        v2.apply_action(GameAction(action_type="Start", player=PlaceAtTable(root=i)))

    for action in v1_actions_to_v2(info["actions"]):
        v2.apply_action(action)

    assert v2.finished
    v2_info = v2.to_finished_info()

    assert v2_info.game_value.root == info["game_value"]
    assert v2_info.schwarz_game == info["schwarz_game"]

    if info["playing_player"] is None:
        assert v2_info.no_one_played
    else:
        assert not v2_info.no_one_played

    v1_tricks = [t for t in info["tricks"] if t]
    assert len(v2_info.tricks) == len(v1_tricks)
    for v1_trick, v2_trick in zip(v1_tricks, v2_info.tricks, strict=True):
        v1_cards = [Card.model_validate(c) for c in v1_trick]
        assert list(v2_trick.cards) == v1_cards

    if info["passed_cards"]["forth"]:
        assert v2_info.passed_cards is not None
        v1_forth = {Card.model_validate(c) for c in info["passed_cards"]["forth"]}
        v1_back = {Card.model_validate(c) for c in info["passed_cards"]["back"]}
        assert set(v2_info.passed_cards[0]) == v1_forth
        assert set(v2_info.passed_cards[1]) == v1_back
    else:
        assert v2_info.passed_cards is None


class TestLegalActionParity:
    @pytest.mark.parametrize("seed", range(100))
    def test_parity(self, seed: int) -> None:
        _play_and_compare(seed)


class TestV1ToV2Replay:
    @pytest.mark.parametrize("seed", range(100))
    def test_replay_v1_as_v2(self, seed: int) -> None:
        _replay_v1_as_v2(seed)
