from random import shuffle
import marjapussi.utils as utils
from marjapussi.player import Player

import logging
logging.basicConfig(format='%(levelname)s: %(message)s')


class MarjaPussi():
    """Implements a single game of MarjaPussi."""
    
    DEFAULT_RULES = {
        "start_game_value": 115,
        "max_game_value": 420,
        "points": {symb: val for symb, val in zip("rsegAZKOU9876L", [100, 80, 60, 40, 11, 10, 4, 3, 2, 0, 0, 0, 0, 20])},
        "start_phase": "PROV",
    }

    def __init__(self, player_names, ruleset={}, log=False, fancy=True) -> None:
        # init logger
        self.logger = logging.getLogger("single_game_logger")
        if log:
            self.logger.setLevel(logging.INFO)
        if log == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        self.fancy = fancy
        # init rules
        self.rules = MarjaPussi.DEFAULT_RULES | ruleset
        self.logger.debug(f"Ruleset: {ruleset}")
        # init players and cards
        deck = utils.CARDS[:]
        shuffle(deck)
        self.players = [Player(name, num, self.rules["points"])
                        for num, name in enumerate(player_names)]
        # only used for logging
        self.players_dict = {player.number: player for player in self.players}
        while deck:
            for p in self.players:
                p.give_card(deck.pop())
        for player in self.players:
            self.logger.debug(
                f"{player.name}: {utils.cards_str(player.cards, fancy=self.fancy)}")
        self.logger.info(MarjaPussi.DEFAULT_MSG["got_their_cards"])

        for i in range(4):
            self.players[i].set_partner(self.players[(i+2) % 4])
            self.players[i].set_next_player(self.players[(i+1) % 4])

        self.player_at_turn = self.players[0]
        self.playing_player = None
        self.game_value = self.rules["start_game_value"]
        self.noone_plays = True
        self.game_phase = self.rules["start_phase"]
        self.passed_cards = {"forth": [], "back": []}
        self.all_actions = []
        self.sup_col = ""
        self.tricks = [[]]

    def legal_actions(self) -> list:
        """
        PROV, PASS, PBCK, PRMO, FTRI, QUES, ANSW, TRCK, DONE
        game phase -> 0-reizen/ 1-schieben/ 2-zurückschieben/ 3-erhöhen/ 4-erster Sitch/ 5-Frage/ 6-Antwort/ 7-Stich
        action -> 'p'<player number>','<phase>','<val | card>
        """
        match self.game_phase:
            case "PROV":
                return self.legal_prov()
            case "PASS":
                return self.legal_pass()
            case "PBCK":
                return self.legal_passing_back()
            case "PRMO":
                return self.legal_prmo()
            case "QUES":
                return self.legal_ques()
            case "ANSW":
                return self.legal_answer()
            case "TRCK":
                return self.legal_trck()
            case "DONE":
                return []
            case _:
                self.logger.critical("Game is in an illegal game phase!")
                return []

    def act_action(self, action):
        """Phases: PROV, PASS, PBCK, PRMO, FTRI, QUES, ANSW, TRCK"""
        # ? there is not a real reason why they are 4 letters long but it looks neat
        if not action in self.legal_actions():
            self.logger.warning(
                "Not a legal action! This is not supposed to happen!")
            return False
            #logging.warning("Proceeding anyway for debugging purposes...")

        self.all_actions.append(action)

        action_list = action.split(',')
        action_list[0] = int(action_list[0])

        self.logger.debug(
            f"{self.player_at_turn.name}: {utils.cards_str(self.player_at_turn.cards, fancy=self.fancy)}")
        self.logger.debug(
            f"Action player={self.players_dict[action_list[0]].name}, phase={action_list[1]}, content={action_list[2]}")

        match action_list:
            case [player, "PROV", value]:
                self.act_prov(player, int(value))
            case [player, "PASS", card]:
                self.act_pass(player, card)
            case [player, "PBCK", card]:
                self.act_pbck(player, card)
            case [player, "PRMO", value]:
                self.act_prmo(player, int(value))
            case [player, "TRCK", card]:
                self.act_trck(player, card)
            case [player, "QUES", quest]:
                self.act_ques(player, quest)
            case [player, "ANSW", answ]:
                self.act_answ(player, answ)
            case _:
                self.logger.critical(
                    f"The action seems to be legal but can not be executed.")
        return True

    def legal_prov(self):
        actions = [f"{self.player_at_turn.number},PROV,{000}"]
        for poss_val in range(self.game_value+5, self.rules["max_game_value"]+1, 5):
            actions.append(f"{self.player_at_turn.number},PROV,{poss_val}")
        return actions

    def act_prov(self, player, value):
        if value > self.game_value:
            self.game_value = value
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['player_says']} {value}.")
        else:
            self.player_at_turn.still_prov = False
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['is_gone']}")
        players_still_prov = sum(
            [1 for p in self.players if p.still_prov])
        # more than one player or last player still able to provoke
        if players_still_prov > 1 or (players_still_prov == 1 and self.game_value == self.rules["start_game_value"]):
            self.player_at_turn = self.player_at_turn.next_player
            while not self.player_at_turn.still_prov:
                self.player_at_turn = self.player_at_turn.next_player
        else:
            if self.game_value == self.rules["start_game_value"]:
                # noone took the game
                self.player_at_turn = self.players[0]
                self.logger.info(
                    f"{MarjaPussi.DEFAULT_MSG['noon_plays']} {self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['plays']}")
                self.game_phase = "TRCK"
            else:
                # last prov player takes the game
                self.noone_plays = False
                self.player_at_turn = [
                    p for p in self.players if p.still_prov][0]
                self.playing_player = self.player_at_turn
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['takes_the_game']} {self.game_value}.")
                self.game_phase = "PASS"

    def legal_pass(self):
        actions = []
        for card in self.playing_player.cards:
            if card in self.passed_cards["forth"]:
                continue
            actions.append(f"{self.playing_player.number},PASS,{card}")
        return actions

    def act_pass(self, player, card):
        if len(self.passed_cards["forth"]) < 4:
            self.passed_cards["forth"].append(card)
        if len(self.passed_cards["forth"]) == 4:
            self.logger.debug(
                f"{player} gives {utils.cards_str(self.passed_cards['forth'], fancy=self.fancy)}.")
            for c in self.passed_cards["forth"]:
                self.playing_player.take_card(c)
                self.playing_player.partner.give_card(c)
            self.player_at_turn = self.player_at_turn.partner
            self.game_phase = "PBCK"

    def legal_passing_back(self):
        actions = []
        for card in self.playing_player.partner.cards:
            if card in self.passed_cards["back"]:
                continue
            actions.append(f"{self.playing_player.partner.number},PBCK,{card}")
        return actions

    def act_pbck(self, player, card):
        if len(self.passed_cards["back"]) < 4:
            self.passed_cards["back"].append(card)
        if len(self.passed_cards["back"]) == 4:
            self.logger.debug(
                f"{player} gives {utils.cards_str(self.passed_cards['back'], fancy=self.fancy)}.")
            for c in self.passed_cards["back"]:
                self.player_at_turn.take_card(c)
                self.playing_player.give_card(c)
            self.player_at_turn = self.playing_player
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['and']} {self.player_at_turn.partner.name} {MarjaPussi.DEFAULT_MSG['passed_cards']}")
            self.game_phase = "PRMO"

    def legal_prmo(self):
        actions = [f"{self.player_at_turn.number},PRMO,{000}"]
        for poss_val in range(self.game_value+5, self.rules["max_game_value"], 5):
            actions.append(f"{self.player_at_turn.number},PRMO,{poss_val}")
        return actions

    def act_prmo(self, player, value):
        if value > self.game_value:
            self.game_value = value
            self.logger.info(
                f"{self.playing_player.name} {MarjaPussi.DEFAULT_MSG['raises_to']} {value}.")
        else:
            self.logger.info(
                f"{self.playing_player.name} {MarjaPussi.DEFAULT_MSG['plays_for']} {self.game_value}.")
        self.game_phase = "TRCK"

    def legal_trck(self):
        return [f"{self.player_at_turn.number},TRCK,{c}" for c in
                utils.allowed_general(self.tricks[-1], self.player_at_turn.cards,
                                      sup_col=self.sup_col, first=(len(self.tricks[0]) != 4))]

    def act_trck(self, player, card):
        self.logger.info(
            f"{self.players_dict[player].name} {MarjaPussi.DEFAULT_MSG['plays']} {utils.card_str(card, fancy=self.fancy)}.")
        self.player_at_turn.take_card(card)
        # first not over
        self.tricks[-1].append(card)
        self.player_at_turn = self.player_at_turn.next_player
        # trick over
        if len(self.tricks[-1]) == 4:
            for c in self.tricks[-1]:
                if c == utils.high_card(self.tricks[-1], sup_col=self.sup_col):
                    break
                self.player_at_turn = self.player_at_turn.next_player
            self.logger.info(
                f"{MarjaPussi.DEFAULT_MSG['trick']} {len(self.tricks)}: {utils.cards_str(self.tricks[-1],fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['goes_to']} {self.player_at_turn.name}.")
            self.player_at_turn.take_trick(
                self.tricks[-1], last=len(self.tricks) == len(utils.CARDS)/4)
            self.game_phase = "QUES"
            if len(self.tricks) == len(utils.CARDS)/4:
                self.game_phase = "DONE"
                self.eval_game()
            else:
                self.tricks.append([])

    def legal_ques(self):
        """my->my,yo->yours,ou->ours"""
        lvl = self.player_at_turn.asking
        quests = []
        if lvl == 0:
            quests += [f"{self.player_at_turn.number},QUES,my{col}" for col in utils.COLORS
                       if utils.contains_pair(self.player_at_turn.cards, col)]
        if lvl <= 1:
            quests += [f"{self.player_at_turn.number},QUES,you"]
        if lvl <= 2:
            quests += [f"{self.player_at_turn.number},QUES,ou{col}" for col in utils.COLORS]
        return quests

    def act_ques(self, player, ques):
        if ques[:2] == "my":
            self.sup_col = col = ques[2]
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['has']} {utils.color_str(col,fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['pair']}")
            self.logger.info(
                f"{col.capitalize()} {MarjaPussi.DEFAULT_MSG['is_sup']}")
            self.player_at_turn.call_sup(col)
            self.game_phase = "TRCK"
        if ques == "you":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['asks_for']} {MarjaPussi.DEFAULT_MSG['pair']}")
            self.player_at_turn.asking = 1
            self.player_at_turn = self.player_at_turn.partner
            self.game_phase = "ANSW"
        if ques[:2] == "ou":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['asks_for']} {utils.color_str(ques[-1], fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['half']}")
            self.player_at_turn.asking = 2
            self.player_at_turn = self.player_at_turn.partner
            self.game_phase = "ANSW"

    def legal_answer(self):
        quest = self.all_actions[-1][-3:]
        if quest == "you":
            answ = [f"{self.player_at_turn.number},ANSW,my{col}" for col in utils.COLORS
                    if utils.contains_pair(self.player_at_turn.cards, col)]
            if not answ:
                return [f"{self.player_at_turn.number},ANSW,nmy"]
            return answ
        else:
            col = quest[-1]
            return [f"{self.player_at_turn.number},ANSW,{(f'ou{col}') if utils.contains_half(self.player_at_turn.cards,col) else f'no{col}'}"]

    def act_answ(self, player, answ):
        old_sup = self.sup_col
        # partner has no pair
        if answ == "nmy":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['no_pair']}")
        # partner has a pair
        if answ[:2] == "my":
            self.sup_col = answ[-1]
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['has']} {utils.color_str(self.sup_col, fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['pair']}")
            self.player_at_turn.call_sup(self.sup_col)
        # partner has a half
        if answ[:2] == "ou":
            pot_sup = answ[-1]
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['has']} {utils.color_str(pot_sup, fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['half']}")
            if utils.contains_half(self.player_at_turn.partner.cards, pot_sup):
                self.sup_col = pot_sup
                self.player_at_turn.call_sup(pot_sup)
                self.logger.info(
                    f"{self.player_at_turn.partner.name} {MarjaPussi.DEFAULT_MSG['has_also']} {utils.color_str(pot_sup, fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['half']} ")
        # partner doesn't have a half
        if answ[:2] == "no":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.DEFAULT_MSG['doesnt_have']} {utils.color_str(answ[-1], fancy=self.fancy)} {MarjaPussi.DEFAULT_MSG['half']}")
        # check if new color is sup
        if self.sup_col != old_sup:
            self.logger.info(
                f"{utils.color_str(self.sup_col, fancy=self.fancy).capitalize()} {MarjaPussi.DEFAULT_MSG['is_sup']}")
        self.player_at_turn = self.player_at_turn.partner
        self.game_phase = "TRCK"

    def eval_game(self):
        if self.game_value == self.rules["start_game_value"]:
            self.playing_player = self.player_at_turn
            self.logger.info(f"Game is done. No one played the game.")
        else:
            self.logger.info(
                f"Game is done. Was played for {self.game_value} points.")
        playing, partner = self.playing_player, self.playing_player.partner
        self.logger.info(
            f"{playing.name} and {partner.name} made {playing.points_made}+{partner.points_made}={(pl:=playing.points_made+partner.points_made)}")
        notplay, noplaypart = self.playing_player.next_player, self.playing_player.next_player.partner
        self.logger.info(
            f"{notplay.name} and {noplaypart.name} made {notplay.points_made}+{noplaypart.points_made}={(npl:=notplay.points_made+noplaypart.points_made)}")
        # logging.info(f"{pl+npl=}")

        if not self.noone_plays:
            self.logger.info(
                f"Playing party made {pl}/{self.game_value} points.")
            if pl >= self.game_value:
                self.logger.info(utils.bold_str(
                    f"Playing party WINS.", fancy=self.fancy))
            else:
                self.logger.info(utils.bold_str(
                    f"Playing party LOSES.", fancy=self.fancy))
        else:
            self.logger.info("There are only loosers this round.")

    def state_dict(self):
        return {
            "players_names": [player.name for player in self.players],
            "players_cards": {player.name: player.cards for player in self.players},
            "game_value": self.game_value,
            "sup_color": self.sup_col,
            "player_at_turn": self.player_at_turn.name,
            "game_phase": self.game_phase,
            "trick_num": len(self.tricks),
            "current_trick": self.tricks[-1],
            "legal_actions": self.legal_actions(),
            "points_playing_party": self.playing_player.points_made + self.playing_player.partner.points_made,
            "points_not_playing_party": self.playing_player.next_player.points_made + self.playing_player.next_player.partner.points_made,
            "won": self.playing_player.points_made + self.playing_player.partner.points_made > self.game_value,
            "noone_plays": self.noone_plays,
        }
    
    DEFAULT_MSG = {
        "got_their_cards": "All players got their cards.",
        "player_says": "says",
        "is_gone": "is gone.",
        "noon_plays": "No one takes the game.",
        "starts": "starts.",
        "takes_the_game": "takes the game for",
        "and": "and",
        "passed_cards": "passed cards",
        "raises_to": "raises to",
        "plays_for": "plays for",
        "plays": "plays",
        "trick": "Trick",
        "goes_to": "goes to",
        "has": "has",
        "is_sup": "is now superior.",
        "asks_for": "asks for",
        "pair": "pair",
        "half": "half",
        "no_pair": "doesn't have a pair.",
        "has_also": "also has",
        "doesnt_have": "doesn't have",
        "game_done_noone": "Game is finished. No one played.",
        "game_done": "Game is finished."
    }

    GERMAN_MSG = {
        "got_their_cards": "Alle Spieler erhalten ihre Karten.",
        "player_says": "sagt",
        "is_gone": "ist weg.",
        "noon_plays": "Niemand spielt das Spiel.",
        "starts": "beginnt.",
        "takes_the_game": "nimmt das Spiel für",
        "and": "und",
        "passed_cards": "haben geschoben.",
        "raises_to": "erhöht auf",
        "plays_for": "spielt für",
        "plays": "legt",
        "trick": "Stich",
        "goes_to": "geht an",
        "has": "hat",
        "is_sup": "ist jetzt Trumpf.",
        "asks_for": "fragt nach",
        "pair": "Paar.",
        "half": "Hälfte.",
        "no_pair": "hat kein Paar.",
        "has_also": "hat auch",
        "doesnt_have": "hat keine",
        "game_done_noone": "Spiel vorbei. Niemand hat gespielt.",
        "game_done": "Spiel vorbei."
    }
    DEFAULT_MSG = GERMAN_MSG

