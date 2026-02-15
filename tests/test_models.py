from __future__ import annotations

import json
from pathlib import Path

import pytest

from marjapussi.v2.models import GameFinishedInfo
from marjapussi.v2.types import (
    Card,
    PlaceAtTable,
    Points,
    Suit,
    Value,
)

EXAMPLES_PATH = Path(__file__).resolve().parent / "examples.json"


class TestCardSerialization:
    def test_card_to_json(self) -> None:
        card = Card(suit=Suit.Red, value=Value.Ace)
        assert card.model_dump(mode="json") == "r-A"

    def test_card_from_string(self) -> None:
        card = Card.model_validate("g-O")
        assert card.suit == Suit.Green
        assert card.value == Value.Ober

    def test_card_round_trip(self) -> None:
        for s in Suit:
            for v in Value:
                card = Card(suit=s, value=v)
                serialized = card.model_dump(mode="json")
                restored = Card.model_validate(serialized)
                assert restored == card

    def test_card_invalid_format(self) -> None:
        with pytest.raises(ValueError):
            Card.model_validate("invalid")


class TestPlaceAtTable:
    def test_serializes_as_int(self) -> None:
        seat = PlaceAtTable(root=2)
        assert seat.model_dump(mode="json") == 2

    def test_partner(self) -> None:
        assert PlaceAtTable(root=0).partner() == PlaceAtTable(root=2)
        assert PlaceAtTable(root=1).partner() == PlaceAtTable(root=3)

    def test_next(self) -> None:
        assert PlaceAtTable(root=3).next() == PlaceAtTable(root=0)

    def test_party(self) -> None:
        assert PlaceAtTable(root=0).party() == PlaceAtTable(root=0)
        assert PlaceAtTable(root=3).party() == PlaceAtTable(root=1)


class TestPoints:
    def test_serializes_as_int(self) -> None:
        p = Points(root=42)
        assert p.model_dump(mode="json") == 42

    def test_arithmetic(self) -> None:
        a = Points(root=10)
        b = Points(root=5)
        assert a + b == Points(root=15)
        assert a - b == Points(root=5)
        assert a > b
        assert b < a


class TestGameFinishedInfo:
    @pytest.fixture
    def examples_json(self) -> list[dict]:
        with open(EXAMPLES_PATH) as f:
            return json.load(f)

    def test_parse_examples(self, examples_json: list[dict]) -> None:
        for i, raw in enumerate(examples_json):
            info = GameFinishedInfo.model_validate(raw)
            assert info.info.player_names is not None, f"Example {i} failed"

    def test_round_trip_examples(self, examples_json: list[dict]) -> None:
        for i, raw in enumerate(examples_json):
            info = GameFinishedInfo.model_validate(raw)
            reserialized = json.loads(info.model_dump_json())
            assert reserialized == raw, f"Example {i} round-trip mismatch"
