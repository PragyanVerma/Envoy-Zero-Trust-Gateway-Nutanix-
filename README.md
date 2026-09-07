# 🛡️ Envoy Zero-Trust Intelligent Gateway

> An ML-powered, production-grade edge gateway that enforces zero-trust security using real-time trust scoring, dynamic routing, distributed rate limiting, and full observability — built with Envoy, FastAPI, Scikit-Learn, Redis, Prometheus, Grafana, and Docker Compose.


<p align="center">
  <img src="architechture.png" alt="Envoy Zero-Trust Gateway Architecture" width="800"/>
</p>
<p align="center"><i>High-level architecture showing request flow through the Envoy Gateway, ML Auth Service, Redis, and dual backends with the Prometheus + Grafana observability stack.</i></p>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
  - [Step 1: Clone the Repository](#step-1-clone-the-repository)
  - [Step 2: Generate JWT Keys](#step-2-generate-jwt-keys)
  - [Step 3: Train the ML Model](#step-3-train-the-ml-model)
  - [Step 4: Start the Infrastructure](#step-4-start-the-infrastructure)
- [How It Works](#how-it-works)
  - [Request Lifecycle](#request-lifecycle)
  - [ML Trust Scoring](#ml-trust-scoring)
  - [Distributed Rate Limiting (Redis)](#distributed-rate-limiting-redis)
  - [Dynamic Routing](#dynamic-routing)
  - [Circuit Breakers & Retry Logic](#circuit-breakers--retry-logic)
- [Running the Attack Simulation](#running-the-attack-simulation)
- [Dashboards & Observability](#dashboards--observability)
  - [Streamlit Live Dashboard](#streamlit-live-dashboard)
  - [Web Dashboard (Static HTML)](#web-dashboard-static-html)
  - [Grafana (Envoy Metrics)](#grafana-envoy-metrics)
  - [Prometheus (Metrics Store)](#prometheus-metrics-store)
- [Configuration Reference](#configuration-reference)
- [Teardown](#teardown)

---

## Overview

Traditional rate limiters use static thresholds (e.g., "100 requests/min") that are easily bypassed by low-and-slow attacks. This project replaces that with an **ML-powered trust scoring engine** that evaluates every request in real time using multiple behavioral signals — request rate, endpoint sensitivity, and time of day — to dynamically route traffic between a **standard backend** (trusted) and an **isolated sandbox backend** (suspicious).

The entire system is containerized with **Docker Compose** and runs as **7 interconnected services**.

---

## Key Features

| Feature | Description |
|---|---|
| **JWT Authentication (RS256)** | Envoy validates every incoming JWT before any backend sees it. Identity (`sub` claim) is extracted and forwarded to the auth service. |
| **ML Trust Scoring** | A Logistic Regression model (Scikit-Learn) scores every request based on 3 features: request rate, endpoint sensitivity, and hour of day. |
| **Dynamic Routing** | Envoy's `ext_authz` filter + `clear_route_cache: true` enables per-request routing decisions — trusted traffic goes to the standard backend, suspicious traffic is sandboxed. |
| **Distributed Rate Limiting** | Redis Sorted Sets implement a sliding window rate counter per identity. No in-memory state — scales horizontally. |
| **Circuit Breakers** | Envoy enforces connection limits (`max_connections: 100`), pending request caps (`max_pending: 50`), and automatic retries on `5xx` and `connect-failure`. |
| **Outlier Detection** | 3 consecutive `5xx` responses eject a backend from the load balancing pool for 30 seconds. |
| **Live Dashboards** | Streamlit dashboard for ML decisions, a standalone HTML dashboard with attack simulation, and Grafana for Envoy proxy metrics. |

---

## Architecture

The system is composed of **7 Docker containers** that work together:

```
                         ┌──────────────────────────┐
                         │   Client / Attack Script  │
                         └────────────┬─────────────┘
                                      │ HTTP + JWT (RS256)
                                      ▼
                    ┌─────────────────────────────────────┐
                    │        Envoy Gateway (:10000)        │
                    │  JWT Validation → ext_authz → Route  │
                    │     Circuit Breakers · Retry Logic    │
                    └───┬──────────┬──────────┬───────────┘
                        │          │          │
                  ext_authz    Trusted    Suspicious
                   check      Traffic     Traffic
                        │          │          │
                        ▼          ▼          ▼
          ┌──────────────────┐ ┌────────┐ ┌────────┐
          │  Auth Service    │ │Standard│ │Sandbox │
          │  (FastAPI :8000) │ │Backend │ │Backend │
          │  ML Model +      │ │(Flask  │ │(Flask  │
          │  Rate Limiting   │ │ :5001) │ │ :5002) │
          └────────┬─────────┘ └────────┘ └────────┘
                   │
                   │ Sliding Window
                   ▼ (ZADD/ZCARD)
             ┌───────────┐
             │   Redis    │
             │  (:6379)   │
             └───────────┘

          ┌───────────────────────────────────────┐
          │          Observability Stack           │
          │  Prometheus (:9090) → Grafana (:3000)  │
          │  Scrapes /stats/prometheus from Envoy   │
          └───────────────────────────────────────┘
```

> 📸 **See the full architecture diagram above** ([architechture.png](architechture.png)) for a visual overview of the complete request flow.

### Container Summary

| # | Service | Port(s) | Role |
|---|---|---|---|
| 1 | **Envoy** | `10000`, `9901` (admin) | API Gateway — JWT validation, ext_authz, dynamic routing, circuit breakers |
| 2 | **Auth Service** | `8000` | FastAPI — ML trust scoring, Redis rate limiting, route decisions |
| 3 | **Redis** | `6379` | Distributed sliding window rate limiter (Sorted Sets) |
| 4 | **Standard Backend** | `5001` | Flask — serves trusted traffic |
| 5 | **Sandbox Backend** | `5002` | Flask — isolated environment for suspicious traffic |
| 6 | **Prometheus** | `9090` | Scrapes Envoy metrics from `/stats/prometheus` every 5s |
| 7 | **Grafana** | `3000` | Pre-provisioned dashboards for Envoy proxy metrics |

---

## Tech Stack

- **Envoy Proxy** `v1.28` — High-performance L7 proxy
- **FastAPI** + **Uvicorn** — Async Python auth service
- **Scikit-Learn** — Logistic Regression trust model
- **Redis Alpine** — Sorted Set-based sliding window rate limiting
- **Flask** — Lightweight backend services
- **Prometheus** — Time-series metrics collection
- **Grafana** — Metrics visualization
- **Docker Compose** — Container orchestration
- **Streamlit** — Live ML decision dashboard
- **PyJWT + Cryptography** — RS256 JWT generation

---

## Project Structure

```
envoy-zero-trust-gateway/
│
├── docker-compose.yml           # Orchestrates all 7 containers
│
├── envoy/
│   └── envoy.yaml               # Full Envoy config (JWT, ext_authz, clusters, circuit breakers)
│
├── auth-service/
│   ├── main.py                  # FastAPI auth service (ML inference + Redis rate limiting)
│   ├── trust_model.pkl          # Pre-trained Logistic Regression model
│   ├── requirements.txt         # Python dependencies (fastapi, scikit-learn, redis, etc.)
│   └── Dockerfile               # Container build config
│
├── backend/
│   ├── app.py                   # Standard Flask backend (trusted traffic)
│   └── Dockerfile
│
├── sandbox-backend/
│   ├── app.py                   # Sandbox Flask backend (suspicious traffic)
│   └── Dockerfile
│
├── jwt-keys/
│   ├── private.pem              # RSA private key (RS256 signing)
│   └── public.pem               # RSA public key (JWT validation)
│
├── prometheus/
│   └── prometheus.yml           # Scrape config (Envoy :9901/stats/prometheus)
│
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── datasource.yml   # Auto-provisions Prometheus as data source
│       └── dashboards/
│           ├── dashboard.yml    # Dashboard provisioning config
│           └── envoy.json       # Pre-built Envoy metrics dashboard
│
├── web-dashboard/
│   └── index.html               # Standalone HTML dashboard with live attack simulator
│
├── train_model.py               # Script to train the Logistic Regression trust model
├── generate_jwt.py              # Script to generate RSA keys & signed JWTs
├── attack_simulation.py         # Script to simulate 3 attack scenarios against the gateway
├── dashboard.py                 # Streamlit live dashboard (reads auth-service logs)
│
└── architechture.png            # Architecture diagram
```

---

## Prerequisites

- **Docker** & **Docker Compose** installed and running
- **Python 3.9+** (for local scripts: JWT generation, ML training, dashboards)
- **pip** (Python package manager)

---

## Setup & Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/<your-username>/envoy-zero-trust-gateway.git
cd envoy-zero-trust-gateway
```

### Step 2: Generate JWT Keys

Create a Python virtual environment and generate the RSA key pair used for JWT signing and validation:

```bash
python3 -m venv venv
source venv/bin/activate

# Install local dependencies
pip install requests streamlit PyJWT cryptography pandas scikit-learn numpy joblib

# Generate RSA key pair (creates jwt-keys/private.pem & public.pem)
python generate_jwt.py
```

This generates:
- `jwt-keys/private.pem` — Used by the simulation scripts to sign JWTs
- `jwt-keys/public.pem` — The corresponding public key (JWKS is embedded in `envoy.yaml`)

> **Note:** The JWKS (JSON Web Key Set) representation of the public key is already embedded inline in `envoy/envoy.yaml`. If you regenerate keys, you must update the JWKS in the Envoy config.

### Step 3: Train the ML Model

```bash
python train_model.py
```

This script:
1. Generates **300 synthetic training samples** with features: `request_rate`, `is_sensitive_endpoint`, `hour_of_day`
2. Trains a **Logistic Regression** classifier (label: 1 = trusted, 0 = suspicious)
3. Reports accuracy on a 20% test split
4. Saves the model to `auth-service/trust_model.pkl`

**Label logic:**
- **Trusted (1):** Request rate < 8/window AND not a sensitive endpoint
- **Suspicious (0):** High request rate OR sensitive endpoint
- ~10% noise is injected for realistic decision boundaries

### Step 4: Start the Infrastructure

```bash
docker compose up --build -d
```

Wait ~10 seconds for all 7 containers to fully initialize. Verify with:

```bash
docker compose ps
```

You should see all services running:
| Service | Status | Ports |
|---|---|---|
| envoy | Running | `10000`, `9901` |
| auth-service | Running | `8000` |
| redis | Running | `6379` |
| backend | Running | `5001` |
| sandbox-backend | Running | `5002` |
| prometheus | Running | `9090` |
| grafana | Running | `3000` |

---

## How It Works

### Request Lifecycle

Every incoming request flows through the following pipeline:

```
Client sends HTTP request with JWT Bearer token
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │ 1. ENVOY: JWT Validation (RS256)             │
   │    - Validates signature, issuer, audience    │
   │    - Extracts payload into metadata           │
   │    - Rejects invalid tokens with 401          │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │ 2. ENVOY → AUTH SERVICE: ext_authz check     │
   │    - Forwards JWT claims via header           │
   │    - Auth service extracts caller identity    │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │ 3. AUTH SERVICE: Rate Limiting (Redis)       │
   │    - ZREMRANGEBYSCORE: remove old timestamps  │
   │    - ZADD: add current timestamp              │
   │    - ZCARD: count requests in window          │
   │    - Sliding window = 10 seconds              │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │ 4. AUTH SERVICE: ML Inference                 │
   │    - Features: [request_rate, is_sensitive,   │
   │      hour_of_day]                             │
   │    - LogisticRegression.predict_proba()       │
   │    - trust_score = P(trusted)                 │
   │    - Route = "standard" if ≥ 0.5 else         │
   │      "sandbox"                                │
   └──────────────────┬──────────────────────────┘
                      ▼
   ┌─────────────────────────────────────────────┐
   │ 5. ENVOY: Dynamic Route Decision             │
   │    - Reads x-route-to header from auth resp   │
   │    - clear_route_cache: true re-evaluates     │
   │      route AFTER auth response                │
   │    - Routes to backend_service or             │
   │      sandbox_backend cluster                  │
   └──────────────────┬──────────────────────────┘
                      ▼
          ┌──────────────────────┐
          │ Standard Backend     │  ← if trust_score ≥ 0.5
          │   OR                 │
          │ Sandbox Backend      │  ← if trust_score < 0.5
          └──────────────────────┘
```

### ML Trust Scoring

The auth service uses a **Logistic Regression** model with 3 input features:

| Feature | Source | Description |
|---|---|---|
| `request_rate` | Redis `ZCARD` | Number of requests from this identity in the last 10s |
| `is_sensitive_endpoint` | URL path parsing | `1` if path contains `admin`, `delete`, or `refund`; `0` otherwise |
| `hour_of_day` | System clock | Current hour (0–23) |

**Output:** `trust_score` = probability of class 1 (trusted), ranging from 0.0 to 1.0.

**Routing threshold:** `trust_score ≥ 0.5` → Standard Backend, `trust_score < 0.5` → Sandbox Backend.

### Distributed Rate Limiting (Redis)

Rate limiting uses **Redis Sorted Sets** to implement a per-identity sliding window:

```
ZREMRANGEBYSCORE <caller_id> 0 <current_time - 10>    # Remove expired entries
ZADD <caller_id> <current_time> <current_time>         # Add current request
ZCARD <caller_id>                                       # Count = request_rate
EXPIRE <caller_id> 11                                   # Auto-cleanup for idle keys
```

All 4 commands execute in a single **Redis pipeline** (atomic, single round-trip).

### Dynamic Routing

Envoy's routing is controlled by the `x-route-to` response header from the auth service:

- **`x-route-to: standard`** → Routes to `backend_service` cluster (Flask on port 5001)
- **`x-route-to: sandbox`** → Routes to `sandbox_backend` cluster (Flask on port 5002)

> **Critical:** `clear_route_cache: true` in the ext_authz config is **required**. Without it, Envoy caches the route decision _before_ the auth service responds, making dynamic routing impossible.

### Circuit Breakers & Retry Logic

Each backend cluster in Envoy is configured with:

```yaml
circuit_breakers:
  thresholds:
    - max_connections: 100        # Max concurrent connections
      max_pending_requests: 50    # Max queued requests
      max_requests: 100           # Max active requests
      max_retries: 3              # Max concurrent retries

outlier_detection:
  consecutive_5xx: 3              # Eject after 3 consecutive 5xx
  interval: 10s                   # Check interval
  base_ejection_time: 30s         # Ejection duration
  max_ejection_percent: 50        # Max % of hosts ejected

retry_policy:
  retry_on: "5xx,connect-failure,reset"
  num_retries: 2
  per_try_timeout: 2s
```

---

## Running the Attack Simulation

With the virtual environment activated and all containers running:

```bash
source venv/bin/activate
python attack_simulation.py
```

### Simulation Scenarios

The script runs **3 automated attack scenarios** against `http://localhost:10000`:

#### Scenario 1: Normal Traffic
- **Identity:** `order-service`
- **Behavior:** 5 requests with 1-second delays
- **Expected:** Trust score stays high (~0.7+), all requests routed to **STANDARD** backend
- **Why:** Low request rate + non-sensitive path = trusted

#### Scenario 2: Burst Attack
- **Identity:** `suspicious-service`
- **Behavior:** 15 rapid-fire requests with no delay
- **Expected:** Trust score drops progressively as request rate climbs. After ~5-8 requests, crosses the 0.5 threshold and routes to **SANDBOX**
- **Why:** High request rate within 10s window triggers ML model's suspicion

#### Scenario 3: Sensitive Endpoint Probe
- **Identity:** `order-service`
- **Behavior:** 3 requests to `/admin` with 0.5s delay
- **Expected:** Trust score drops immediately to ~0.1, all requests routed to **SANDBOX**
- **Why:** `is_sensitive_endpoint = 1` is a strong negative signal in the model

### Sample Output

```
==================================================
SCENARIO 1: Normal Traffic
==================================================
[order-service] / -> Route: STANDARD | Trust Score: 0.7234
[order-service] / -> Route: STANDARD | Trust Score: 0.7134
...

==================================================
SCENARIO 2: Burst Attack
==================================================
[suspicious-service] / -> Route: STANDARD | Trust Score: 0.6891
[suspicious-service] / -> Route: STANDARD | Trust Score: 0.6012
[suspicious-service] / -> Route: SANDBOX  | Trust Score: 0.4321
[suspicious-service] / -> Route: SANDBOX  | Trust Score: 0.2187
...

==================================================
SCENARIO 3: Sensitive Endpoint Probe
==================================================
[order-service] /admin -> Route: SANDBOX | Trust Score: 0.0923
[order-service] /admin -> Route: SANDBOX | Trust Score: 0.0812
...
```

---

## Dashboards & Observability

### Streamlit Live Dashboard

A real-time dashboard that reads the auth-service's JSON log file and visualizes ML trust scores:

```bash
source venv/bin/activate
streamlit run dashboard.py
```

**Features:**
- Total requests, standard vs. sandboxed counts
- Trust score over time (line chart, per caller identity)
- Recent requests table with full details
- Auto-refreshes every 2 seconds

> **Access:** Opens automatically in your browser (default: `http://localhost:8501`)

### Web Dashboard (Static HTML)

A standalone, zero-dependency HTML dashboard with a built-in attack simulator:

```bash
open web-dashboard/index.html
```

**Features:**
- 5 pre-built attack scenarios (click-to-run)
- Live telemetry stream showing every request
- Static vs. ML rate limiter comparison panel
- Circuit breaker & retry simulation
- Client identity profile table
- All logic runs in-browser (no backend required)

### Grafana (Envoy Metrics)

Pre-provisioned with a Prometheus data source and Envoy dashboard:

> **Access:** [http://localhost:3000](http://localhost:3000) (default login: `admin` / `admin`)

**Monitors:**
- Envoy upstream/downstream request rates
- Connection pool utilization
- Circuit breaker trip events
- Response latency percentiles

### Prometheus (Metrics Store)

Scrapes Envoy's admin endpoint every 5 seconds:

> **Access:** [http://localhost:9090](http://localhost:9090)

**Config:** Scrapes `envoy:9901/stats/prometheus` (not `/metrics`)

---

## Configuration Reference

| Config File | Purpose |
|---|---|
| [`envoy/envoy.yaml`](envoy/envoy.yaml) | Envoy listener, JWT validation (inline JWKS), ext_authz filter, cluster definitions, circuit breakers, outlier detection |
| [`auth-service/main.py`](auth-service/main.py) | FastAPI auth handler, ML inference, Redis rate limiting, JSON logging |
| [`docker-compose.yml`](docker-compose.yml) | Service definitions, port mappings, volume mounts, dependency graph |
| [`prometheus/prometheus.yml`](prometheus/prometheus.yml) | Scrape targets and intervals |
| [`grafana/provisioning/datasources/datasource.yml`](grafana/provisioning/datasources/datasource.yml) | Prometheus data source URL |
| [`grafana/provisioning/dashboards/dashboard.yml`](grafana/provisioning/dashboards/dashboard.yml) | Dashboard auto-provisioning config |

### Key Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `REDIS_HOST` | auth-service | `localhost` | Redis hostname (set to `redis` in Docker) |

---

## Teardown

Stop and remove all containers:

```bash
docker compose down
```

To also remove built images:

```bash
docker compose down --rmi all
```

---

## Quick Reference

```bash
# Start everything
docker compose up --build -d

# Generate a JWT for testing
python -c 'from generate_jwt import create_jwt; print(create_jwt("my-service"))'

# Send a single authenticated request
curl -H "Authorization: Bearer $(python -c 'from generate_jwt import create_jwt; print(create_jwt("test-user"))')" http://localhost:10000/

# Run attack simulation
python attack_simulation.py

# Launch Streamlit dashboard
streamlit run dashboard.py

# Check container logs
docker compose logs -f auth-service
docker compose logs -f envoy

# Retrain ML model
python train_model.py

# Teardown
docker compose down
```

---

<p align="center">
  <b>Built with</b> Envoy · FastAPI · Scikit-Learn · Redis · Prometheus · Grafana · Docker Compose
</p>
