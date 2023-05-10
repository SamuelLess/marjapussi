from math import ceil
import random as rnd


class Policy(object):
    def __init__(self) -> None:
        super().__init__()

    """
    This method is called when the agent
    observes an action taken by another player.
    The agent shall update their knowledge about
    the game.
    """
    def observe_action(self, state, action) -> None:
        pass

    """
    This method is called when the agent
    gets it's cards.
    """
    def start_hand(self, possible_cards) -> None:
        pass

    """
    This method is called when the agent
    is at it's turn. It responds with an
    action string.
    """
    def select_action(self, state, legal_actions) -> str:
        """"""


class RandomPolicy(Policy):
    def __init__(self, prom=True) -> None:
        super().__init__()

    def observe_action(self, state, action) -> None:
        pass
    
    def select_action(self, state, legal_actions) -> str:
        return rnd.choice(legal_actions)


class LittleSmartPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()

    def observe_action(self, state, action) -> None:
        pass

    def select_action(self, state, legal_actions) -> str:
        if legal_actions[0].split(',')[1] == 'PROV':
            return rnd.choice(legal_actions)
        return rnd.choice(legal_actions[:int(ceil(len(legal_actions)/2))])