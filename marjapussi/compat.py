from __future__ import annotations

from marjapussi.actions import (
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
from marjapussi.events import GameAction
from marjapussi.rules import sorted_cards
from marjapussi.types import Card, PlaceAtTable, Suit

SUIT_FROM_CHAR: dict[str, Suit] = {
    "r": Suit.Red,
    "s": Suit.Bells,
    "e": Suit.Acorns,
    "g": Suit.Green,
}
CHAR_FROM_SUIT: dict[Suit, str] = {v: k for k, v in SUIT_FROM_CHAR.items()}


def v2_action_to_v1(action: GameAction, *, is_bidding: bool) -> str | None:
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


def v1_action_to_v2(action_str: str) -> GameAction:
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


def v1_actions_to_v2(action_strings: list[str]) -> list[GameAction]:
    """Convert a full v1 action log to v2 actions, grouping pass actions."""
    v2_actions: list[GameAction] = []
    i = 0
    while i < len(action_strings):
        parts = action_strings[i].split(",")
        phase = parts[1]

        if phase in ("PASS", "PBCK"):
            player = PlaceAtTable(root=int(parts[0]))
            cards: list[Card] = []
            for j in range(4):
                card_str = action_strings[i + j].split(",")[2]
                cards.append(Card.model_validate(card_str))
            v2_actions.append(
                GameAction(
                    action_type=ActionPass(Pass=sorted_cards(cards)),
                    player=player,
                )
            )
            i += 4
        else:
            v2_actions.append(v1_action_to_v2(action_strings[i]))
            i += 1

    return v2_actions
