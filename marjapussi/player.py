import marjapussi.utils as utils


class Player():
    """Implements a player of the MarjaPussi game."""

    def __init__(self, name: str, number: int, points: dict) -> None:
        self.name = name
        self.number = number
        self.points = points #defined by rules of the game
        self.partner: Player = None
        self.next_player: Player = None
        self.asking = 0  # 0 -> my; 1 -> yours; 2 -> ours
        self.cards = []  # players card
        self.still_prov = True
        self.prov_val = 0  # highest value said
        self.tricks = []  # all tricks self made
        self.sup_calls = []  # all colors called sup by self
        self.points_made = 0  # sum of points of self

    def take_trick(self, trick, last=False) -> None:
        self.tricks.append(trick)
        self.points_made += sum([self.points[card[2]]
                                for card in trick]) + (self.points["L"] if last else 0)

    def call_sup(self, col) -> None:
        # points go to player calling or asking
        if col in self.sup_calls:
            return
        self.sup_calls.append(col)
        self.points_made += self.points[col]

    def give_card(self, c: str) -> None:
        """Gives the player an additional card."""
        self.cards.append(c)
        # ? sorting doesn't need to be here but is convenient
        self.cards = utils.sorted_cards(self.cards)

    def take_card(self, c: str) -> None:
        self.cards = list(set(self.cards) - {c, })
        self.cards = utils.sorted_cards(self.cards)

    def set_partner(self, partner) -> None:
        self.partner: Player = partner

    def set_next_player(self, next_player) -> None:
        self.next_player = next_player

    def player_info(self) -> dict:
        return {'name': self.name, 'cards': self.cards}
