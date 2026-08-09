from __future__ import annotations

import argparse
import importlib
import random
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from marjapussi.actions import ActionNewBid
from marjapussi.agentic.agent import Agent
from marjapussi.agentic.runner import play_game
from marjapussi.events import CallbackNewTrump, CallbackStillTrump, GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.rules import deck, sorted_cards, suit_points
from marjapussi.state import GameFinishedInfo, GameInfoPlayer
from marjapussi.types import Card, PlaceAtTable, Suit

REGISTRY: list[tuple[str, str, str]] = [
    ("heuristic", "marjapussi.agentic.agents.heuristic", "HeuristicAgent"),
    ("counting", "marjapussi.agentic.agents.counting", "CountingAgent"),
    ("montecarlo", "marjapussi.agentic.agents.montecarlo", "MonteCarloAgent"),
    ("expert", "marjapussi.agentic.agents.expert", "ExpertAgent"),
]
SLOW_CONTESTANTS = frozenset({"montecarlo"})
BASELINE_NAME = "random"

AgentFactory = Callable[[random.Random], Agent]

Deal = tuple[list[Card], list[Card], list[Card], list[Card]]


class RandomAgent(Agent):
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        return self.rng.choice(view.legal_actions)


class _AgentFailure(Exception):
    def __init__(self, team: str, reason: str) -> None:
        super().__init__(reason)
        self.team = team
        self.reason = reason


class _TimedAgent(Agent):
    def __init__(self, inner: Agent, team: str) -> None:
        self.inner = inner
        self.team = team
        self.decision_seconds = 0.0
        self.decisions = 0

    @property
    def place(self) -> PlaceAtTable:  # type: ignore[override]
        return self.inner.place

    @place.setter
    def place(self, value: PlaceAtTable) -> None:
        self.inner.place = value

    def select_action(self, view: GameInfoPlayer) -> GameAction:
        start = time.perf_counter()
        try:
            action = self.inner.select_action(view)
        except Exception as exc:
            raise _AgentFailure(self.team, f"select_action raised {exc!r}") from exc
        finally:
            self.decision_seconds += time.perf_counter() - start
            self.decisions += 1
        if action not in view.legal_actions:
            raise _AgentFailure(self.team, f"illegal action {action}")
        return action

    def observe(self, view: GameInfoPlayer) -> None:
        try:
            self.inner.observe(view)
        except Exception as exc:
            raise _AgentFailure(self.team, f"observe raised {exc!r}") from exc


class SkippedEntry(BaseModel):
    name: str
    import_path: str
    class_name: str
    reason: str


class ArenaConfig(BaseModel):
    deals: int
    seed: int
    include_slow: bool
    slow_deals: int
    only: list[str] | None = None


class GameRecord(BaseModel):
    deal_seed: int
    orientation: int
    team_a: str
    team_b: str
    duration_seconds: float
    result_a: float
    error: str | None = None
    error_team: str | None = None
    game_value: int | None = None
    auction_bid: int | None = None
    auction_winner: str | None = None
    avg_raise: float | None = None
    playing_team: str | None = None
    won: bool | None = None
    no_one_played: bool | None = None
    schwarz: bool | None = None
    points_a: int | None = None
    points_b: int | None = None
    call_points_a: int | None = None
    call_points_b: int | None = None
    tricks_a: int | None = None
    tricks_b: int | None = None
    decision_seconds: dict[str, float] = Field(default_factory=dict)
    decisions: dict[str, int] = Field(default_factory=dict)


class MatchupStats(BaseModel):
    team_a: str
    team_b: str
    games: int
    wins_a: int
    wins_b: int
    draws: int
    forfeits_a: int
    forfeits_b: int
    score_a: float
    avg_point_diff_a: float | None = None


class BucketStats(BaseModel):
    played: int = 0
    made: int = 0


