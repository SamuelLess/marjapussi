# MarjaPussi
Python implementation of MarjaPussi, mostly following the rules from [Wurzel e. V.](http://wurzel.org/pussi/indexba7e.html?seite=regeln), exactly following the rules on [marjapussi.de](https://marjapussi.de/rules).

This package is used by the backend of [marjapussi.de](https://marjapussi.de).

## Installation

Requires Python >= 3.12.

### Pip
```
python -m pip install git+https://github.com/SamuelLess/marjapussi.git
```

### Pixi (development)
```
pixi install
pixi run test
```

## Usage

### v1 (legacy, fully backward-compatible)
```python
from marjapussi.game import MarjaPussi

game = MarjaPussi(['Name1', 'Name2', 'Name3', 'Name4'])

while not game.phase == "DONE":
    action = random.choice(game.legal_actions())
    game.act_action(action)
```

### v2 (Pydantic-typed, event-sourced)
```python
from marjapussi.v2.game import MarjapussiGame
from marjapussi.v2.rules import deck, sorted_cards
from marjapussi.v2.types import Card

# Deal cards
import random
cards = deck()
random.shuffle(cards)
hands = tuple(sorted_cards(cards[i*9:(i+1)*9]) for i in range(4))

game = MarjapussiGame(
    player_names=("Alice", "Bob", "Charlie", "Diana"),
    start_cards=hands,
)

# Game loop: same pattern, fully typed actions
while not game.finished:
    action = random.choice(game.legal_actions())
    game.apply_action(action)

# Serializable output matching the Rust JSON format
info = game.to_finished_info()
print(info.model_dump_json(indent=2))
```

#### Replay from action log
```python
# Reconstruct any game from metadata + action log
replayed = MarjapussiGame.replay(info.info, game.actions)
assert replayed.to_finished_info() == info
```

## Contributing
You are more than welcome to send pull requests or simply talk to me if you think something is wrong or could be done more pythonic.
