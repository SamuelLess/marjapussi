from __future__ import annotations

import random

import pytest

from marjapussi.game import MarjaPussi
from marjapussi.v2.actions import (
    ActionAnnounceTrump,
    ActionAnswer,
    ActionCardPlayed,
    ActionNewBid,
    ActionPass,
    ActionQuestion,
    AnswerNoHalf,
    AnswerYesHalf,
    AnswerYesPair,
    QuestionYourHalf,
)
from marjapussi.v2.events import GameAction
from marjapussi.v2.game import MarjapussiGame
from marjapussi.v2.types import Card, PlaceAtTable, Suit

SUIT_FROM_CHAR: dict[str, Suit] = {
    "r": Suit.Red,
    "s": Suit.Bells,
    "e": Suit.Acorns,
    "g": Suit.Green,
}
CHAR_FROM_SUIT: dict[Suit, str] = {v: k for k, v in SUIT_FROM_CHAR.items()}


def _v2_action_to_v1(action: GameAction, *, is_bidding: bool) -> str | None:
    """Convert a v2 GameAction to v1 string format."""
    p = action.player.root
    at = action.action_type

    if at == "Start":
        return None

    if at == "StopBidding":
        return f"{p},{'PROV' if is_bidding else 'PRMO'},0"

    if isinstance(at, ActionNewBid):
        return f"{p},{'PROV' if is_bidding else 'PRMO'},{at.NewBid}"

    if isinstance(at, ActionCardPlayed):
        return f"{p},TRCK,{at.CardPlayed}"

    if isinstance(at, ActionAnnounceTrump):
        return f"{p},QUES,my{CHAR_FROM_SUIT[at.AnnounceTrump]}"

    if isinstance(at, ActionQuestion):
        if at.Question == "Yours":
            return f"{p},QUES,you"
        if isinstance(at.Question, QuestionYourHalf):
            return f"{p},QUES,ou{CHAR_FROM_SUIT[at.Question.YourHalf]}"

    if isinstance(at, ActionAnswer):
        if at.Answer == "NoPair":
            return f"{p},ANSW,nmy"
        if isinstance(at.Answer, AnswerYesPair):
            return f"{p},ANSW,my{CHAR_FROM_SUIT[at.Answer.YesPair]}"
        if isinstance(at.Answer, AnswerYesHalf):
            return f"{p},ANSW,ou{CHAR_FROM_SUIT[at.Answer.YesHalf]}"
        if isinstance(at.Answer, AnswerNoHalf):
            return f"{p},ANSW,no{CHAR_FROM_SUIT[at.Answer.NoHalf]}"

    msg = f"Unhandled v2 action: {action}"
    raise ValueError(msg)


def _v1_action_to_v2(action_str: str) -> GameAction:
    """Convert a v1 action string to v2 GameAction."""
    parts = action_str.split(",")
    player = PlaceAtTable(root=int(parts[0]))
    phase, content = parts[1], parts[2]

    if phase in ("PROV", "PRMO"):
        val = int(content)
        if val == 0:
            return GameAction(action_type="StopBidding", player=player)
        return GameAction(action_type=ActionNewBid(NewBid=val), player=player)

    if phase == "TRCK":
        return GameAction(
            action_type=ActionCardPlayed(CardPlayed=Card.model_validate(content)),
            player=player,
        )

    if phase == "QUES":
        if content[:2] == "my":
            return GameAction(
                action_type=ActionAnnounceTrump(
                    AnnounceTrump=SUIT_FROM_CHAR[content[2]]
                ),
                player=player,
            )
        if content == "you":
            return GameAction(
                action_type=ActionQuestion(Question="Yours"), player=player
            )
        if content[:2] == "ou":
            return GameAction(
                action_type=ActionQuestion(
                    Question=QuestionYourHalf(YourHalf=SUIT_FROM_CHAR[content[2]])
                ),
                player=player,
            )

    if phase == "ANSW":
        if content == "nmy":
            return GameAction(action_type=ActionAnswer(Answer="NoPair"), player=player)
        if content[:2] == "my":
            return GameAction(
                action_type=ActionAnswer(
                    Answer=AnswerYesPair(YesPair=SUIT_FROM_CHAR[content[2]])
                ),
                player=player,
            )
        if content[:2] == "ou":
            return GameAction(
                action_type=ActionAnswer(
                    Answer=AnswerYesHalf(YesHalf=SUIT_FROM_CHAR[content[2]])
                ),
                player=player,
            )
        if content[:2] == "no":
            return GameAction(
                action_type=ActionAnswer(
                    Answer=AnswerNoHalf(NoHalf=SUIT_FROM_CHAR[content[2]])
                ),
                player=player,
            )

    msg = f"Unhandled v1 action: {action_str}"
    raise ValueError(msg)


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
            if (s := _v2_action_to_v1(a, is_bidding=is_bidding)) is not None
        }

        assert v1_set == v2_as_v1, (
            f"Seed {seed}, step {step}: legal action mismatch\n"
            f"v1 phase={v1.phase}, v2 phase={v2_phase}\n"
            f"v1 only: {v1_set - v2_as_v1}\n"
            f"v2 only: {v2_as_v1 - v1_set}"
        )

        chosen_v1 = rng.choice(sorted(v1_legal))
        assert v1.act_action(chosen_v1)
        v2.apply_action(_v1_action_to_v2(chosen_v1))

        step += 1

    assert v2.finished, f"Seed {seed}: v2 game not finished when v1 is DONE"


class TestLegalActionParity:
    @pytest.mark.parametrize("seed", range(100))
    def test_parity(self, seed: int) -> None:
        _play_and_compare(seed)
