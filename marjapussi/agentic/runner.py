from __future__ import annotations

from marjapussi.agentic.agent import Agent
from marjapussi.events import GameAction
from marjapussi.game import MarjapussiGame
from marjapussi.state import GameFinishedInfo
from marjapussi.types import PlaceAtTable


def play_game(
    agents: tuple[Agent, Agent, Agent, Agent],
    game: MarjapussiGame | None = None,
) -> GameFinishedInfo:
    """Play a full game with one agent per seat and return the finished info."""
    if game is None:
        game = MarjapussiGame(player_names=("Agent0", "Agent1", "Agent2", "Agent3"))
    for seat, agent in enumerate(agents):
        agent.place = PlaceAtTable(root=seat)

    for agent, view in zip(agents, game.to_player_views(), strict=True):
        agent.observe(view)
    while not game.finished:
        game.apply_action(_next_action(agents, game))
        for agent, view in zip(agents, game.to_player_views(), strict=True):
            agent.observe(view)
    return game.to_finished_info()


def _next_action(
    agents: tuple[Agent, Agent, Agent, Agent],
    game: MarjapussiGame,
) -> GameAction:
    seat = game.legal_actions()[0].player
    view = game.to_player_views()[seat.root]
    action = agents[seat.root].select_action(view)
    if action not in view.legal_actions:
        msg = f"Agent at seat {seat.root} returned illegal action {action}"
        raise ValueError(msg)
    return action.model_copy(deep=True)
