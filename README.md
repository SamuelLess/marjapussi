# MarjaPussi
Python implementation of MarjaPussi, mostly following the rules from [Wurzel e. V.](http://wurzel.org/pussi/indexba7e.html?seite=regeln)

There will be a written version of the exact rules somewhere in the future.

## Installation
### Pip
```
python -m pip install git+https://github.com/SamuelLess/marjapussi.git
```
Installation inside docker containers will not work with the `slim` tag due to missing git support.

## Usage
### Import
```
from marjapussi.game import MarjaPussi

game = MarjaPussi(['Name1', 'Name2', 'Name3', 'Name4'])
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


## Contributing
You are more than welcome to send pull requests or simply talk to me if you think something is wrong or could be done more pythonic.
