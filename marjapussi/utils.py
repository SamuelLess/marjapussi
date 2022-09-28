COLORS = [c for c in "rseg"]
VALUES = [v for v in "AZKOU9876"]
CARDS = [c + "-" + v for c in COLORS for v in VALUES]


COLOR_NAMES = {c: name for c, name in zip(
    "rseg", ["Rot", "Schell", "Eichel", "Grün"])}

text_format = {"r": "\033[91m", "s": "\033[93m", "e": "\033[96m", "g": "\033[92m",
               "end": "\033[0m", "bold": "\033[1m", "uline": "\033[4m"}


def allowed_first(cards) -> list:
    """First player has to play an ace, green or any card."""
    allowed = [c for c in cards if c[2] == 'A']
    if not allowed:
        allowed = [c for c in cards if c[0] == 'g']
    if not allowed:
        allowed = cards[:]
    return allowed


def allowed_general(trick, cards, sup_col=None, first=False) -> list:
    if len(trick) == 0 and first:
        return allowed_first(cards)
    if not trick:
        return cards
    trick_col = trick[0][0]
    if first:
        # check for ace
        if (ace := f"{trick_col}-A") in cards:
            return [ace]
    
    if not (allowed:=[c for c in cards if c[0] == trick_col]):
        allowed = [c for c in cards if c[0] == sup_col]
    if (b:=list(filter(lambda card: card == high_card(trick+[card], sup_col=sup_col), allowed))):
        allowed = b
    return allowed if allowed else cards


def high_card(cards, sup_col="") -> str:
    """Finds highest card in single trick."""
    if not cards:
        return None
    high = cards[0]
    col = cards[0][0]
    #!! also not really nice, there has to be a cleaner way but
    for c in cards:
        if c[0] == col and higher_value(high, c):
            high = c

    sup_high = high_card([c for c in cards if c[0] == sup_col]
                         ) if sup_col != "" and sup_col != col else None
    return sup_high if not sup_high is None else high


def higher_value(base, card) -> bool:
    """Returns True if card has higher value than base."""
    for val in VALUES:
        if base[2] == val:
            return False
        if card[2] == val:
            return True


def contains_pair(cards, col) -> bool:
    return f"{col}-K" in cards and f"{col}-O" in cards


def contains_half(cards, col) -> bool:
    return f"{col}-K" in cards or f"{col}-O" in cards


def sorted_cards(cards) -> list:
    return [card for card in CARDS if card in set(cards)]


def card_str(card, fancy=True) -> str:
    return text_format[card[0]] + card + text_format["end"] if fancy else card


def cards_str(cards, fancy=True) -> str:
    return " ".join([card_str(card, fancy=fancy) for card in cards])


def color_str(col, fancy=True) -> str:
    return text_format[col] + COLOR_NAMES[col] + text_format["end"] if fancy else COLOR_NAMES[col]


def bold_str(s, fancy=True) -> str:
    return text_format["bold"] + s + text_format["end"] if fancy else s
