# Envoy Zero-Trust Intelligent Gateway

A production-grade, ML-powered edge gateway that enforces zero-trust security, performs real-time threat detection using machine learning, and provides deep observability — all orchestrated with 8 Docker containers.

---

## Features

### Zero-Trust Security
- **JWT Authentication (RS256):** Envoy validates RSA-256 signed tokens at the edge. Invalid or missing tokens are rejected immediately with a 401 — the backend is never touched.
- **Per-Request Authorization:** Every single request is evaluated by the ML Auth Service before reaching any backend. There is no implicit trust.

### ML-Powered Threat Detection
- **Real-Time Trust Scoring:** A Scikit-Learn Logistic Regression model calculates a trust score (0.0 to 1.0) for every request using 3 features:
  - `request_rate` — number of requests from this identity in the last 10 seconds
  - `is_sensitive_endpoint` — whether the path contains keywords like `admin`, `delete`, or `refund`
  - `hour_of_day` — current hour to detect off-hours anomalies
- **Dynamic Routing:** Trusted users (score ≥ 0.5) are routed to the standard backend. Suspicious users (score < 0.5) are seamlessly redirected to an isolated sandbox — without dropping the connection.
- **Low-and-Slow Attack Detection:** Unlike static rate limiters, the ML model catches slow reconnaissance attacks that stay under fixed thresholds by correlating multiple behavioral signals.

### Distributed Rate Limiting (Redis)
- **Sliding Window Algorithm:** Uses Redis Sorted Sets (`ZADD`, `ZCARD`, `ZREMRANGEBYSCORE`, `EXPIRE`) to count requests per identity within a 10-second window.
- **Atomic Pipeline Execution:** All 4 Redis commands execute in a single pipeline (one network round-trip) for minimal latency.
- **In-Memory Fallback:** If Redis is unavailable, the service falls back to a local in-memory rate counter to maintain availability.

### Resilience & Fault Tolerance
- **Retry Policy:** Envoy automatically retries failed requests (5xx, connection failures, resets) up to 2 times with a 2-second per-try timeout. The client never sees transient failures.
- **Circuit Breakers:** Limits per cluster — max 100 connections, 50 pending requests, 100 concurrent requests, and 3 retries. Prevents cascading failures across services.
- **Outlier Detection:** If a backend returns 3 consecutive 5xx errors, Envoy ejects it from the load balancing pool for 30 seconds (up to 50% of hosts can be ejected).

### Deep Observability
- **Prometheus Metrics:** Scrapes Envoy's `/stats/prometheus` endpoint every 5 seconds. Collects request counts, latencies, error rates, and circuit breaker state.
- **Grafana Dashboards:** Auto-provisioned with 6 panels:
  - Traffic per Backend Cluster (req/sec)
  - ML Auth Service Latency P99 (ms)
  - Circuit Breaker — Active Connections per Cluster
  - Retries & Errors per Cluster
  - Outlier Detection — Ejections
  - Request Success Rate (%) Gauge
- **Jaeger Distributed Tracing:** Envoy generates OpenTelemetry trace spans for every request and exports them to Jaeger via gRPC. Visualizes the full request lifecycle as a waterfall timeline.
- **Streamlit Dashboard:** A Python-based live dashboard that reads the JSON decision logs and displays trust scores, routing decisions, and per-caller charts in real-time.

### Interactive Web Dashboard
- **Browser-Based Attack Simulator** (`web-dashboard/index.html`) with 5 pre-built scenarios:
  1. Legitimate Browsing — normal traffic, 5 requests
  2. Low-and-Slow Attack — under rate limit but hitting sensitive paths
  3. Brute-Force — 15 rapid requests
  4. Sensitive Endpoint Probe — `/admin`, `/delete`, `/refund`
  5. Canary Probe — borderline, mixed paths
