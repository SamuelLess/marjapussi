from __future__ import annotations

import json
from pathlib import Path

import pytest

from marjapussi.agentic.arena import ArenaResults, run_arena

BOGUS_REGISTRY = [("ghost", "marjapussi.agentic.agents.ghost", "GhostAgent")]


@pytest.fixture(scope="module")
def tiny_results(tmp_path_factory: pytest.TempPathFactory) -> tuple[ArenaResults, Path]:
    out = tmp_path_factory.mktemp("arena") / "results"
    return run_arena(deals=4, seed=17, registry=BOGUS_REGISTRY, output_dir=out), out


class TestTinyArena:
    def test_random_mirror_match_completes(
        self, tiny_results: tuple[ArenaResults, Path]
    ) -> None:
        results, _ = tiny_results
        assert results.contestants == ["random"]
        assert len(results.records) == 8
        assert all(r.error is None for r in results.records)
        assert all(r.team_a == r.team_b == "random" for r in results.records)

    def test_duplicate_deals_both_orientations(
        self, tiny_results: tuple[ArenaResults, Path]
    ) -> None:
        results, _ = tiny_results
        seen = {(r.deal_seed, r.orientation) for r in results.records}
        assert seen == {(17 + i, o) for i in range(4) for o in (0, 1)}

    def test_mirror_results_symmetric(
        self, tiny_results: tuple[ArenaResults, Path]
    ) -> None:
        results, _ = tiny_results
        (matchup,) = results.matchups
        assert matchup.games == 8
        assert matchup.wins_a + matchup.wins_b + matchup.draws == 8
        (stats,) = results.agents
        assert stats.games == 16
        assert stats.wins == stats.losses
        assert stats.avg_point_diff == 0.0

    def test_reproducible(self, tiny_results: tuple[ArenaResults, Path]) -> None:
        results, _ = tiny_results
        again = run_arena(deals=4, seed=17, registry=BOGUS_REGISTRY)
        timing = {"duration_seconds", "decision_seconds"}
        assert [r.model_dump(exclude=timing) for r in again.records] == [
            r.model_dump(exclude=timing) for r in results.records
        ]

    def test_writes_valid_json_and_report(
        self, tiny_results: tuple[ArenaResults, Path]
    ) -> None:
        results, out = tiny_results
        loaded = json.loads((out / "results.json").read_text())
        assert loaded["ranking"] == results.ranking
        assert len(loaded["records"]) == len(results.records)
        report = (out / "report.md").read_text()
        assert "# Arena Report" in report
        assert "random" in report

    def test_bogus_registry_entry_skipped(
        self, tiny_results: tuple[ArenaResults, Path]
    ) -> None:
        results, _ = tiny_results
        (skipped,) = results.skipped
        assert skipped.name == "ghost"
        assert "ModuleNotFoundError" in skipped.reason


class TestRegistryFilters:
    def test_unknown_only_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown contestants"):
            run_arena(deals=1, registry=BOGUS_REGISTRY, only=["ghost"])
