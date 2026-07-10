# routewise

**Cost-aware LLM request router** — scores every incoming query for difficulty, routes it to the cheapest model tier that can actually handle it, caches near-duplicates, and degrades gracefully when a provider fails or rate-limits.

**Live demo:** https://llm-router-nine-eta.vercel.app/
**Backend API:** https://llm-router-d2b2.onrender.com

---

## The problem

Sending every request — `"hi"`, a summarization job, a system-design question — to the same frontier-class model wastes money at scale. Most queries don't need it. This router sits between the caller and the LLM providers, decides how hard each query actually is, and sends it to the cheapest tier that can handle it.

## Screenshots

![Hero — live routing diagram](backend\router\screenshots\hero.png)
*The right panel is a real circuit diagram of the three tiers, not decoration — the active node lights up based on the actual routing decision for whatever you just typed.*

![Metrics dashboard](backend\router\screenshots\metrics.png)
*Pulled live from `/stats`, aggregating every real request this instance has logged.*

## How it works

1. **Score** — a LightGBM regressor, trained on 6,500 hand-validated and LLM-labeled queries, predicts a 0–10 difficulty score directly from the query text. Runs locally in under 100ms; no API call needed to make this decision.
2. **Route** — the score maps to a tier (`cheap` / `mid` / `frontier`). A safety margin biases borderline queries toward the *safer*, more capable tier rather than the cheaper one — under-routing a hard query to a weak model is worse than over-routing an easy one.
3. **Respond** — a semantic cache (embedding similarity, conservative 0.95 threshold) checks for near-duplicate queries first. If the assigned tier's provider call fails or rate-limits, the request automatically steps down to the next tier instead of erroring out.

## Architecture

```
Query → [semantic cache check] → [difficulty classifier] → [tier router] → [provider + failover] → response
                ↓ (hit)                                              ↓ (fail)
           cached response                                    next tier down
```

## Tech stack

| Layer | Tools |
|---|---|
| Difficulty model | LightGBM, `sentence-transformers` (MiniLM-L6-v2) |
| Backend | FastAPI, SQLAlchemy, Supabase (Postgres) |
| Providers | Groq (mid/frontier tiers), Ollama (local cheap tier) |
| Frontend | React, Vite, Tailwind, Recharts |
| Deployment | Docker, Render (backend), Vercel (frontend) |

## Model tiers

| Tier | Model | Backend |
|---|---|---|
| Cheap | `llama3.2:3b` | Local via Ollama (falls back to Groq's `llama-3.1-8b-instant` if Ollama is unreachable) |
| Mid | `llama-3.3-70b-versatile` | Groq |
| Frontier | `deepseek-r1-distill-llama-70b` | Groq |

## Key engineering decisions

- **Continuous 0–10 score, not fixed categories.** Lets routing thresholds be retuned later without relabeling any data.
- **Cache threshold is deliberately conservative (0.95).** Semantic similarity isn't correctness — *"convert 5 miles to km"* and *"convert 10 miles to km"* are ~95%+ similar in embedding space but have different correct answers. Erring toward fewer cache hits over risking a wrong cached answer.
- **Asymmetric safety margin at the frontier boundary.** Sending an easy query to a pricier tier costs a bit more money; sending a hard query to a weaker tier risks a bad answer. The margin only nudges borderline cases *up*, never down.
- **Fallback lives inside the cheap tier, not as a tier-level chain.** If Ollama fails, the request is served by Groq instead — transparently, still logged as tier `cheap`.

## Honest limitations


- **Ollama doesn't run in the cloud deployment.** The hosted version on Render has no local GPU, so every "cheap" tier request there hits Ollama, fails, and falls back to Groq automatically. Local demos are the only place the actual local-model routing runs. This is by design, not a bug.
- **Failover is single-provider.** The fallback chain moves between tiers within Groq (plus the Ollama→Groq fallback above). There's no second independent provider (e.g. OpenAI) wired in, so a full Groq outage isn't covered.
- **The difficulty model has a known weak spot.** It underperforms on system-design/architecture-style queries specifically, because the training data (general instruction-style queries) has very few real examples of that category. Documented, not silently hidden.
- **Training labels have some noise.** Labels came from an LLM auto-labeler validated against a small hand-labeled gold set, not a fully human-audited dataset. Current model: MAE ≈ 1.09, Spearman ≈ 0.74 on held-out data.
- **CORS is wide open (`allow_origins=["*"]`)** — fine for a public demo, not how this would ship for real production traffic.

## Running it locally

```bash
git clone https://github.com/Ishan-5/llm-router.git
cd llm-router

# backend
pip install -r requirements.txt
uvicorn router.main:app --reload

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Requires a `.env` with `GROQ_API_KEY` and `DATABASE_URL` (Supabase Postgres connection string). Ollama is optional locally — if it's not running, the cheap tier automatically falls back to Groq.

## Running it with Docker

```bash
docker compose build
docker compose up
```

Ollama still needs to run natively on your host machine (not containerized) — see `docker-compose.yml` for the `host.docker.internal` networking that lets the container reach it.

## Project structure

```
llm-router/
├── backend/
│   ├── router/                         # FastAPI backend
│   │   ├── main.py                     # /route and /stats endpoints
│   │   ├── classifier.py               # wraps the trained difficulty model
│   │   ├── providers.py                # Groq + Ollama calls, cost calculation
│   │   ├── rate_limiter.py             # tier-level failover
│   │   ├── cache.py                    # semantic cache
│   │   ├── config.py                   # model tiers, fallback chain, pricing
│   │   ├── db.py                       # request logging (Postgres via SQLAlchemy)
│   │   └── ollama_client.py            # Ollama HTTP client
│   ├── src/
│   │   ├── train_difficulty_model.py   # LightGBM training script
│   │   └── predict_difficulty.py       # inference + tier mapping
│   ├── dataset_pipeline/               # labeling scripts + labeled dataset
│   │   ├── labeling_dataset/
│   │   │   ├── label_gold_dataset.py
│   │   │   └── label_merged_dataset_full.py
│   │   └── datasets/
│   │       ├── labeled_dataset/
│   │       └── raw/
│   ├── eval/                           # dataset collection scripts
│   │   ├── get_datasets/
│   │   └── datasets/
│   └── models/
│       └── difficulty_regressor.joblib
├── frontend/                           # React + Vite + Tailwind + Recharts
│   ├── src/
│   │   ├── components/
│   │   │   ├── Header.jsx
│   │   │   ├── Footer.jsx
│   │   │   ├── RoutingDiagram.jsx
│   │   │   ├── MetricsDashboard.jsx
│   │   │   ├── HowItWorks.jsx
│   │   │   └── ThemeToggle.jsx
│   │   ├── App.jsx
│   │   ├── api.js
│   │   ├── main.jsx
│   │   ├── index.css
│   │   └── useTheme.js
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.js
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example

```

What's not built yet

Being direct about this rather than implying otherwise: no automated test suite, no CI pipeline, no multi-provider failover, no auth/rate-limiting for public API use. These would be the next additions if this moved past portfolio scope.



*Built by [Ishan](https://github.com/Ishan-5) · [LinkedIn](https://linkedin.com/in/devansh584)*
