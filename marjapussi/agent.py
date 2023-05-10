from marjapussi.game import MarjaPussi
from marjapussi.policy import Policy, RandomPolicy
from marjapussi.utils import CARDS, COLORS, VALUES, all_color_cards, all_value_cards, cards_str, high_card, higher_cards, sorted_cards

from tqdm import trange
import logging
logging.basicConfig(format='%(levelname)s: %(message)s')

class Agent:
    """Implements an agent able to play Marjapussi."""
    def __init__(self, name: str, all_players: list[str], policy: Policy, start_cards: list[str], custom_state_dict={}, log=False) -> None:
        """Creates Agent playing in specific game with given Policy.
        The state_dict as well as the  can be extended with own metrics
        """
        self.name = name
        self.all_players = all_players
        self.policy = policy
        self.state: dict = {
            'player_num': all_players.index(name),
            'cards': start_cards,
            'provoking_history': [],
            'game_value': 115,
            'current_trick': [],
            'all_tricks': [],
            'points': {player: 0 for player in all_players},
            'possible_cards': {player: set() if player == name else set(CARDS[:]).difference(start_cards) for player in all_players},
            'secure_cards': {player: set(start_cards) if player == name else set() for player in all_players},
            'playing_player': '',
        }
        self.custom_state = custom_state_dict

        # give the policy the start hand
        self.policy.start_hand(self.state['possible_cards'])

        self.logger = logging.getLogger("single_agent_logger")
        self.log = log
        if log:
            self.logger.setLevel(logging.INFO)
        if log == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        self.logger.info(f"Created Agent: {self}")

    
    def __str__(self):
        return f"<{self.name} Agent, {type(self.policy).__name__}>"

    def next_action(self, possible_actions):
        """Use policy to calculate best action from given state and possible actions."""
        self.logger.debug(f"{self} selects action.")
        return self.policy.select_action(self.state, possible_actions)

    def observe_action(self, action):
        """Observe an action and update state. (using custom function if given)"""
        player_num, phase, val = action.split(',')
        player_num = int(player_num)
        partner_num = (player_num + 2) % 4
        player_name = self.all_players[player_num]

        if phase == 'PROV' or phase == 'PRMO':
            self.state['provoking_history'].append((player_num, int(val)))
            if int(val):
                self.state['playing_player'] = player_name
                self.state['game_value'] = int(val)
        
        if phase == 'TRCK':
            self.state['current_trick'].append((player_name, val))
            if len(self.state['current_trick']) == 4:
                self.state['all_tricks'].append(self.state['current_trick'][:])
                if self.log:
                    self.logger.debug(f"AGENT {self} evals trick")
                self.state['possible_cards'] = self._possible_cards_after_trick(self.state['possible_cards'], self.state['current_trick'])
                self.state['current_trick'] = []

            if len(self.state['all_tricks']) == 0 and len(self.state['current_trick']) == 0:
                if val.split('-')[1] != 'A':
                    for i in COLORS:
                        self.state['possible_cards'][player_name].discard(f"{i}-A")
                elif val.split('-')[0] != 'g':
                    for i in VALUES:
                        self.state['possible_cards'][player_name].discard(f"g-{i}")

        if phase == 'PASS' or phase == "PBCK":
            self.state['secure_cards'][player_name].discard(val)
            self.state['possible_cards'][player_name].discard(val)
            self.state['secure_cards'][self.all_players[partner_num]].add(val)
            self.state['possible_cards'][self.all_players[partner_num]].add(val)
            #remove from enemys
            self.state['possible_cards'][self.all_players[partner_num]].discard(val)
            self.state['possible_cards'][self.all_players[partner_num]].discard(val)

        if val in CARDS and not (phase == 'PASS' or phase == "PBCK"):
            assert val in self.state['possible_cards'][player_name] or val in self.state['secure_cards'][player_name], "Card has to be possible if it is played."
            for name in self.all_players:
                self.state['possible_cards'][name].discard(val)
                self.state['secure_cards'][name].discard(val)

        # let the policy observe the action as well
        self.policy.observe_action(self.state, action)

        self.logger.debug(f"{self} observed {action}.")

        if self.log == 'DEBUG':
            self._print_state()

    def _print_state(self):
        print(f"State of {str(self)}:")
        print(f"cards: {self.state['cards']}")
        print(f"points: {self.state['points']}")
        print(f"playing_player: {self.state['playing_player']}")
        print(f"possible cards:")
        for p, cards in self.state['possible_cards'].items():
            print(f"{p}:\t {cards_str(list(sorted_cards(cards)))}")
        print(f"secure cards:")
        for p, cards in self.state['secure_cards'].items():
            print(f"{p}:\t {cards_str(list(sorted_cards(cards)))}")
        print(self.state)
    
    def _possible_cards_after_trick(self, possible: dict, trick: list, sup_col='', first_trick=False) -> dict[str]:
        """Returns which player could have which cards after a trick.
        possible: dict with players and possible cards
        trick: list of tuples with (player, card)
        trump: color of trump [r|s|e|g]
        first_trick: whether the trick is the first trick
        """
        if self.log:
            pass
            #print(f"poss befor trick")
            #self._print_state()
        
        trick_col = trick[0][1][0]
        trick_till_here = []
        #print(f"{trick_col=}")
        #first trick
        if first_trick and trick[0][1][2] != 'A': # first trick needs to be an ace or green
            player = trick[0][0]
            possible[player] = (set(possible[player]).difference(set(all_value_cards('A'))))
            if trick[0][1][0] != 'g':
                possible[player] = (set(possible[player]).difference(set(all_color_cards('g'))))
        #any trick
        for player, card in trick:
            if card[0] != trick_col and card[0] != sup_col: # cant have same color and cant have trump
                possible[player] = (set(possible[player]).difference(set(all_color_cards(sup_col))))
            if card[0] != trick_col: # cant have same color
                possible[player] = (set(possible[player]).difference(set(all_color_cards(trick_col))))
            if trick_till_here and card != high_card(trick_till_here + [card]): #cant have any card higher than the highest in the trick
                possible[player] = (set(possible[player]).difference(
                    set(higher_cards(high_card(trick_till_here, sup_col=sup_col),sup_col=sup_col, pool=possible[player]))))
            trick_till_here.append(card)
        if self.log:
            pass
            #print("poss after")
            #self._print_state()
        return possible

    def _standing_cards(player_name, possible: dict, sup_col) -> list:
        """TODO Returns all cards with which player_name """


