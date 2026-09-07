# Envoy Zero-Trust Intelligent Gateway

An edge gateway that replaces static rate limits with real ML-based trust scoring. Every request gets scored in real time and routed to either a normal backend or an isolated sandbox, depending on how suspicious it looks. Built on Envoy, FastAPI, scikit-learn, Redis, and the usual Prometheus/Grafana combo, all wired together with Docker Compose.

I put this together because static thresholds like "100 req/min" are trivial to get around with a slow enough attack. This does something smarter — it looks at request rate, endpoint sensitivity, and time of day, feeds those into a logistic regression model, and makes a routing decision per request.

## Contents

- [Why this exists](#why-this-exists)
- [Architecture](#architecture)
- [Stack](#stack)
- [Repo layout](#repo-layout)
- [Getting it running](#getting-it-running)
- [How a request actually flows through](#how-a-request-actually-flows-through)
- [The trust model](#the-trust-model)
- [Rate limiting with Redis](#rate-limiting-with-redis)
- [Circuit breakers](#circuit-breakers--retries)
- [Attack simulation](#attack-simulation)
- [Dashboards](#dashboards)
- [Config files, if you need to change something](#config-files)
- [Tearing it down](#tearing-it-down)

## Why this exists

Most rate limiters are static and stateless in the worst way — they don't care *who* you are or *what* you're hitting, just how fast you're hitting it. That's easy to route around. This project scores trust dynamically using three signals (request rate, whether the endpoint is sensitive, hour of day), and routes low-trust traffic into a sandboxed backend instead of just blocking it outright. That way you still get a response (useful for not tipping off an attacker) without exposing anything real.

It runs as seven containers under Docker Compose — Envoy in front, a FastAPI auth service doing the ML inference and rate-limit bookkeeping, Redis backing the sliding window counters, two Flask backends (standard + sandbox), and Prometheus/Grafana watching Envoy's metrics.

## Architecture

Requests come in through Envoy, which validates the JWT, then calls out to the auth service (`ext_authz`) before deciding where to route. The auth service checks Redis for the caller's recent request rate, runs the trust model, and hands back a routing header. Envoy re-evaluates the route based on that header (this requires `clear_route_cache: true` — more on that below) and sends the request on to either the standard backend or the sandbox.

```
Client → Envoy (JWT check) → ext_authz call → Auth Service
                                                   │
                                    Redis (rate)   │   Trust model (sklearn)
                                          └─────────┴─────────┘
                                                   │
                                          x-route-to: standard | sandbox
                                                   │
                                       Envoy re-routes accordingly
                                                   │
                                  ┌────────────────┴────────────────┐
                             Standard backend               Sandbox backend
                               (Flask, :5001)                 (Flask, :5002)
```

Prometheus scrapes Envoy's stats endpoint separately and Grafana visualizes it — that part runs independently of the request path.

### Containers

| Service | Port(s) | What it does |
|---|---|---|
| Envoy | 10000, 9901 (admin) | JWT validation, ext_authz, routing, circuit breakers |
| Auth service | 8000 | FastAPI — ML scoring, Redis rate limiting |
| Redis | 6379 | Sliding-window rate counters (sorted sets) |
| Standard backend | 5001 | Flask, serves trusted traffic |
| Sandbox backend | 5002 | Flask, isolated environment for suspicious traffic |
| Prometheus | 9090 | Scrapes Envoy metrics every 5s |
| Grafana | 3000 | Dashboards on top of Prometheus |

## Stack

Envoy 1.28, FastAPI + Uvicorn, scikit-learn (just logistic regression, nothing fancy), Redis, Flask for the two backends, Prometheus + Grafana for observability, PyJWT/cryptography for RS256 tokens, and Streamlit for the live decision dashboard. Everything's orchestrated with Docker Compose.

## Repo layout

```
envoy-zero-trust-gateway/
├── docker-compose.yml
├── envoy/
│   └── envoy.yaml              # JWT config, ext_authz, clusters, circuit breakers
├── auth-service/
│   ├── main.py                 # ML inference + Redis rate limiting
│   ├── trust_model.pkl
│   ├── requirements.txt
│   └── Dockerfile
├── backend/
│   ├── app.py                  # standard Flask backend
│   └── Dockerfile
├── sandbox-backend/
│   ├── app.py                  # sandbox Flask backend
│   └── Dockerfile
├── jwt-keys/
│   ├── private.pem
│   └── public.pem
├── prometheus/
│   └── prometheus.yml
├── grafana/
│   └── provisioning/
│       ├── datasources/datasource.yml
│       └── dashboards/
│           ├── dashboard.yml
│           └── envoy.json
├── web-dashboard/
│   └── index.html              # standalone HTML dashboard, no backend needed
├── train_model.py
├── generate_jwt.py
├── attack_simulation.py
└── dashboard.py                # Streamlit dashboard
```

## Getting it running

You'll need Docker + Docker Compose, and Python 3.9+ locally for the helper scripts (JWT generation, training, dashboards).

**1. Clone it**

```bash
git clone https://github.com/<your-username>/envoy-zero-trust-gateway.git
cd envoy-zero-trust-gateway
```

**2. Generate JWT keys**

```bash
python3 -m venv venv
source venv/bin/activate
pip install requests streamlit PyJWT cryptography pandas scikit-learn numpy joblib

python generate_jwt.py
```

This drops `private.pem` and `public.pem` into `jwt-keys/`. The public key's JWKS representation is already baked into `envoy/envoy.yaml` — if you regenerate the keys, you need to update that JWKS block by hand too, Envoy won't pick it up automatically.

**3. Train the trust model**

```bash
python train_model.py
```

Generates 300 synthetic samples (features: request rate, sensitive-endpoint flag, hour of day), trains a logistic regression classifier, prints accuracy on a held-out 20%, and saves the model to `auth-service/trust_model.pkl`.

Label logic, roughly: under 8 requests per window and a non-sensitive endpoint counts as trusted; anything with a high rate or a sensitive path counts as suspicious. There's about 10% label noise mixed in so the decision boundary isn't a clean step function.

**4. Bring up the stack**

```bash
docker compose up --build -d
```

Give it about 10 seconds, then check:

```bash
docker compose ps
```

You should see all seven containers up: envoy, auth-service, redis, backend, sandbox-backend, prometheus, grafana.

## How a request actually flows through

1. **Envoy validates the JWT** (RS256) — checks signature, issuer, audience. Bad token gets a 401 immediately, nothing downstream even sees it.
2. **Envoy calls the auth service** via `ext_authz`, forwarding the JWT claims as headers.
3. **Auth service checks Redis** for that identity's request rate — a pipelined `ZREMRANGEBYSCORE` / `ZADD` / `ZCARD` against a 10-second sliding window.
4. **Auth service runs the model** — `[request_rate, is_sensitive_endpoint, hour_of_day]` goes into `predict_proba()`, and the probability of "trusted" comes back as the trust score.
5. **Auth service responds** with an `x-route-to` header, either `standard` or `sandbox`, based on whether the score clears 0.5.
6. **Envoy re-routes** based on that header. This step only works because of `clear_route_cache: true` in the ext_authz filter config — without it, Envoy picks the route *before* the auth check finishes, and the header gets ignored.

## The trust model

Three features, nothing exotic:

- **Request rate** — pulled straight from Redis (`ZCARD` on the sliding window)
- **Sensitive endpoint** — 1 if the path contains `admin`, `delete`, or `refund`, else 0
- **Hour of day** — 0–23, from the system clock

Output is a trust score between 0 and 1. Score ≥ 0.5 goes to the standard backend, below that goes to sandbox. It's a simple model on purpose — the interesting part is the plumbing that lets Envoy make per-request routing decisions off of it, not the model itself.

## Rate limiting with Redis

```
ZREMRANGEBYSCORE <id> 0 <now - 10>   # drop anything outside the window
ZADD <id> <now> <now>                 # record this request
ZCARD <id>                            # this count is the request_rate feature
EXPIRE <id> 11                        # so idle keys don't hang around forever
```

All four run in a single Redis pipeline, so it's one round trip and atomic. No in-memory counters anywhere, which means you can scale the auth service horizontally without the rate limiting getting inconsistent between instances.

## Circuit breakers & retries

Each backend cluster in Envoy has:

```yaml
circuit_breakers:
  thresholds:
    - max_connections: 100
      max_pending_requests: 50
      max_requests: 100
      max_retries: 3

outlier_detection:
  consecutive_5xx: 3
  interval: 10s
  base_ejection_time: 30s
  max_ejection_percent: 50

retry_policy:
  retry_on: "5xx,connect-failure,reset"
  num_retries: 2
  per_try_timeout: 2s
```

Three consecutive 5xxs and a backend gets pulled out of the pool for 30 seconds. Nothing unusual here, just standard Envoy resilience config.

## Attack simulation

With containers up and the venv active:

```bash
python attack_simulation.py
```

It runs three scenarios against `localhost:10000`:

**Normal traffic** — `order-service` sends 5 requests, 1s apart. Trust score should stay around 0.7+, everything lands on the standard backend. Low rate, boring endpoint, no reason to be suspicious.

**Burst attack** — `suspicious-service` fires 15 requests back to back with no delay. Trust score drops as the rate climbs; somewhere around request 5-8 it crosses below 0.5 and starts getting sandboxed.

**Sensitive endpoint probe** — `order-service` hits `/admin` three times, 0.5s apart. Trust score falls off a cliff immediately (down around 0.1) since `is_sensitive_endpoint` is a strong signal on its own, regardless of rate.

Sample output looks something like:

```
SCENARIO 1: Normal Traffic
[order-service] / -> STANDARD | trust: 0.7234
[order-service] / -> STANDARD | trust: 0.7134
...

SCENARIO 2: Burst Attack
[suspicious-service] / -> STANDARD | trust: 0.6891
[suspicious-service] / -> STANDARD | trust: 0.6012
[suspicious-service] / -> SANDBOX  | trust: 0.4321
[suspicious-service] / -> SANDBOX  | trust: 0.2187
...

SCENARIO 3: Sensitive Endpoint Probe
[order-service] /admin -> SANDBOX | trust: 0.0923
[order-service] /admin -> SANDBOX | trust: 0.0812
...
```

## Dashboards

**Streamlit** (`streamlit run dashboard.py`) — reads the auth service's JSON logs and shows request counts, trust score over time per identity, and a recent-requests table. Refreshes every 2 seconds, opens at `localhost:8501`.

**Static HTML dashboard** (`web-dashboard/index.html`) — no backend needed, runs entirely client-side. Has five click-to-run attack scenarios built in, a live telemetry stream, a side-by-side comparison of static vs. ML-based limiting, and a circuit breaker simulator.

**Grafana** (`localhost:3000`, login `admin`/`admin`) — pre-provisioned with Prometheus as a data source and an Envoy dashboard covering request rates, connection pool usage, circuit breaker trips, and latency percentiles.

**Prometheus** (`localhost:9090`) — scrapes `envoy:9901/stats/prometheus` (note: not `/metrics`) every 5 seconds.

## Config files

| File | Purpose |
|---|---|
| `envoy/envoy.yaml` | Listener, JWT/JWKS, ext_authz filter, clusters, circuit breakers |
| `auth-service/main.py` | ML inference, Redis rate limiting, logging |
| `docker-compose.yml` | Service defs, ports, volumes, dependency ordering |
| `prometheus/prometheus.yml` | Scrape targets/intervals |
| `grafana/provisioning/datasources/datasource.yml` | Prometheus data source URL |
| `grafana/provisioning/dashboards/dashboard.yml` | Dashboard auto-provisioning |

The one environment variable worth knowing about: `REDIS_HOST` on the auth service, defaults to `localhost`, gets set to `redis` in the Compose file for container networking.

## Tearing it down

```bash
docker compose down
```

Add `--rmi all` if you want the built images gone too.

## Quick reference

```bash
# start everything
docker compose up --build -d

# generate a JWT for testing
python -c 'from generate_jwt import create_jwt; print(create_jwt("my-service"))'

# hit the gateway with an authenticated request
curl -H "Authorization: Bearer $(python -c 'from generate_jwt import create_jwt; print(create_jwt("test-user"))')" http://localhost:10000/

# run the attack simulation
python attack_simulation.py

# streamlit dashboard
streamlit run dashboard.py

# logs
docker compose logs -f auth-service
docker compose logs -f envoy

# retrain the model
python train_model.py

# teardown
docker compose down
```

---

Built with Envoy, FastAPI, scikit-learn, Redis, Prometheus, Grafana, and Docker Compose.