class AgentStats(BaseModel):
    name: str
    games: int
    wins: int
    draws: int
    losses: int
    forfeits: int
    score: float
    avg_points: float | None = None
    avg_point_diff: float | None = None
    avg_call_points: float | None = None
    avg_tricks: float | None = None
    auction_wins: int = 0
    auction_win_rate: float | None = None
    avg_winning_bid: float | None = None
    avg_raise: float | None = None
    contracts_played: int = 0
    contracts_made: int = 0
    contract_success_rate: float | None = None
    contracts_by_bucket: dict[str, BucketStats] = Field(default_factory=dict)
    games_defending: int = 0
    sets_as_defender: int = 0
    set_rate_as_defender: float | None = None
    avg_points_conceded: float | None = None
    no_one_played_rate: float | None = None
    schwarz_rate: float | None = None
    mean_decision_seconds: float | None = None
    mean_game_seconds: float | None = None
    errors: list[str] = Field(default_factory=list)


class ArenaResults(BaseModel):
    config: ArenaConfig
    contestants: list[str]
    skipped: list[SkippedEntry]
    records: list[GameRecord]
    matchups: list[MatchupStats]
    agents: list[AgentStats]
    ranking: list[str]


def discover_contestants(
    registry: list[tuple[str, str, str]],
) -> tuple[dict[str, AgentFactory], list[SkippedEntry]]:
    factories: dict[str, AgentFactory] = {}
    skipped: list[SkippedEntry] = []
    for name, import_path, class_name in registry:
        try:
            module = importlib.import_module(import_path)
            factories[name] = getattr(module, class_name)
        except Exception as exc:
            skipped.append(
                SkippedEntry(
                    name=name,
                    import_path=import_path,
                    class_name=class_name,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )
    return factories, skipped


def _make_deal(seed: int) -> Deal:
    rng = random.Random(seed)
    cards = deck()
    rng.shuffle(cards)
    hands: list[list[Card]] = [[], [], [], []]
    for i, card in enumerate(cards):
        hands[i % 4].append(card)
    return (
        sorted_cards(hands[0]),
        sorted_cards(hands[1]),
        sorted_cards(hands[2]),
        sorted_cards(hands[3]),
    )


def _bucket(game_value: int) -> str:
    if game_value <= 140:
        return "115-140"
    if game_value <= 180:
        return "145-180"
    if game_value <= 240:
        return "185-240"
    return "245-420"


def _call_points(info: GameFinishedInfo) -> dict[int, int]:
    called: set[tuple[int, Suit]] = set()
    points = {0: 0, 1: 0}
    for event in info.all_events:
        callback = event.callback
        if isinstance(callback, CallbackNewTrump):
            suit = callback.NewTrump
        elif isinstance(callback, CallbackStillTrump):
            suit = callback.StillTrump
        else:
            continue
        player = event.last_action.player
        if (player.root, suit) in called:
            continue
        called.add((player.root, suit))
        points[player.party().root] += suit_points(suit)
    return points


def _auction_summary(
    info: GameFinishedInfo,
) -> tuple[int | None, PlaceAtTable | None, float | None]:
    bids: list[int] = []
    winner: PlaceAtTable | None = None
    for action_type, player in info.bidding_history:
        if isinstance(action_type, ActionNewBid):
            bids.append(action_type.NewBid)
            winner = player
    if not bids:
        return None, None, None
    previous = [MarjapussiGame.START_VALUE, *bids[:-1]]
    raises = [b - prev for prev, b in zip(previous, bids, strict=True)]
    return bids[-1], winner, sum(raises) / len(raises)


def _play_one(
    team_a: str,
    factory_a: AgentFactory,
    team_b: str,
    factory_b: AgentFactory,
    deal_seed: int,
    deal: Deal,
    orientation: int,
) -> GameRecord:
    teams = ("a", "b", "a", "b") if orientation == 0 else ("b", "a", "b", "a")
    names = {"a": team_a, "b": team_b}
    factories = {"a": factory_a, "b": factory_b}
    agents = tuple(
        _TimedAgent(
            factories[side](random.Random(f"{deal_seed}:{orientation}:{seat}:{side}")),
            side,
        )
        for seat, side in enumerate(teams)
    )
    game = MarjapussiGame(
        player_names=tuple(f"{names[side]}_{seat}" for seat, side in enumerate(teams)),
        start_cards=tuple(list(hand) for hand in deal),
    )
    party_a = 0 if orientation == 0 else 1

    start = time.perf_counter()
    try:
        info = play_game(agents, game)
    except _AgentFailure as exc:
        return GameRecord(
            deal_seed=deal_seed,
            orientation=orientation,
            team_a=team_a,
            team_b=team_b,
            duration_seconds=time.perf_counter() - start,
            result_a=0.0 if exc.team == "a" else 1.0,
            error=exc.reason,
            error_team=names[exc.team],
        )
    except Exception as exc:
        return GameRecord(
            deal_seed=deal_seed,
            orientation=orientation,
            team_a=team_a,
            team_b=team_b,
            duration_seconds=time.perf_counter() - start,
            result_a=0.5,
            error=f"engine error: {exc!r}",
        )
    duration = time.perf_counter() - start

    points = {0: 0, 1: 0}
    tricks = {0: 0, 1: 0}
    for trick in info.tricks:
        party = trick.winner.party().root
        points[party] += trick.points.root
        tricks[party] += 1
    call_points = _call_points(info)

    playing_team = None
    result_a = 0.5
    if info.playing_party is not None and info.won is not None:
        playing_is_a = info.playing_party.party().root == party_a
        playing_team = team_a if playing_is_a else team_b
        result_a = 1.0 if playing_is_a == info.won else 0.0

    auction_bid, auction_winner_seat, avg_raise = _auction_summary(info)
    auction_winner = None
    if auction_winner_seat is not None:
        auction_is_a = auction_winner_seat.party().root == party_a
        auction_winner = team_a if auction_is_a else team_b

    decision_seconds = {"a": 0.0, "b": 0.0}
    decisions = {"a": 0, "b": 0}
    for agent, side in zip(agents, teams, strict=True):
        decision_seconds[side] += agent.decision_seconds
        decisions[side] += agent.decisions

    return GameRecord(
        deal_seed=deal_seed,
        orientation=orientation,
        team_a=team_a,
        team_b=team_b,
        duration_seconds=duration,
        result_a=result_a,
        game_value=info.game_value.root,
        auction_bid=auction_bid,
        auction_winner=auction_winner,
        avg_raise=avg_raise,
        playing_team=playing_team,
        won=info.won,
        no_one_played=info.no_one_played,
        schwarz=info.schwarz_game,
        points_a=points[party_a],
        points_b=points[1 - party_a],
        call_points_a=call_points[party_a],
        call_points_b=call_points[1 - party_a],
        tricks_a=tricks[party_a],
        tricks_b=tricks[1 - party_a],
        decision_seconds=decision_seconds,
        decisions=decisions,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sides_for(name: str, record: GameRecord) -> list[str]:
    sides = []
    if record.team_a == name:
        sides.append("a")
    if record.team_b == name:
        sides.append("b")
    return sides


def _matchup_stats(team_a: str, team_b: str, records: list[GameRecord]) -> MatchupStats:
    wins_a = sum(1 for r in records if r.result_a == 1.0)
    wins_b = sum(1 for r in records if r.result_a == 0.0)
    draws = sum(1 for r in records if r.result_a == 0.5)
    diffs = [
        float(r.points_a - r.points_b)
        for r in records
        if r.points_a is not None and r.points_b is not None
    ]
    return MatchupStats(
        team_a=team_a,
        team_b=team_b,
        games=len(records),
        wins_a=wins_a,
        wins_b=wins_b,
        draws=draws,
        forfeits_a=sum(1 for r in records if r.error_team == team_a),
        forfeits_b=sum(1 for r in records if r.error_team == team_b),
        score_a=(wins_a + 0.5 * draws) / len(records) if records else 0.0,
        avg_point_diff_a=_mean(diffs),
    )


def _agent_stats(name: str, records: list[GameRecord]) -> AgentStats:
    played = [(r, side) for r in records for side in _sides_for(name, r)]
    games = len(played)
    wins = draws = losses = forfeits = 0
    points: list[float] = []
    diffs: list[float] = []
    call_points: list[float] = []
    tricks: list[float] = []
    auction_wins = 0
    auction_games = 0
    winning_bids: list[float] = []
    raises: list[float] = []
    buckets: dict[str, BucketStats] = {}
    contracts_played = contracts_made = 0
    defending = sets_as_defender = 0
    conceded: list[float] = []
    no_one_played = 0
    schwarz = 0
    finished = 0
    decision_seconds = 0.0
    decisions = 0
    game_seconds: list[float] = []
    errors: list[str] = []

    for record, side in played:
        result = record.result_a if side == "a" else 1.0 - record.result_a
        if record.error is not None:
            if record.error_team == name:
                forfeits += 1
                errors.append(
                    f"deal {record.deal_seed} orientation {record.orientation}"
                    f" vs {record.team_b if side == 'a' else record.team_a}:"
                    f" {record.error}"
                )
                losses += 1
            elif record.error_team is None:
                draws += 1
            else:
                wins += 1
            continue
        finished += 1
        if result == 1.0:
            wins += 1
        elif result == 0.0:
            losses += 1
        else:
            draws += 1

        own = record.points_a if side == "a" else record.points_b
        other = record.points_b if side == "a" else record.points_a
        own_tricks = record.tricks_a if side == "a" else record.tricks_b
        assert own is not None and other is not None and own_tricks is not None
        points.append(float(own))
        diffs.append(float(own - other))
        own_calls = record.call_points_a if side == "a" else record.call_points_b
        if own_calls is not None:
            call_points.append(float(own_calls))
        tricks.append(float(own_tricks))
        game_seconds.append(record.duration_seconds)
        decision_seconds += record.decision_seconds[side]
        decisions += record.decisions[side]
        if record.no_one_played:
            no_one_played += 1
        if record.schwarz:
            schwarz += 1
        if record.auction_winner is not None:
            auction_games += 1
            if record.auction_winner == name:
                auction_wins += 1
                assert record.auction_bid is not None
                winning_bids.append(float(record.auction_bid))
                if record.avg_raise is not None:
                    raises.append(record.avg_raise)
        if record.playing_team is not None and record.game_value is not None:
            if record.playing_team == name:
                contracts_played += 1
                bucket = buckets.setdefault(_bucket(record.game_value), BucketStats())
                bucket.played += 1
                if record.won:
                    contracts_made += 1
                    bucket.made += 1
            else:
                defending += 1
                conceded.append(float(other))
                if not record.won:
                    sets_as_defender += 1

    return AgentStats(
        name=name,
        games=games,
        wins=wins,
        draws=draws,
        losses=losses,
        forfeits=forfeits,
        score=(wins + 0.5 * draws) / games if games else 0.0,
        avg_points=_mean(points),
        avg_point_diff=_mean(diffs),
        avg_call_points=_mean(call_points),
        avg_tricks=_mean(tricks),
        auction_wins=auction_wins,
        auction_win_rate=auction_wins / auction_games if auction_games else None,
        avg_winning_bid=_mean(winning_bids),
        avg_raise=_mean(raises),
        contracts_played=contracts_played,
        contracts_made=contracts_made,
        contract_success_rate=(
            contracts_made / contracts_played if contracts_played else None
        ),
        contracts_by_bucket=dict(sorted(buckets.items())),
        games_defending=defending,
        sets_as_defender=sets_as_defender,
        set_rate_as_defender=sets_as_defender / defending if defending else None,
        avg_points_conceded=_mean(conceded),
        no_one_played_rate=no_one_played / finished if finished else None,
        schwarz_rate=schwarz / finished if finished else None,
        mean_decision_seconds=decision_seconds / decisions if decisions else None,
        mean_game_seconds=_mean(game_seconds),
        errors=errors,
    )


def run_arena(
    deals: int = 50,
    seed: int = 0,
    *,
    registry: list[tuple[str, str, str]] | None = None,
    include_slow: bool = False,
    slow_deals: int = 10,
    only: list[str] | None = None,
    output_dir: Path | None = None,
    verbose: bool = False,
) -> ArenaResults:
    factories, skipped = discover_contestants(
        REGISTRY if registry is None else registry
    )
    factories = {BASELINE_NAME: RandomAgent, **factories}
    if only is not None:
        unknown = [name for name in only if name not in factories]
        if unknown:
            msg = f"Unknown contestants {unknown}; available: {sorted(factories)}"
            raise ValueError(msg)
        factories = {name: factories[name] for name in only}
    elif not include_slow:
        factories = {
            name: factory
            for name, factory in factories.items()
            if name not in SLOW_CONTESTANTS
        }

    names = list(factories)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
    if not pairs:
        pairs = [(names[0], names[0])]

    deal_seeds = [seed + i for i in range(deals)]
    deal_cache = {s: _make_deal(s) for s in deal_seeds}

    records: list[GameRecord] = []
    matchups: list[MatchupStats] = []
    for team_a, team_b in pairs:
        slow = team_a in SLOW_CONTESTANTS or team_b in SLOW_CONTESTANTS
        pair_seeds = deal_seeds[: min(slow_deals, deals)] if slow else deal_seeds
        if verbose:
            print(f"[arena] {team_a} vs {team_b}: {len(pair_seeds)} deals x 2")
        pair_records = [
            _play_one(
                team_a,
                factories[team_a],
                team_b,
                factories[team_b],
                deal_seed,
                deal_cache[deal_seed],
                orientation,
            )
            for deal_seed in pair_seeds
            for orientation in (0, 1)
        ]
        records.extend(pair_records)
        matchups.append(_matchup_stats(team_a, team_b, pair_records))

    agents = [_agent_stats(name, records) for name in names]
    ranking = sorted(
        agents, key=lambda s: (s.score, s.avg_point_diff or 0.0), reverse=True
    )
    results = ArenaResults(
        config=ArenaConfig(
            deals=deals,
            seed=seed,
            include_slow=include_slow,
            slow_deals=slow_deals,
            only=only,
        ),
        contestants=names,
        skipped=skipped,
        records=records,
        matchups=matchups,
        agents=agents,
        ranking=[s.name for s in ranking],
    )
    if output_dir is not None:
        write_results(results, output_dir)
    return results


def _fmt(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _fmt_ms(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds * 1000.0:.3f}"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render_report(results: ArenaResults) -> str:
    stats_by_name = {s.name: s for s in results.agents}
    score_by_pair: dict[tuple[str, str], float] = {}
    for m in results.matchups:
        score_by_pair[(m.team_a, m.team_b)] = m.score_a
        score_by_pair[(m.team_b, m.team_a)] = 1.0 - m.score_a

    sections = [
        "# Arena Report",
        f"Config: {results.config.model_dump()}",
        "## Win semantics",
        "A game is won by the bidding party if its trick points reach the contract"
        " (`GameFinishedInfo.won`), otherwise by the defenders. Games where nobody"
        " bid above 115 (`no_one_played`, `won is None`) count as a draw (0.5"
        " points for each team). A game aborted by an agent exception or illegal"
        " action is a forfeit loss for that agent's team.",
        "## Contestants",
        ", ".join(results.contestants),
    ]
    if results.skipped:
        sections.append("## Skipped registry entries")
        sections.append(
            _table(
                ["name", "import path", "class", "reason"],
                [
                    [e.name, e.import_path, e.class_name, e.reason]
                    for e in results.skipped
                ],
            )
        )

    sections.append("## Ranking")
    sections.append(
        _table(
            [
                "rank",
                "agent",
                "score",
                "W/D/L",
                "forfeits",
                "avg point diff",
                "avg points",
                "avg tricks",
                "mean ms/decision",
            ],
            [
                [
                    str(i + 1),
                    name,
                    _fmt(s.score, 3),
                    f"{s.wins}/{s.draws}/{s.losses}",
                    str(s.forfeits),
                    _fmt(s.avg_point_diff, 1),
                    _fmt(s.avg_points, 1),
                    _fmt(s.avg_tricks, 2),
                    _fmt_ms(s.mean_decision_seconds),
                ]
                for i, name in enumerate(results.ranking)
                for s in [stats_by_name[name]]
            ],
        )
    )

    sections.append("## Head-to-head score matrix (row vs column)")
    sections.append(
        _table(
            ["", *results.ranking],
            [
                [
                    row,
                    *[
                        _fmt(score_by_pair.get((row, col)), 3)
                        for col in results.ranking
                    ],
                ]
                for row in results.ranking
            ],
        )
    )

    sections.append("## Matchups")
    sections.append(
        _table(
            ["team a", "team b", "games", "a wins", "b wins", "draws", "avg diff a"],
            [
                [
                    m.team_a,
                    m.team_b,
                    str(m.games),
                    str(m.wins_a),
                    str(m.wins_b),
                    str(m.draws),
                    _fmt(m.avg_point_diff_a, 1),
                ]
                for m in results.matchups
            ],
        )
    )

    sections.append("## Auction")
    sections.append(
        _table(
            [
                "agent",
                "auction win rate",
                "avg winning bid",
                "avg raise",
                "avg call points",
            ],
            [
                [
                    s.name,
                    _fmt(s.auction_win_rate, 3),
                    _fmt(s.avg_winning_bid, 1),
                    _fmt(s.avg_raise, 1),
                    _fmt(s.avg_call_points, 1),
                ]
                for s in results.agents
            ],
        )
    )

    buckets = sorted({b for s in results.agents for b in s.contracts_by_bucket})
    sections.append("## Contracts (made/played per bid bucket)")
    sections.append(
        _table(
            ["agent", "played", "made", "success rate", *buckets],
            [
                [
                    s.name,
                    str(s.contracts_played),
                    str(s.contracts_made),
                    _fmt(s.contract_success_rate, 3),
                    *[
                        (
                            f"{stat.made}/{stat.played}"
                            if (stat := s.contracts_by_bucket.get(bucket)) is not None
                            else "-"
                        )
                        for bucket in buckets
                    ],
                ]
                for s in results.agents
            ],
        )
    )

    sections.append("## Defense and game character")
    sections.append(
        _table(
            [
                "agent",
                "games defending",
                "set rate as defender",
                "avg points conceded",
                "no-one-played rate",
                "schwarz rate",
            ],
            [
                [
                    s.name,
                    str(s.games_defending),
                    _fmt(s.set_rate_as_defender, 3),
                    _fmt(s.avg_points_conceded, 1),
                    _fmt(s.no_one_played_rate, 3),
                    _fmt(s.schwarz_rate, 3),
                ]
                for s in results.agents
            ],
        )
    )

    sections.append("## Timing")
    sections.append(
        _table(
            ["agent", "mean s/game", "mean ms/decision"],
            [
                [s.name, _fmt(s.mean_game_seconds, 4), _fmt_ms(s.mean_decision_seconds)]
                for s in results.agents
            ],
        )
    )

    error_rows = [[s.name, error] for s in results.agents for error in s.errors]
    if error_rows:
        sections.append("## Errors")
        sections.append(_table(["agent", "error"], error_rows))

    return "\n\n".join(sections) + "\n"


def write_results(results: ArenaResults, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(results.model_dump_json(indent=2))
    (output_dir / "report.md").write_text(render_report(results))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m marjapussi.agentic.arena")
    parser.add_argument("--deals", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--include-slow", action="store_true")
    parser.add_argument("--slow-deals", type=int, default=10)
    parser.add_argument("--only", nargs="+", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.out
    if output_dir is None:
        output_dir = Path(__file__).resolve().parents[2] / "arena_results"
    results = run_arena(
        deals=args.deals,
        seed=args.seed,
        include_slow=args.include_slow,
        slow_deals=args.slow_deals,
        only=args.only,
        output_dir=output_dir,
        verbose=True,
    )
    for entry in results.skipped:
        print(f"[arena] skipped {entry.name}: {entry.reason}")
    print(f"[arena] contestants: {', '.join(results.contestants)}")
    print(f"[arena] games played: {len(results.records)}")
    for rank, name in enumerate(results.ranking, start=1):
        stats = next(s for s in results.agents if s.name == name)
        print(
            f"[arena] {rank}. {name} score={stats.score:.3f}"
            f" W/D/L={stats.wins}/{stats.draws}/{stats.losses}"
            f" forfeits={stats.forfeits}"
        )
    print(f"[arena] results written to {output_dir}")


if __name__ == "__main__":
    main()