def test_agents(policy_A: Policy, policy_B: Policy, log_agent=False, log_game=False,
                rounds: int=100, custom_rules: dict={}) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Plays specified number of rounds and returns wins and losses of policy_A and policy_B.
    """
    print(f"Testing {type(policy_A).__name__} vs {type(policy_B).__name__} in {rounds} games.") 
    players = [1,2,3,4] # 2,4 play with policy_A and 1,3 with policy_B
    results = [[0,0],[0,0]]
    for _ in trange(rounds, leave=False):
        testgame = MarjaPussi(
                players, log=log_game, fancy=True, override_rules=custom_rules)
        testgame.players
        agents = {player.name: 
                    Agent(player.name, [p.name for p in testgame.players], policy_A if player.name%2==0 else policy_B, player.cards, log=log_agent) 
                    for player in testgame.players}
        
        while testgame.phase != "DONE":
            player, legal = testgame.player_at_turn.name, testgame.legal_actions()
            chosen_action = agents[player].next_action(legal)
            testgame.act_action(chosen_action)
            for agent in agents.values():
                agent.observe_action(chosen_action)
        res = testgame.end_info()
        playing_player = res['playing_player']
        players: list = res['players']
        if playing_player:
            points_pl = res['players_points'][playing_player] + res['players_points'][players[(players.index(playing_player)+2)%4]]
            won = points_pl >= res['game_value']
            results[playing_player%2][0 if won else 1] += 1
        #reorder players for next round
        players = players[1:] + [players[0]]
    
    party_A_played, party_A_won = sum(results[0]), results[0][0]
    party_B_played, party_B_won = sum(results[1]), results[1][0]
    try:
        print(f"{type(policy_A).__name__} took {party_A_played}/{rounds}={party_A_played*100.0/rounds:.2f}% games " + 
            f"and won {party_A_won}/{party_A_played}={party_A_won*100.0/party_A_played:.2f}%.")
        print(f"{type(policy_B).__name__} took {party_B_played}/{rounds}={party_B_played*100.0/rounds:.2f}% games " +
            f"and won {party_B_won}/{party_B_played}={party_B_won*100.0/party_B_played:.2f}%.")
    except:
        print("!!! Not enough games for sensical evaluation!")
    return (tuple(results[0]), tuple(results[1]))

