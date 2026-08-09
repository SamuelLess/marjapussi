from __future__ import annotations

import random


class TestV1GameLoop:
    def test_full_game(self) -> None:
        from marjapussi.legacy.game import MarjaPussi

        rng = random.Random(42)
        game = MarjaPussi(
            ["Alice", "Bob", "Charlie", "Diana"],
            log=False,
        )
        while game.phase != "DONE":
            actions = game.legal_actions()
            assert len(actions) > 0
            action = rng.choice(actions)
            result = game.act_action(action)
            assert result is True

    def test_end_info_structure(self) -> None:
        from marjapussi.legacy.game import MarjaPussi

        rng = random.Random(99)
        game = MarjaPussi(["A", "B", "C", "D"], log=False)
        while game.phase != "DONE":
            action = rng.choice(game.legal_actions())
            game.act_action(action)

        info = game.end_info()
        assert "players" in info
        assert "cards" in info
        assert "tricks" in info
        assert "actions" in info
        assert "game_value" in info
        assert "schwarz_game" in info
        assert len(info["players"]) == 4

    def test_state_dict_structure(self) -> None:
        from marjapussi.legacy.game import MarjaPussi

        game = MarjaPussi(["A", "B", "C", "D"], log=False)
        state = game.state_dict()
        assert "players_names" in state
        assert "game_phase" in state
        assert "legal_actions" in state
        assert len(state["players_names"]) == 4
