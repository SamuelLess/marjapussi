from math import ceil
import random as rnd

class Policy(object):
    def __init__(self) -> None:
        super().__init__()

    def select_action(self, state, legal_actions) -> str:
        """"""


class RandomPolicy(Policy):
    def __init__(self, prom=True) -> None:
        super().__init__()
    
    def select_action(self, state, legal_actions) -> str:
        return rnd.choice(legal_actions)


class LittleSmartPolicy(Policy):
    def __init__(self) -> None:
        super().__init__()

    def select_action(self, state, legal_actions) -> str:
        if legal_actions[0].split(',')[1] == 'PROV':
            return rnd.choice(legal_actions)
        return rnd.choice(legal_actions[:int(ceil(len(legal_actions)/2))])