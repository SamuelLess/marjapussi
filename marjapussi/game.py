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

    def __init__(self, player_names, override_rules={}, log=True, fancy=True, language=1) -> None:
        # init logger
        self.logger = logging.getLogger("single_game_logger")
        if log:
            self.logger.setLevel(logging.INFO)
        if log == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        self.fancy = fancy
        self.language = language
        # init rules
        self.rules = MarjaPussi.DEFAULT_RULES | override_rules
        self.logger.debug(f"Ruleset: {override_rules}")
        # init players and cards
        assert len(player_names) == 4, "There have to be 4 names!"
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
        self.logger.info(MarjaPussi.INFO_MSG["got_their_cards"][self.language])

        for i in range(4):
            self.players[i].set_partner(self.players[(i+2) % 4])
            self.players[i].set_next_player(self.players[(i+1) % 4])

        self.original_cards = {p.name: p.cards[:] for p in self.players}
        self.player_at_turn = self.players[0]
        self.playing_player = None
        self.game_value = self.rules["start_game_value"]
        self.no_one_plays = True
        self.phase = self.rules["start_phase"]
        self.passed_cards = {"forth": [], "back": []}
        self.all_actions = []
        self.sup_col = ""
        self.all_sup = []
        self.tricks = [[]]

    def legal_actions(self) -> list:
        """
        phases: PROV, PASS, PBCK, PRMO, FTRI, QUES, ANSW, TRCK, DONE
        action -> <player number>','<phase>','<val | card>
        """
        legal_in_phase = {
            "PROV": self.legal_prov,
            "PASS": self.legal_pass,
            "PBCK": self.legal_passing_back,
            "PRMO": self.legal_prmo,
            "QUES": self.legal_ques,#also includes act_trck
            "ANSW": self.legal_answer,
            "TRCK": self.legal_trck,
            "DONE": lambda: []
        }[self.phase]
        return legal_in_phase()

    def act_action(self, action) -> bool:
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

        act_in_phase = {
            "PROV": self.act_prov,
            "PASS": self.act_pass,
            "PBCK": self.act_pbck,
            "PRMO": self.act_prmo,
            "QUES": self.act_ques,
            "ANSW": self.act_answ,
            "TRCK": self.act_trck,
        }[action_list[1]]
        act_in_phase(action_list[0], action_list[2])
        return True

    def legal_prov(self):
        actions = [f"{self.player_at_turn.number},PROV,{000}"]
        for poss_val in range(self.game_value+5, self.rules["max_game_value"]+1, 5):
            actions.append(f"{self.player_at_turn.number},PROV,{poss_val}")
        return actions

    def act_prov(self, player, value):
        value = int(value)
        if value > self.game_value:
            self.game_value = value
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['player_says'][self.language]} {value}.")
        else:
            self.player_at_turn.still_prov = False
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['is_gone'][self.language]}")
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
                    f"{MarjaPussi.INFO_MSG['noon_plays'][self.language]}. {self.player_at_turn.name} {MarjaPussi.INFO_MSG['plays'][self.language]}")
                self.phase = "TRCK"
            else:
                # last prov player takes the game
                self.no_one_plays = False
                self.player_at_turn = [
                    p for p in self.players if p.still_prov][0]
                self.playing_player = self.player_at_turn
                self.player_at_turn = self.playing_player.partner
                self.logger.info(
                    f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['takes_the_game'][self.language]} {self.game_value}.")
                self.phase = "PASS"

    def legal_pass(self):
        actions = []
        for card in self.playing_player.partner.cards:
            if card in self.passed_cards["forth"]:
                continue
            actions.append(f"{self.playing_player.partner.number},PASS,{card}")
        return actions

    def act_pass(self, player, card):
        if len(self.passed_cards["forth"]) < 4:
            self.passed_cards["forth"].append(card)
        if len(self.passed_cards["forth"]) == 4:
            self.logger.debug(
                f"{player} gives {utils.cards_str(self.passed_cards['forth'], fancy=self.fancy)}.")
            for c in self.passed_cards["forth"]:
                self.playing_player.give_card(c)
                self.playing_player.partner.take_card(c)
            self.player_at_turn = self.player_at_turn.partner
            self.phase = "PBCK"

    def legal_passing_back(self):
        actions = []
        for card in self.playing_player.cards:
            if card in self.passed_cards["back"]:
                continue
            actions.append(f"{self.playing_player.number},PBCK,{card}")
        return actions

    def act_pbck(self, player, card):
        if len(self.passed_cards["back"]) < 4:
            self.passed_cards["back"].append(card)
        if len(self.passed_cards["back"]) == 4:
            self.logger.debug(
                f"{player} gives {utils.cards_str(self.passed_cards['back'], fancy=self.fancy)}.")
            for c in self.passed_cards["back"]:
                self.playing_player.take_card(c)
                self.playing_player.partner.give_card(c)
            self.player_at_turn = self.playing_player
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['and'][self.language]} {self.player_at_turn.partner.name} {MarjaPussi.INFO_MSG['passed_cards'][self.language]}")
            self.phase = "PRMO"

    def legal_prmo(self):
        actions = [f"{self.player_at_turn.number},PRMO,{000}"]
        for poss_val in range(self.game_value+5, self.rules["max_game_value"]+1, 5):
            actions.append(f"{self.player_at_turn.number},PRMO,{poss_val}")
        return actions

    def act_prmo(self, player, value):
        value = int(value)
        if value > self.game_value:
            self.game_value = value
            self.logger.info(
                f"{self.playing_player.name} {MarjaPussi.INFO_MSG['raises_to'][self.language]} {value}.")
        else:
            self.logger.info(
                f"{self.playing_player.name} {MarjaPussi.INFO_MSG['plays_for'][self.language]} {self.game_value}.")
        self.phase = "TRCK"

    def legal_trck(self):
        return [f"{self.player_at_turn.number},TRCK,{c}" for c in
                utils.allowed_general(self.tricks[-1], self.player_at_turn.cards,
                                      sup_col=self.sup_col, first=(len(self.tricks[0]) != 4))]

    def act_trck(self, player, card):
        self.logger.info(
            f"{self.players_dict[player].name} {MarjaPussi.INFO_MSG['plays'][self.language]} {utils.card_str(card, fancy=self.fancy)}.")
        self.phase = 'TRCK'
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
                f"{MarjaPussi.INFO_MSG['trick'][self.language]} {len(self.tricks)}: {utils.cards_str(self.tricks[-1],fancy=self.fancy)} {MarjaPussi.INFO_MSG['goes_to'][self.language]} {self.player_at_turn.name}.")
            self.player_at_turn.take_trick(
                self.tricks[-1], last=len(self.tricks) == len(utils.CARDS)/4)
            self.phase = "QUES"
            if len(self.tricks) == len(utils.CARDS)/4:
                self.phase = "DONE"
                self.eval_game()
            else:
                self.tricks.append([])

    def legal_ques(self):
        """my->my,yo->yours,ou->ours"""
        lvl = self.player_at_turn.asking
        quests = []
        if lvl == 0:
            quests += [f"{self.player_at_turn.number},QUES,my{col}" for col in utils.COLORS
                       if (utils.contains_pair(self.player_at_turn.cards, col) and col not in self.all_sup)]
        if lvl <= 1:
            quests += [f"{self.player_at_turn.number},QUES,you"]
        if lvl <= 2:
            quests += [f"{self.player_at_turn.number},QUES,ou{col}" for col in utils.COLORS]
        return quests+self.legal_trck()

    def act_ques(self, player, ques):
        if ques[:2] == "my":
            self.sup_col = col = ques[2]
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has'][self.language]} {utils.color_str(col,fancy=self.fancy)} {MarjaPussi.INFO_MSG['pair'][self.language]}")
            self.logger.info(
                f"{col.capitalize()} {MarjaPussi.INFO_MSG['is_sup'][self.language]}")
            self.player_at_turn.call_sup(col)
            self.all_sup.append(col)
            self.phase = "TRCK"
        if ques == "you":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['asks_for'][self.language]} {MarjaPussi.INFO_MSG['pair'][self.language]}")
            self.player_at_turn.asking = 1
            self.player_at_turn = self.player_at_turn.partner
            self.phase = "ANSW"
        if ques[:2] == "ou":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['asks_for'][self.language]} {utils.color_str(ques[-1], fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")
            self.player_at_turn.asking = 2
            self.player_at_turn = self.player_at_turn.partner
            self.phase = "ANSW"

    def legal_answer(self):
        quest = self.all_actions[-1][-3:]
        if quest == "you":
            answ = [f"{self.player_at_turn.number},ANSW,my{col}" for col in utils.COLORS
                    if (utils.contains_pair(self.player_at_turn.cards, col) and not col in self.all_sup)]
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
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['no_pair'][self.language]}")
        # partner has a pair
        if answ[:2] == "my":
            self.sup_col = answ[-1]
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has'][self.language]} {utils.color_str(self.sup_col, fancy=self.fancy)} {MarjaPussi.INFO_MSG['pair'][self.language]}")
            self.player_at_turn.call_sup(self.sup_col)
            self.all_sup.append(self.sup_col)
        # partner has a half
        if answ[:2] == "ou":
            pot_sup = answ[-1]
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['has'][self.language]} {utils.color_str(pot_sup, fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")
            if utils.contains_half(self.player_at_turn.partner.cards, pot_sup):
                self.sup_col = pot_sup
                self.player_at_turn.call_sup(pot_sup)
                self.logger.info(
                    f"{self.player_at_turn.partner.name} {MarjaPussi.INFO_MSG['has_also'][self.language]} {utils.color_str(pot_sup, fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]} ")
        # partner doesn't have a half
        if answ[:2] == "no":
            self.logger.info(
                f"{self.player_at_turn.name} {MarjaPussi.INFO_MSG['doesnt_have'][self.language]} {utils.color_str(answ[-1], fancy=self.fancy)} {MarjaPussi.INFO_MSG['half'][self.language]}")
        # check if new color is sup
        if self.sup_col != old_sup:
            self.all_sup.append(self.sup_col)
            self.logger.info(
                f"{utils.color_str(self.sup_col, fancy=self.fancy).capitalize()} {MarjaPussi.INFO_MSG['is_sup'][self.language]}")
        self.player_at_turn = self.player_at_turn.partner
        self.phase = "TRCK"

    def eval_game(self):
        self.logger.info(MarjaPussi.INFO_MSG["game_done"][self.language])
        if self.no_one_plays:
            return
        playing, partner = self.playing_player, self.playing_player.partner
        self.logger.info(
            f"{playing.name} {MarjaPussi.INFO_MSG['and'][self.language]} {partner.name}: {playing.points_made}+{partner.points_made}={(pl:=playing.points_made+partner.points_made)}")
        notplay, noplaypart = self.playing_player.next_player, self.playing_player.next_player.partner
        self.logger.info(
            f"{notplay.name} {MarjaPussi.INFO_MSG['and'][self.language]} {noplaypart.name}: {notplay.points_made}+{noplaypart.points_made}={(npl:=notplay.points_made+noplaypart.points_made)}")

        if not self.no_one_plays:
            self.logger.info(
                f"{MarjaPussi.INFO_MSG['playing_party'][self.language]}: {pl}/{self.game_value}")
            if pl >= self.game_value:
                self.logger.info(utils.bold_str(
                    MarjaPussi.INFO_MSG['win'][self.language], fancy=self.fancy))
            else:
                self.logger.info(utils.bold_str(
                    MarjaPussi.INFO_MSG['loose'][self.language], fancy=self.fancy))
        else:
            self.logger.info("There are only loosers this round.")

    def players_cards(self):
        return {player.name: player.cards for player in self.players}

    def state_dict(self):
        return {
            "players_names": [player.name for player in self.players],
            "players_cards": {player.name: player.cards for player in self.players},
            "game_value": self.game_value,
            "sup_color": self.sup_col,
            "player_at_turn": self.player_at_turn.name,
            "game_phase": self.phase,
            "trick_num": len(self.tricks),
            "current_trick": self.tricks[-1],
            "legal_actions": self.legal_actions(),
            "points_playing_party": None if self.playing_player == None else self.playing_player.points_made + self.playing_player.partner.points_made,
            "points_not_playing_party": None if self.playing_player == None else self.playing_player.next_player.points_made + self.playing_player.next_player.partner.points_made,
            "won": None if self.playing_player == None else self.playing_player.points_made + self.playing_player.partner.points_made > self.game_value,
            "noone_plays": None if self.playing_player == None else self.no_one_plays,
        }
    
    def end_info(self):
        """Return dict with all relevant info."""
        return {
            "players": [p.name for p in self.players],
            "cards": self.original_cards,
            "passed_cards": self.passed_cards,
            "tricks": self.tricks,
            "actions": self.all_actions,
            "playing_player": self.playing_player.name if not self.no_one_plays else None,
            "game_value": self.game_value,
            "players_points": {p.name: p.points_made for p in self.players},
            "players_sup": {p.name: p.sup_calls for p in self.players},
            "schwarz_game": (len(self.players[0].tricks)+len(self.players[2].tricks) == 9),
        }

    INFO_MSG = {
        "got_their_cards": ["All players got their cards.", "Alle Spieler erhalten ihre Karten."],
        "player_says": ["says", "sagt"],
        "is_gone": ["is gone.", "ist weg."],
        "noon_plays": ["No one takes the game.", "Niemand spielt das Spiel."],
        "starts": ["starts.", "beginnt."],
        "takes_the_game": ["takes the game for", "nimmt das Spiel für"],
        "and": ["and", "und"],
        "passed_cards": ["passed cards.", "haben geschoben."],
        "raises_to": ["raises to", "erhöht auf"],
        "plays_for": ["plays for", "spielt für"],
        "plays": ["plays", "legt"],
        "trick": ["Trick", "Stich"],
        "goes_to": ["goes to", "geht an"],
        "has": ["has", "hat"],
        "is_sup": ["is now superior.", "ist jetzt Trumpf"],
        "asks_for": ["asks for", "fragt nach"],
        "pair": ["pair.", "Paar."],
        "half": ["half.", "Hälfte."],
        "no_pair": ["doesn't have a pair.", "hat kein Paar."],
        "has_also": ["also has", "hat auch"],
        "doesnt_have": ["doesn't have", "hat keine"],
        "game_done": ["Game is finished.", "Spiel vorbei."],
        "win": ["Playing party WINS.", "Spielende Partei hat gewonnen!"],
        "loose": [f"Playing party WINS.", "Spielende Partei hat verloren."],
        "noonewins": ["No one played, no one wins...", "Niemand hat gespielt, Niemand gewinnt..."],
        "playing_party": ["Playing Party", "Spielende Partei"]
    }
