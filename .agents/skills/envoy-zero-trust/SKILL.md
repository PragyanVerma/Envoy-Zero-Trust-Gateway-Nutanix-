---
name: envoy-zero-trust-context
description: >-
  Use this skill to understand the architecture, components, and current state of the Envoy Zero-Trust Intelligent Gateway hackathon project. Activate this when the user asks to modify, extend, or explain the gateway.
---

# Envoy Zero-Trust Intelligent Gateway - Context

This project is an ML-powered, production-grade edge gateway that manages traffic, enforces security, and provides deep observability.

## Architecture & Components (8 Containers)
- **envoy (Port 10000/9901)**: The main entry point. Handles JWT validation (RS256), dynamic routing via ext_authz (`clear_route_cache: true`), circuit breakers, and OpenTelemetry tracing.
- **auth-service (Port 8000)**: FastAPI app. Reads JWT claims, queries Redis for rate limits, runs Scikit-Learn `trust_model.pkl` inference, and returns route decisions (standard vs sandbox).
- **redis (Port 6379)**: Distributed rate limiting using Sorted Sets (ZADD, ZCARD, ZREMRANGEBYSCORE) for a sliding window.
- **backend (Port 5001)**: Standard Flask backend for trusted traffic.
- **sandbox-backend (Port 5002)**: Isolated Flask backend for suspicious traffic.
- **prometheus (Port 9090)**: Scrapes Envoy metrics from `/stats/prometheus`.
- **grafana (Port 3000)**: Visualizes traffic, ML latency, and circuit breaker status.
- **jaeger (Port 16686)**: Visualizes OpenTelemetry distributed tracing from Envoy.

## Critical Configuration Rules
- **Envoy ext_authz**: `clear_route_cache: true` is strictly required. Without it, Envoy will cache routes before the auth service can change the routing headers.
- **Prometheus Scrape**: Envoy exports metrics at `/stats/prometheus`, not `/metrics`.
- **JWT Keys**: Public/private keys are stored in `jwt-keys/`. The Envoy config contains a JWKS representation of the public key.

## Helpful Commands
- **Rebuild and Start**: `docker compose up --build -d`
- **Generate Traffic / Test ML Routing**: `python attack_simulation.py` (Must be run inside virtual environment `venv/bin/activate`)
- **Generate JWT**: `python -c 'from generate_jwt import create_jwt; print(create_jwt("user-name"))'`

## Development Workflow
When the user asks to add a new feature, always consider how it fits into the Zero-Trust constraints, how it scales (e.g., use Redis instead of RAM), and if it can be monitored (add Grafana panels).
