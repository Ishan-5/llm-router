# Contributing to RouteWise

Thanks for taking a look. This is a small, single-maintainer project, but issues
and pull requests are genuinely welcome — small, focused changes are the easiest
to review and merge.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). For
security problems, follow [SECURITY.md](SECURITY.md) rather than opening a public
issue.

## Ways to contribute

- 🐛 **Bug reports** — use the [bug report form](.github/ISSUE_TEMPLATE/bug_report.yml).
  Include the version/commit, what you did, what happened, and what you expected.
- ✨ **Feature ideas** — use the [feature request form](.github/ISSUE_TEMPLATE/feature_request.yml).
- 📝 **Docs** — typos, unclear steps and stale numbers are real bugs here; part of
  the test suite exists to catch exactly that (see [Tests](#tests)).
- 🔧 **Code** — see the workflow below.

## Local setup

Requires **Python 3.11+**, **Node 20.10+**, and npm.

```bash
git clone https://github.com/Ishan-5/llm-router.git
cd llm-router

# backend
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
cd backend
pip install -r ../requirements.txt -r ../requirements-dev.txt
cd ..

# CLI
cd cli && npm ci && cd ..

# web dashboard
cd frontend && npm ci && cd ..
```

The backend needs a `.env` — copy `.env.example` and fill in the keys you have
(`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `DATABASE_URL`, and so on). Run it with
`cd backend && uvicorn router.main:app --reload`, and the dashboard with
`cd frontend && npm run dev`. Full notes are in the
[README](README.md#-running-it-locally).

## Tests

CI runs three jobs; run the same commands before opening a PR:

```bash
ruff check .                                  # lint: correctness-only rule set
pytest backend/tests/                         # backend suite
pytest backend/tests/ --cov=backend/router    # with coverage

cd cli      && npm test                       # tsc build + node:test
cd frontend && npm run build                  # dashboard must build clean
```

Two things worth knowing:

- The **CLI tests need Node 20.10+**, and `node --test` only expands a glob on
  newer Node. That is why `cli/package.json` leaves the test glob unquoted and
  lets the shell do the expansion.
- The backend suite includes **guard tests** that read `README.md` and
  `frontend/src/productMetrics.js`. If you change a public number, update the
  source of truth and the README together, or the guards fail — that is the point
  of them.

## Changing the model

The difficulty scorer is a shipped artifact with a documented contract:

1. Retrain and deploy only if the candidate beats the live model:
   `cd backend && python mlops/retrain.py --deploy --version vNN`
2. The tool appends a row to `backend/mlops/model_metrics.csv`.
3. Update [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) and any public figure in
   `frontend/src/productMetrics.js`.
4. Run `pytest backend/tests/test_difficulty_model_gate.py` — it warns on a
   metric regression and fails if the card, the tracker and the artifact disagree.

## Commit and pull-request conventions

- Branch off `main`: `git checkout -b fix/short-description`.
- Prefer **small, focused commits** (a few files each) with a clear subject of the
  form `area: what changed` — e.g. `ci: run the CLI job on Node 20`.
- Keep a PR to one concern, fill in the
  [PR template](.github/PULL_REQUEST_TEMPLATE.md), and tick the checks that apply.
- Don't commit secrets. `.env`, `frontend/.env` and `venv/` are ignored; keep it
  that way.

## License

By contributing you agree that your work is released under the project's
[LICENSE](LICENSE).
