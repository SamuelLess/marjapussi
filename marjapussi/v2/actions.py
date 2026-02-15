from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from marjapussi.v2.types import Card, Suit


class QuestionYourHalf(BaseModel):
    YourHalf: Suit


QuestionType = Literal["Yours"] | QuestionYourHalf


class AnswerYesPair(BaseModel):
    YesPair: Suit


class AnswerYesHalf(BaseModel):
    YesHalf: Suit


class AnswerNoHalf(BaseModel):
    NoHalf: Suit


AnswerType = Literal["NoPair"] | AnswerYesPair | AnswerYesHalf | AnswerNoHalf


class ActionNewBid(BaseModel):
    NewBid: int


class ActionPass(BaseModel):
    Pass: list[Card]


class ActionCardPlayed(BaseModel):
    CardPlayed: Card


class ActionQuestion(BaseModel):
    Question: QuestionType


class ActionAnswer(BaseModel):
    Answer: AnswerType


class ActionAnnounceTrump(BaseModel):
    AnnounceTrump: Suit


ActionType = (
    Literal[
        "Start",
        "StopBidding",
        "UndoRequest",
        "UndoDecline",
        "UndoAccept",
    ]
    | ActionNewBid
    | ActionPass
    | ActionCardPlayed
    | ActionQuestion
    | ActionAnswer
    | ActionAnnounceTrump
)
