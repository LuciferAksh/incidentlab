# Contributing

Run `python scripts/setup.py` once and start with `python scripts/dev.py --no-build`.

Keep fault labels outside `diagnose()`. When changing ranking, add an evaluation case that can fail independently of the implementation. Use clean observation windows, explicit sample sizes, and honest missing-data behavior.

Before proposing a change:

1. Run `npm run build`.
2. Run `.venv/Scripts/python.exe -m pytest -q` on Windows (`.venv/bin/python` on Unix).
3. Run that interpreter with `-m ruff check incidentlab scripts tests` and `-m ruff format --check incidentlab scripts tests`.
4. Stop the running lab, then run `scripts/verify.py --start --rounds 2` with that interpreter.
5. For UI changes, inspect the browser workflow and a narrow viewport.

Use `npm run format` for TypeScript, CSS, JSON, and Markdown. Do not commit telemetry, credentials, environments, or generated bundles.

Python versions are pinned in `requirements.lock`; Node versions in `package-lock.json`. Refresh Python dependencies in a clean environment from `pyproject.toml`, run the full suite, then regenerate with `pip freeze --exclude incidentlab`. Never include editable local paths in the lock.
