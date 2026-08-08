from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from datetime import datetime
from itertools import combinations

from marjapussi.actions import (
    ActionAnnounceTrump,
    ActionAnswer,
    ActionCardPlayed,
    ActionNewBid,
    ActionPass,
    ActionQuestion,
    ActionType,
    AnswerNoHalf,
    AnswerYesHalf,
    AnswerYesPair,
    QuestionYourHalf,
)
from marjapussi.events import (
    CallbackNewTrump,
    CallbackNoHalf,
    CallbackOnlyHalf,
    CallbackStillTrump,
    GameAction,
    GameCallback,
    GameEvent,
    GameEventPlayer,
)
from marjapussi.player import PlayerState
from marjapussi.rules import (
    allowed_cards,
    contains_half,
    contains_pair,
    deck,
    sorted_cards,
    trick_points,
    trick_winner,
)
from marjapussi.state import (
    FinishedTrick,
    GameFinishedInfo,
    GameInfoPlayer,
    GameMetaInfo,
    GamePhaseAnsweringHalf,
)
from marjapussi.types import Card, PlaceAtTable, Points, Suit


def _default_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MarjapussiGame:
    START_VALUE = 115
    MAX_VALUE = 420
    TOTAL_TRICKS = 9

    def __init__(
        self,
        player_names: tuple[str, str, str, str],
        start_cards: tuple[list[Card], list[Card], list[Card], list[Card]]
        | None = None,
        *,
        name: str = "",
        time_fn: Callable[[], str] = _default_time,
    ) -> None:
        if start_cards is None:
            cards = deck()
            random.shuffle(cards)
            start_cards = tuple(
                sorted_cards(cards[i * 9 : (i + 1) * 9]) for i in range(4)
            )
        self._time_fn = time_fn
        now = time_fn()
        self._meta = GameMetaInfo(
            name=name,
            create_time=now,
            player_names=player_names,
            player_start_cards=tuple(list(c) for c in start_cards),
        )
        self._actions: list[GameAction] = []
        self._events: list[GameEvent] = []

        self._players: list[PlayerState] = [
            PlayerState(
                place=PlaceAtTable(root=i),
                name=n,
                hand=sorted_cards(list(cards)),
            )
            for i, (n, cards) in enumerate(zip(player_names, start_cards, strict=True))
        ]
        self._phase: str | GamePhaseAnsweringHalf = "WaitingForStart"
        self._player_at_turn = PlaceAtTable(root=0)
        self._players_started: set[int] = set()
        self._game_value: int = self.START_VALUE
        self._trump: Suit | None = None
        self._trump_called: list[Suit] = []
        self._playing_player: PlaceAtTable | None = None
        self._no_one_played: bool = True
        self._passed_forth: list[Card] = []
        self._passed_back: list[Card] = []
        self._after_passing: (
            tuple[list[Card], list[Card], list[Card], list[Card]] | None
        ) = None
        self._bidding_history: list[tuple[ActionType, PlaceAtTable]] = []
        self._current_trick: list[Card] = []
        self._trick_lead = PlaceAtTable(root=0)
        self._all_tricks: list[FinishedTrick] = []
        self._first_trick_done: bool = False

    @property
    def actions(self) -> tuple[GameAction, ...]:
        return tuple(self._actions)

    @property
    def phase(self) -> str | GamePhaseAnsweringHalf:
        return self._phase

    @property
    def finished(self) -> bool:
        return self._phase == "Ended"

    def legal_actions(self) -> list[GameAction]:
        phase = self._phase
        if phase == "WaitingForStart":
            return self._legal_waiting()
        if phase == "Bidding":
            return self._legal_bidding()
        if phase == "PassingForth":
            return self._legal_passing_forth()
        if phase == "PassingBack":
            return self._legal_passing_back()
        if phase == "Raising":
            return self._legal_raising()
        if phase == "StartTrick":
            return self._legal_start_trick()
        if phase == "Trick":
            return self._legal_trick()
        if phase == "AnsweringPair":
            return self._legal_answering_pair()
        if isinstance(phase, GamePhaseAnsweringHalf):
            return self._legal_answering_half()
        return []

    def to_player_views(
        self,
    ) -> tuple[GameInfoPlayer, GameInfoPlayer, GameInfoPlayer, GameInfoPlayer]:
        legal_actions = self.legal_actions()
        latest_event = self._events[-1] if self._events else None
        players_pressed_start = [
            self._players[seat].name for seat in sorted(self._players_started)
        ]
        last_trick = self._all_tricks[-1] if self._all_tricks else None
        player_at_turn_name = self._players[self._player_at_turn.root].name

        def _last_event_for(seat: PlaceAtTable) -> GameEventPlayer | None:
            if latest_event is None:
                return None
            action_type = latest_event.last_action.action_type
            if isinstance(action_type, ActionPass):
                actor = latest_event.last_action.player
                if seat != actor and seat != actor.partner():
                    return "HiddenEvent"
            return latest_event

        def _view_for(seat: PlaceAtTable) -> GameInfoPlayer:
            perspective = (seat, seat.next(), seat.partner(), seat.prev())
            meta = self._meta.model_copy(
                update={
                    "player_start_cards": tuple(
                        list(cards) if i == seat.root else []
                        for i, cards in enumerate(self._meta.player_start_cards)
                    )
                }
            )
            return GameInfoPlayer(
                meta_info=meta,
                players_pressed_start=players_pressed_start,
                players_from_perspective=tuple(
                    self._players[p.root].name for p in perspective
                ),
                player_at_turn=player_at_turn_name,
                own_cards=list(self._players[seat.root].hand),
                players_cards_number_perspective=tuple(
                    len(self._players[p.root].hand) for p in perspective
                ),
                game_phase=self._phase,
                bidding_history=list(self._bidding_history),
                current_trick=list(self._current_trick),
                last_trick=last_trick,
                last_event=_last_event_for(seat),
                legal_actions=[
                    action for action in legal_actions if action.player == seat
                ],
            ).model_copy(deep=True)

        return (
            _view_for(PlaceAtTable(root=0)),
            _view_for(PlaceAtTable(root=1)),
            _view_for(PlaceAtTable(root=2)),
            _view_for(PlaceAtTable(root=3)),
        )

    def apply_action(self, action: GameAction) -> None:
        if action not in self.legal_actions():
            msg = f"Illegal action {action} in phase {self._phase}"
            raise ValueError(msg)
        self._actions.append(action)
        callback = self._apply_to_state(action)
        self._events.append(
            GameEvent(
                last_action=action,
                callback=callback,
                player_at_turn=self._player_at_turn,
                time=self._time_fn(),
            )
        )

    @staticmethod
    def replay(
        meta: GameMetaInfo,
        actions: Sequence[GameAction],
        *,
        time_fn: Callable[[], str] = _default_time,
    ) -> MarjapussiGame:
        """Reconstruct a game by re-applying a sequence of actions."""
        game = MarjapussiGame(
            player_names=meta.player_names,
            start_cards=meta.player_start_cards,
            name=meta.name,
            time_fn=time_fn,
        )
        game._meta.create_time = meta.create_time
        for action in actions:
            game.apply_action(action)
        return game

    def to_finished_info(self) -> GameFinishedInfo:
        """Build a summary with scores, tricks, and outcome of the completed game."""
        if not self.finished:
            raise ValueError("Game has not ended")

        won = None
        playing_party = None
        if self._playing_player is not None:
            playing_party = self._playing_player.party()
            seat = self._playing_player.root
            partner = (seat + 2) % 4
            total = self._players[seat].points + self._players[partner].points
            won = total >= self._game_value

        p0 = len(self._players[0].tricks_won)
        p2 = len(self._players[2].tricks_won)
        p1 = len(self._players[1].tricks_won)
        p3 = len(self._players[3].tricks_won)
        schwarz = p0 + p2 == self.TOTAL_TRICKS or p1 + p3 == self.TOTAL_TRICKS

        passed_cards = None
        if self._passed_forth:
            passed_cards = (self._passed_forth, self._passed_back)

        return GameFinishedInfo(
            info=self._meta,
            game_value=Points(root=self._game_value),
            won=won,
            no_one_played=self._no_one_played,
            schwarz_game=schwarz,
            playing_party=playing_party,
            after_passing=self._after_passing,
            passed_cards=passed_cards,
            bidding_history=list(self._bidding_history),
            tricks=list(self._all_tricks),
            all_events=list(self._events),
        )

    def _apply_to_state(self, action: GameAction) -> GameCallback | None:
        """Dispatch an action to the matching handler and return any callback."""
        at = action.action_type
        if at == "Start":
            return self._apply_start(action.player)
        if isinstance(at, ActionNewBid):
            return self._apply_new_bid(action.player, at.NewBid)
        if at == "StopBidding":
            return self._apply_stop_bidding(action.player)
        if isinstance(at, ActionPass):
            return self._apply_pass(action.player, at.Pass)
        if isinstance(at, ActionCardPlayed):
            return self._apply_card_played(action.player, at.CardPlayed)
        if isinstance(at, ActionAnnounceTrump):
            return self._apply_announce_trump(action.player, at.AnnounceTrump)
        if isinstance(at, ActionQuestion):
            return self._apply_question(action.player, at.Question)
        if isinstance(at, ActionAnswer):
            return self._apply_answer(action.player, at.Answer)
        msg = f"Unhandled action type: {at}"
        raise ValueError(msg)

    def _apply_start(self, player: PlaceAtTable) -> GameCallback | None:
        self._players_started.add(player.root)
        if len(self._players_started) == 4:
            self._meta.start_time = self._time_fn()
            self._phase = "Bidding"
        return None

    def _apply_new_bid(self, player: PlaceAtTable, value: int) -> GameCallback | None:
        if self._phase == "Bidding":
            self._game_value = value
            self._bidding_history.append((ActionNewBid(NewBid=value), player))
            self._advance_bidding()
        elif self._phase == "Raising":
            self._game_value = value
            self._phase = "Trick"
            self._trick_lead = self._player_at_turn
        return None

    def _apply_stop_bidding(self, player: PlaceAtTable) -> GameCallback | None:
        if self._phase == "Bidding":
            self._players[player.root].still_bidding = False
            self._bidding_history.append(("StopBidding", player))
            self._advance_bidding()
        elif self._phase == "Raising":
            self._phase = "Trick"
            self._trick_lead = self._player_at_turn
        return None

    def _apply_pass(
        self, player: PlaceAtTable, cards: list[Card]
    ) -> GameCallback | None:
        if self._phase == "PassingForth":
            partner = self._players[player.root]
            playing = self._players[self._playing_player.root]
            for card in cards:
                partner.remove_card(card)
                playing.give_card(card)
            self._passed_forth = list(cards)
            self._player_at_turn = self._playing_player
            self._phase = "PassingBack"
        elif self._phase == "PassingBack":
            playing = self._players[player.root]
            partner_seat = self._playing_player.partner()
            partner = self._players[partner_seat.root]
            for card in cards:
                playing.remove_card(card)
                partner.give_card(card)
            self._passed_back = list(cards)
            self._after_passing = (
                list(self._players[0].hand),
                list(self._players[1].hand),
                list(self._players[2].hand),
                list(self._players[3].hand),
            )
            self._player_at_turn = self._playing_player
            self._phase = "Raising"
        return None

    def _apply_card_played(
        self, player: PlaceAtTable, card: Card
    ) -> GameCallback | None:
        self._players[player.root].remove_card(card)
        self._current_trick.append(card)

        if len(self._current_trick) == 1:
            self._trick_lead = player

        if len(self._current_trick) == 4:
            is_last = len(self._all_tricks) + 1 == self.TOTAL_TRICKS
            winner = trick_winner(self._current_trick, self._trump, self._trick_lead)
            pts = trick_points(self._current_trick, last=is_last)
            finished = FinishedTrick(
                cards=(
                    self._current_trick[0],
                    self._current_trick[1],
                    self._current_trick[2],
                    self._current_trick[3],
                ),
                winner=winner,
                points=Points(root=pts),
            )
            self._all_tricks.append(finished)
            self._players[winner.root].take_trick(
                list(self._current_trick), last=is_last
            )
            self._current_trick = []
            self._player_at_turn = winner
            self._first_trick_done = True

            if is_last:
                self._phase = "Ended"
                self._meta.end_time = self._time_fn()
            else:
                self._phase = "StartTrick"
        else:
            self._player_at_turn = player.next()
            self._phase = "Trick"
        return None

    def _apply_announce_trump(
        self, player: PlaceAtTable, suit: Suit
    ) -> GameCallback | None:
        old_trump = self._trump
        self._trump = suit
        self._trump_called.append(suit)
        self._players[player.root].call_trump(suit)
        self._phase = "Trick"
        if old_trump == suit:
            return CallbackStillTrump(StillTrump=suit)
        return CallbackNewTrump(NewTrump=suit)

    def _apply_question(
        self,
        player: PlaceAtTable,
        question: str | QuestionYourHalf,
    ) -> GameCallback | None:
        p = self._players[player.root]
        if question == "Yours":
            p.asking_level = max(p.asking_level, 1)
            self._player_at_turn = player.partner()
            self._phase = "AnsweringPair"
        elif isinstance(question, QuestionYourHalf):
            p.asking_level = max(p.asking_level, 2)
            self._player_at_turn = player.partner()
            self._phase = GamePhaseAnsweringHalf(AnsweringHalf=question.YourHalf)
        return None

    def _apply_answer(
        self,
        player: PlaceAtTable,
        answer: str | AnswerYesPair | AnswerYesHalf | AnswerNoHalf,
    ) -> GameCallback | None:
        asker = player.partner()
        callback: GameCallback | None = None

        if answer == "NoPair":
            pass
        elif isinstance(answer, AnswerYesPair):
            suit = answer.YesPair
            old_trump = self._trump
            self._trump = suit
            self._trump_called.append(suit)
            self._players[player.root].call_trump(suit)
            callback = (
                CallbackStillTrump(StillTrump=suit)
                if old_trump == suit
                else CallbackNewTrump(NewTrump=suit)
            )
        elif isinstance(answer, AnswerYesHalf):
            suit = answer.YesHalf
            if contains_half(self._players[asker.root].hand, suit):
                old_trump = self._trump
                self._trump = suit
                self._trump_called.append(suit)
                self._players[player.root].call_trump(suit)
                callback = (
                    CallbackStillTrump(StillTrump=suit)
                    if old_trump == suit
                    else CallbackNewTrump(NewTrump=suit)
                )
            else:
                callback = CallbackOnlyHalf(OnlyHalf=suit)
        elif isinstance(answer, AnswerNoHalf):
            callback = CallbackNoHalf(NoHalf=answer.NoHalf)

        self._player_at_turn = asker
        self._phase = "Trick"
        return callback

    def _advance_bidding(self) -> None:
        """Move turn to the next active bidder or resolve the bidding phase."""
        still = [p for p in self._players if p.still_bidding]
        n = len(still)
        if n > 1 or (n == 1 and self._game_value == self.START_VALUE):
            seat = self._player_at_turn.root
            for _ in range(4):
                seat = (seat + 1) % 4
                if self._players[seat].still_bidding:
                    self._player_at_turn = PlaceAtTable(root=seat)
                    return
        if self._game_value == self.START_VALUE:
            self._player_at_turn = PlaceAtTable(root=0)
            self._no_one_played = True
            self._phase = "Trick"
            self._trick_lead = self._player_at_turn
        else:
            winner = still[0]
            self._playing_player = winner.place
            self._no_one_played = False
            self._player_at_turn = winner.place.partner()
            self._phase = "PassingForth"

    def _legal_waiting(self) -> list[GameAction]:
        return [
            GameAction(
                action_type="Start",
                player=PlaceAtTable(root=i),
            )
            for i in range(4)
            if i not in self._players_started
        ]

    def _legal_bidding(self) -> list[GameAction]:
        seat = self._player_at_turn
        actions: list[GameAction] = [GameAction(action_type="StopBidding", player=seat)]
        for v in range(self._game_value + 5, self.MAX_VALUE + 1, 5):
            actions.append(
                GameAction(
                    action_type=ActionNewBid(NewBid=v),
                    player=seat,
                )
            )
        return actions

    def _legal_passing_forth(self) -> list[GameAction]:
        partner = self._playing_player.partner()
        hand = self._players[partner.root].hand
        return [
            GameAction(
                action_type=ActionPass(Pass=list(combo)),
                player=partner,
            )
            for combo in combinations(hand, 4)
        ]

    def _legal_passing_back(self) -> list[GameAction]:
        seat = self._playing_player
        hand = self._players[seat.root].hand
        return [
            GameAction(
                action_type=ActionPass(Pass=list(combo)),
                player=seat,
            )
            for combo in combinations(hand, 4)
        ]

    def _legal_raising(self) -> list[GameAction]:
        seat = self._player_at_turn
        actions: list[GameAction] = [GameAction(action_type="StopBidding", player=seat)]
        for v in range(self._game_value + 5, self.MAX_VALUE + 1, 5):
            actions.append(
                GameAction(
                    action_type=ActionNewBid(NewBid=v),
                    player=seat,
                )
            )
        return actions

    def _legal_start_trick(self) -> list[GameAction]:
        seat = self._player_at_turn
        p = self._players[seat.root]
        actions: list[GameAction] = []

        if p.asking_level == 0:
            for suit in Suit:
                if contains_pair(p.hand, suit) and suit not in self._trump_called:
                    actions.append(
                        GameAction(
                            action_type=ActionAnnounceTrump(AnnounceTrump=suit),
                            player=seat,
                        )
                    )

        if p.asking_level <= 1:
            actions.append(
                GameAction(
                    action_type=ActionQuestion(Question="Yours"),
                    player=seat,
                )
            )

        if p.asking_level <= 2:
            for suit in Suit:
                actions.append(
                    GameAction(
                        action_type=ActionQuestion(
                            Question=QuestionYourHalf(YourHalf=suit)
                        ),
                        player=seat,
                    )
                )

        actions.extend(self._card_play_actions(seat))
        return actions

    def _legal_trick(self) -> list[GameAction]:
        return self._card_play_actions(self._player_at_turn)

    def _legal_answering_pair(self) -> list[GameAction]:
        seat = self._player_at_turn
        p = self._players[seat.root]
        pairs = [
            GameAction(
                action_type=ActionAnswer(Answer=AnswerYesPair(YesPair=suit)),
                player=seat,
            )
            for suit in Suit
            if contains_pair(p.hand, suit) and suit not in self._trump_called
        ]
        if pairs:
            return pairs
        return [
            GameAction(
                action_type=ActionAnswer(Answer="NoPair"),
                player=seat,
            )
        ]

    def _legal_answering_half(self) -> list[GameAction]:
        seat = self._player_at_turn
        p = self._players[seat.root]
        phase = self._phase
        assert isinstance(phase, GamePhaseAnsweringHalf)
        suit = phase.AnsweringHalf

        if contains_half(p.hand, suit):
            return [
                GameAction(
                    action_type=ActionAnswer(Answer=AnswerYesHalf(YesHalf=suit)),
                    player=seat,
                )
            ]
        return [
            GameAction(
                action_type=ActionAnswer(Answer=AnswerNoHalf(NoHalf=suit)),
                player=seat,
            )
        ]

    def _card_play_actions(self, seat: PlaceAtTable) -> list[GameAction]:
        hand = self._players[seat.root].hand
        playable = allowed_cards(
            self._current_trick,
            hand,
            self._trump,
            first_trick=not self._first_trick_done,
        )
        return [
            GameAction(
                action_type=ActionCardPlayed(CardPlayed=card),
                player=seat,
            )
            for card in playable
        ]
