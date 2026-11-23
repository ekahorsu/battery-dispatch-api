# Battery Dispatch Optimization API

[![ci-cd](https://github.com/ekahorsu/battery-dispatch-api/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/ekahorsu/battery-dispatch-api/actions/workflows/ci-cd.yml)

A cloud-deployed REST API that computes the profit-maximizing charge and discharge schedule of a grid battery from electricity prices. It solves a linear program for energy arbitrage, compares the result with a rule-based baseline, and runs as a Docker container on Google Cloud Run with automated testing and deployment through GitHub Actions.

**Live service:** `https://<your-cloud-run-url>/docs` (interactive documentation, add the URL after deploying)

## Overview

A battery earns money in an energy market by charging when prices are low and discharging when they are high. Given a day of hourly prices and the battery's technical limits, the service answers: *what schedule maximizes profit, and how much better is it than a simple rule?*

The algorithmic core is the same kind of model used in market-facing energy management software: an optimization model wrapped in a validated, tested and deployable interface.

## Optimization model

For periods *t = 1..T* with price *p_t* ($/MWh) and interval length Δt, the decision variables are the charging power *c_t*, the discharging power *d_t* and the state of charge *s_t*.

```
maximize    Σ_t [ p_t (d_t − c_t) Δt − k d_t Δt ]

subject to  s_t = s_{t−1} + η_c c_t Δt − d_t Δt / η_d        (energy balance)
            0 ≤ c_t ≤ P,   0 ≤ d_t ≤ P                         (power rating)
            0 ≤ s_t ≤ E,   s_T ≥ s_final                       (energy capacity, end-of-day state)
```

where *E* is the energy capacity, *P* the power rating, *η_c* and *η_d* the charging and discharging efficiencies, and *k* a cycling (degradation) cost per MWh discharged. The model is solved with the HiGHS solver through SciPy.

The **rule-based baseline** charges at full power in the cheapest 20% of hours and discharges in the most expensive 20%, within the same limits.

## Results

Backtest on 124 days of PJM-based hourly prices (the price series from the [battery arbitrage project](https://github.com/ekahorsu/battery-arbitrage-reinforcement-learning), modeled from real PJM East hourly demand), for a 20 MWh / 5 MW battery with 95% charging and discharging efficiency and a $2/MWh cycling cost:

| Method | Mean daily profit | Total over 124 days |
|--------|-------------------|---------------------|
| Optimal schedule (linear program) | **$158.80** | **$19,691** |
| Rule-based baseline | $86.06 | $10,671 |

The optimal schedule earns **85% more** than the rule-based baseline and comes out ahead on 99% of days. Reproduce with `python scripts/backtest.py`.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service status and version |
| POST | `/dispatch/optimal` | Optimal schedule from the linear program |
| POST | `/dispatch/rule-based` | Schedule from the rule-based baseline |
| POST | `/dispatch/compare` | Both schedules and the profit improvement |
| GET | `/docs` | Interactive documentation (try requests in the browser) |

Example request (`examples/sample_request.json`, one day of prices):

```bash
curl -X POST https://<your-cloud-run-url>/dispatch/compare \
  -H "Content-Type: application/json" \
  -d @examples/sample_request.json
```

Response (shortened):

```json
{
  "optimal_profit": 161.33,
  "rule_based_profit": 138.06,
  "improvement_pct": 16.9,
  "optimal": {
    "method": "linear_program",
    "energy_charged_mwh": 26.053,
    "energy_discharged_mwh": 23.513,
    "schedule": [{"period": 0, "price": 24.3, "charge_mw": 0.0, "discharge_mw": 0.0, "soc_mwh": 0.0}, "..."]
  }
}
```

Inputs are validated: prices must contain at least two values, battery ratings must be positive, and the state of charge cannot exceed the capacity. Invalid requests return HTTP 422 with a clear message.

## Engineering

- **Python package** with the optimization core (`app/optimizer.py`) separated from the API layer (`app/main.py`) and the request and response schemas (`app/schemas.py`, Pydantic).
- **Unit and API tests** (pytest, 14 tests): known optimal solutions, efficiency losses, cycling cost, power and energy limits, energy balance on random prices, the optimal schedule never losing to the baseline, and input validation.
- **Docker** image based on `python:3.12-slim`, running as a non-root user.
- **CI/CD with GitHub Actions** (`.github/workflows/ci-cd.yml`): every push and pull request runs the tests, builds the Docker image and smoke-tests the running container; every push to `main` that passes is deployed automatically to **Google Cloud Run** and checked with a live health request.

```
GitHub push ──► GitHub Actions: pytest ─► docker build ─► container smoke test
                                                   │
                                     (main branch only)
                                                   ▼
                     Cloud Build ─► Artifact Registry ─► Cloud Run (HTTPS endpoint)
```

## Run locally

```bash
git clone https://github.com/ekahorsu/battery-dispatch-api.git
cd battery-dispatch-api
pip install -r requirements-dev.txt
pytest -v
uvicorn app.main:app --reload        # then open http://localhost:8000/docs
```

With Docker:

```bash
docker build -t battery-dispatch-api .
docker run -p 8080:8080 battery-dispatch-api   # then open http://localhost:8080/docs
```

## Deploy

See [DEPLOY.md](DEPLOY.md) for the step-by-step Google Cloud Run setup, including the service account for automated deployment and cost safeguards.

## Repository contents

- `app/` - optimization core, API and schemas
- `tests/` - pytest suite
- `scripts/backtest.py` - multi-day comparison of the optimal and rule-based schedules
- `examples/sample_request.json` - one day of prices and a battery specification
- `Dockerfile`, `.dockerignore` - container image
- `.github/workflows/ci-cd.yml` - continuous integration and deployment
- `DEPLOY.md` - deployment guide

## Next steps

- Add ancillary service (reserve) bids and co-optimize energy and reserves
- Accept price forecasts with uncertainty and solve a stochastic or robust version of the model
- Connect the [PJM load forecasting model](https://github.com/ekahorsu/pjm-load-forecasting-chronos) as a price or load input