- **Live Telemetry Stream** — real-time request log with trust scores, routes, and rates
- **Static vs ML Comparison** — side-by-side view showing how static rate limiters get bypassed while ML catches the attack
- **Circuit Breaker & Retry Simulation** — interactive scenarios for backend 503s, outlier ejection, and connection overload
- **Client Profiles Table** — per-identity stats including request count, average trust score, current route, and status

### Architecture Documentation
- **Interactive Architecture Page** (`architecture.html`) — a detailed, styled HTML document covering the request flow, all 8 containers, the ML model, resilience features, port summary, and technology stack.

---

## Architecture — 8 Containers

| Container | Port | Technology | Role |
|-----------|------|------------|------|
| **Envoy Proxy** | 10000, 9901 | Envoy v1.28 | Edge gateway — JWT validation, ext_authz, dynamic routing, retries, circuit breakers, tracing |
| **Auth Service** | 8000 | FastAPI + Scikit-Learn | ML trust scoring, per-request authorization, decision logging |
| **Redis** | 6379 | Redis Alpine | Distributed sliding-window rate limiting via Sorted Sets |
| **Standard Backend** | 5001 | Flask | Serves trusted users (trust score ≥ 0.5) |
| **Sandbox Backend** | 5002 | Flask | Isolated environment for suspicious users (trust score < 0.5) |
| **Prometheus** | 9090 | Prometheus | Metrics collection from Envoy's `/stats/prometheus` |
| **Grafana** | 3000 | Grafana | Auto-provisioned dashboards with 6 monitoring panels |
| **Jaeger** | 16686 | Jaeger | Distributed tracing via OpenTelemetry (OTLP gRPC on port 4317) |

---

## Request Flow

```
Client (with JWT)
    │
    ▼
┌──────────────────────────────┐
│  Envoy Proxy (:10000)        │
│  1. Validate JWT (RS256)     │──── Invalid → 401 Unauthorized
│  2. Forward to Auth Service  │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  ML Auth Service (:8000)     │
│  1. Extract caller identity  │
│  2. Query Redis for rate     │
│  3. Extract 3 ML features    │
│  4. Run model inference      │
│  5. Return trust score       │
└──────────┬───────────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
 Score ≥ 0.5  Score < 0.5
     │           │
     ▼           ▼
 Standard     Sandbox
 Backend      Backend
 (:5001)      (:5002)
```

---

## The ML Model

The trust model is a **Logistic Regression** classifier trained on 300 synthetic data points with 3 features:

| Feature | Low Value | High Value | Effect on Trust |
|---------|-----------|------------|-----------------|
| `request_rate` | 1-3 requests in 10s | 10+ requests in 10s | High rate → Lower trust |
| `is_sensitive_endpoint` | Normal path (`/`) | Dangerous path (`/admin`) | Sensitive → Much lower trust |
| `hour_of_day` | Business hours | Off hours | Minor effect |

The model is trained offline using `train_model.py` and saved as `trust_model.pkl`. Only **inference** happens during live traffic.

---

## Setup & Installation

Clone the repository and navigate to the project directory:
```bash
git clone https://github.com/PragyanVerma/Envoy-Zero-Trust-Gateway-Nutanix-.git
cd Envoy-Zero-Trust-Gateway-Nutanix-
```

Create a virtual environment and install the required local dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install requests streamlit PyJWT cryptography pandas scikit-learn numpy joblib
```

---

## Start the Infrastructure

Build and start all 8 containers:
```bash
docker compose up --build -d
```
*(Wait a few seconds for the containers to fully start.)*

---

## Usage

### Generate JWT Tokens
```bash
python generate_jwt.py
```
This generates signed RS256 JWT tokens for test identities (`order-service`, `payments-service`, `suspicious-service`).

### Send a Request Through the Gateway
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" http://localhost:10000/
```

### Run the Attack Simulation
Open a second terminal with the virtual environment activated:
```bash
cd Envoy-Zero-Trust-Gateway-Nutanix-
source venv/bin/activate
python attack_simulation.py
```

