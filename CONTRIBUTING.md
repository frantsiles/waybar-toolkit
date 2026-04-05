# Contributing

Thanks for contributing to Waybar Toolkit.

## Development principles
- Keep changes focused and small when possible.
- Prefer clarity over cleverness.
- Preserve current behavior unless the change explicitly targets it.
- Do not introduce heavy dependencies for functionality that can be implemented with the standard library or existing project patterns.

## Programming guidelines
- Target Python 3.10+.
- Follow existing module structure (`monitors`, `processes`, `utils`) and avoid cross-module coupling when a backend/helper boundary already exists.
- Add docstrings to public classes/functions and keep naming explicit.
- Handle external command failures and `/proc` parsing failures defensively.
- Avoid broad side effects in UI handlers; move reusable logic into helper methods.
- Keep UI text concise and status messages actionable.

## Quality checks before PR
- Install dev tooling once: `pip install --user -e ".[dev]"`.
- Run linting: `python -m ruff check .`.
- Run formatting check/fix as needed: `python -m ruff format .`.
- Run tests: `python -m pytest`.
- Run type checks: `python -m mypy`.
- Run syntax checks for touched modules (`python -m py_compile ...`) when iterating quickly.
- If you add logic with non-trivial behavior, add/update tests in `tests/`.
- Review your own diff and remove unrelated changes.
- Update `CHANGELOG.md` for user-visible behavior changes.
- Keep project metadata version aligned with release notes when preparing a release.

## Rules for AI agents and AI-assisted contributions
- AI-generated patches must be reviewed by a human before merge.
- Never commit secrets, tokens, local machine paths, or private identifiers.
- Do not run destructive commands unless explicitly requested by the maintainer.
- Keep edits minimal and localized to the requested scope.
- Preserve selection/state identity when mutating ordered UI collections (do not rely on stale indices after reordering).
- When committing AI-assisted changes, include co-author attribution when required by repository workflow.

## Pull request guidance
- Use clear commit messages that describe intent and scope.
- Include a short validation note (what was tested and how).
- Mention limitations or known follow-up work if any.
