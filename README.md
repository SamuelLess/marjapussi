# MarjaPussi
Python implementation of MarjaPussi, mostly following the rules from [Wurzel e. V.](http://wurzel.org/pussi/indexba7e.html?seite=regeln), exactly following the rules on [marjapussi.de](https://marjapussi.de/rules).

This package is used by the backend of [marjapussi.de](https://marjapussi.de).

## Installation

Requires Python >= 3.12.

```
pip install marjapussi
```

or

```
pixi add --pypi marjapussi
```

## Quick start

```python
import random
from marjapussi.game import MarjapussiGame

# Cards are shuffled and dealt automatically
game = MarjapussiGame(player_names=("Alice", "Bob", "Charlie", "Diana"))

# Start all players, then play until the game ends
while not game.finished:
    action = random.choice(game.legal_actions())
    game.apply_action(action)

# Serialisable result with scores, tricks, and outcome
info = game.to_finished_info()
print(info.model_dump_json(indent=2))
```

## Core concepts

### Game loop

Every game follows the same pattern:

1. Create a `MarjapussiGame` with player names and dealt hands.
2. Call `game.legal_actions()` to get the list of valid actions for the current state.
3. Pick one and pass it to `game.apply_action(action)`.
4. Repeat until `game.finished` is `True`.

### Phases

The game progresses through these phases automatically:

| Phase | Description |
|---|---|
| `WaitingForStart` | Players confirm readiness |
| `Bidding` | Players bid for the right to play |
| `PassingForth` / `PassingBack` | Partners exchange 4 cards each |
| `Raising` | Playing player may raise the game value |
| `StartTrick` | Trick leader may announce trump or ask partner before playing |
| `Trick` | Remaining players follow suit |
| `AnsweringPair` / `AnsweringHalf` | Partner responds to trump questions |
| `Ended` | Game is over |

### Actions

All actions are Pydantic models (`GameAction`) with a typed `action_type` and a `player` seat. Action types include `Start`, `StopBidding`, `NewBid`, `Pass`, `CardPlayed`, `AnnounceTrump`, `Question`, and `Answer`.

### Replay

Any game can be reconstructed from its metadata and action log:

```python
from marjapussi.game import MarjapussiGame

replayed = MarjapussiGame.replay(info.info, game.actions)
assert replayed.to_finished_info() == info
```

### Types

| Type | Module | Description |
|---|---|---|
| `Card` | `marjapussi.types` | Immutable card with `suit` and `value`, serialises as `"r-A"` |
| `Suit` | `marjapussi.types` | `Green`, `Acorns`, `Bells`, `Red` |
| `Value` | `marjapussi.types` | `Six` through `Ace` |
| `PlaceAtTable` | `marjapussi.types` | Seat index 0-3 with `.partner()`, `.next()`, `.prev()` |
| `Points` | `marjapussi.types` | Integer wrapper with arithmetic support |
| `GameFinishedInfo` | `marjapussi.state` | Full game result including tricks, scores, and events |

## Development

```
pixi install
pixi run test
```

## Contributing

Pull requests and feedback are welcome. If you think something is wrong or could be improved, feel free to open an issue or reach out.

---

<details>
<summary>Legacy implementation (v1)</summary>

The original implementation is still available under `marjapussi.legacy`. It uses plain Python classes with string-based actions and is fully preserved for backward compatibility.

```python
import random
from marjapussi.legacy.game import MarjaPussi

game = MarjaPussi(["Name1", "Name2", "Name3", "Name4"])

while not game.phase == "DONE":
    action = random.choice(game.legal_actions())
    game.act_action(action)
```

Actions are strings in the format `"<player>,<phase>,<value|card>"`, for example `"0,PROV,120"` or `"2,TRCK,r-A"`.

A compatibility layer in `marjapussi.compat` provides converters between the two formats:

```python
from marjapussi.compat import v1_action_to_v2, v2_action_to_v1, v1_actions_to_v2
```

</details>
