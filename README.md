# MarjaPussi

## Install
### Pip
```
```

## Usage
### Import
```
from marjapussi.game import MarjaPussi

game = MarjaPussi([Name1, Name2, Name3, Name4])
```
### Keyword Arguments
- `log = [True | False | 'DEBUG')`: sets printlevel for `game.logger`.
- `fancy = [True | False]`: enable color output using ANSI escape sequences
- `override_rules`: dict overriding entries in `MarjaPussi.DEFAULT_RULES`

### Example Game Loop
```
while not game.phase == "DONE":
    legal_actions = game.legal_actions()
    #choosing an action
    action = random.choice(legal_actions)
    #returns True at success
    game.act_action(action)
```