The simulation runs 3 scenarios:
1. **Normal Traffic** — 5 slow requests. Trust score stays high (~0.7), routed to STANDARD.
2. **Burst Attack** — 15 rapid requests. Trust score drops as rate increases, eventually routed to SANDBOX.
3. **Sensitive Endpoint Probe** — Requests to `/admin`. Trust score drops to ~0.1 immediately, forced into SANDBOX.

### Launch the Streamlit Dashboard
```bash
streamlit run dashboard.py
```
Displays live trust scores, routing decisions, and per-caller charts with auto-refresh.

### Open the Web Dashboard
Open `web-dashboard/index.html` in a browser to use the interactive attack simulator with live telemetry, circuit breaker simulations, and the Static vs ML comparison.

### Open the Architecture Page
Open `architecture.html` in a browser for a detailed visual overview of the system architecture, request flow, and all 8 containers.

---

## Monitoring & Observability

| Tool | URL | What It Shows |
|------|-----|---------------|
| **Grafana** | http://localhost:3000 | 6 auto-provisioned panels — traffic, latency, circuit breakers, retries, ejections, success rate |
| **Prometheus** | http://localhost:9090 | Raw Envoy metrics queries |
| **Jaeger** | http://localhost:16686 | Distributed trace waterfall for every request |
| **Envoy Admin** | http://localhost:9901 | Envoy internal stats, config, and cluster health |

---

## Retrain the ML Model

To regenerate the trust model with fresh synthetic data:
```bash
python train_model.py
```
This creates `auth-service/trust_model.pkl`. Rebuild the auth-service container afterward:
```bash
docker compose up --build auth-service -d
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Edge Proxy | Envoy Proxy v1.28 | Traffic management, JWT validation, dynamic routing, retries, circuit breakers |
| Auth / ML | FastAPI + Scikit-Learn | Real-time ML inference and per-request authorization |
| Identity | JWT (RS256) + PyJWT | Cryptographic authentication |
| Rate Limiting | Redis (Sorted Sets) | Distributed sliding-window rate limiting |
| Backends | Flask | Standard & Sandbox services |
| Metrics | Prometheus | Time-series metrics collection |
| Dashboards | Grafana + Streamlit | Enterprise monitoring & ML visualization |
| Tracing | Jaeger + OpenTelemetry | Distributed request tracing |
| Orchestration | Docker Compose | Multi-container orchestration |

---

## Project Structure

```
├── envoy/
│   └── envoy.yaml                    # Envoy proxy configuration
├── auth-service/
│   ├── main.py                       # ML Auth Service (FastAPI)
│   ├── trust_model.pkl               # Pre-trained ML model
│   ├── requirements.txt              # Python dependencies
│   └── Dockerfile
├── backend/
│   ├── app.py                        # Standard backend (Flask)
│   └── Dockerfile
├── sandbox-backend/
│   ├── app.py                        # Sandbox backend (Flask)
│   └── Dockerfile
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       │   ├── dashboard.yml         # Dashboard provisioning config
│       │   └── envoy.json            # 6-panel Grafana dashboard
│       └── datasources/
│           └── datasource.yml        # Prometheus datasource config
├── prometheus/
│   └── prometheus.yml                # Prometheus scrape config
├── jwt-keys/
│   ├── private.pem                   # RSA private key for signing JWTs
│   └── public.pem                    # RSA public key
├── web-dashboard/
│   └── index.html                    # Interactive browser-based dashboard
├── architecture.html                 # Architecture documentation page
├── docker-compose.yml                # 8-container orchestration
├── generate_jwt.py                   # JWT token generator
├── train_model.py                    # ML model training script
├── attack_simulation.py              # Traffic simulation script
├── dashboard.py                      # Streamlit live dashboard
└── README.md
```

---

## Teardown

```bash
docker compose down
```
