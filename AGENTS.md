## Python Agent Rules (Pixi-Based Project)

### Package & Environment

- Use **pixi** for all dependency management and task execution
- Run tasks via `pixi run <task>`
- Respect defined pixi environments
- Do not bypass pixi with system Python, pip, or virtualenvs

### Code Philosophy

- Write only what is needed; no speculative or “just in case” code
- Prefer deleting unused code over keeping it for later
- Keep implementations minimal, explicit, and readable
- Every line of code should be easy to justify and test

### Imports & Structure

- Use absolute imports from the project package
- Do not re-export symbols via `__init__.py` (keep them empty)
- Import directly from the defining module
- Avoid local imports; use only to break unavoidable circular dependencies
- Never use wildcard imports (`from x import *`)
- Use `from __future__ import annotations`

### Typing Rules

- Use modern Python typing:
  - `X | None` instead of `Optional[X]`
  - `list[X]`, `dict[K, V]` instead of `List`, `Dict`
  - PEP 695 generics: `class Repo[T]:`
- Put type parameters on the class definition, not via `Generic`
- Prefer explicit, concrete types over overly generic ones

### Logging

- Use the project logger factory (e.g. `get_logger`)
- Create loggers at module level
- Use f-strings for log messages
- Do not configure logging inside modules

### Documentation & Comments

- No module-level docstrings
- Keep docstrings minimal (one line if needed)
- Do not document obvious behavior
- Avoid comments that restate the code
- Assume the reader can read Python

### Data & Models

- Use Pydantic models for data validation, schemas, and configuration
- Use `BaseSettings` (or equivalent) for configuration with env prefixes
- Use plain `@dataclass` only for simple internal structures without validation needs

### Async & I/O

- Prefer async-first design for all I/O-bound code
- Do not mix sync and async APIs without clear boundaries

### Style & Tooling

- Formatting and linting are enforced via `pixi run lefthook-run`
- Follow the configured line length (typically 88 chars)
- Keep functions small and composable
- Prefer composition over inheritance

### Git & PRs

- Every commit title and PR title must follow the Conventional Commits format (e.g. `feat: add belief tracking`, `fix(engine): correct trick scoring`)

### Testing

- Use pytest
- Mark tests clearly (e.g. `unit`, `integration`)
- Tests should be deterministic and fast by default
- Do not add tests for unused or speculative code
