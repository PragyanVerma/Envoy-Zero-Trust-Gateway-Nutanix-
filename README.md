# Envoy ML-based Rate Limiter

This project demonstrates a dynamic, ML-powered rate limiter and routing engine using Envoy, FastAPI, and Scikit-Learn.

## Features
- **JWT Authentication:** Envoy intercepts requests and validates JWTs before they reach any backend service.
- **ML Trust Scoring:** An authorization service (`auth-service`) uses a trained scikit-learn Logistic Regression model to assign a `trust_score` to every request based on request rate, time of day, and sensitivity of the path.
- **Dynamic Routing:** If a user's trust score drops below `0.5`, Envoy seamlessly routes their requests to a rate-limited sandbox backend without dropping the connection.
- **Live Dashboard:** A Streamlit dashboard visualizes the ML decisions in real-time.

---

## 1. Setup & Installation

Clone the repository and navigate to the project directory:
```bash
git clone https://github.com/PragyanVerma/Envoy-Zero-Trust-Gateway-Nutanix-.git
cd Envoy-Zero-Trust-Gateway-Nutanix-
```

Create a virtual environment and install the required local dependencies for the dashboard and simulation scripts:
```bash
python3 -m venv venv
source venv/bin/activate
pip install requests streamlit PyJWT cryptography pandas scikit-learn numpy joblib
```

---

## 2. Start the Infrastructure

Run Docker Compose to build and start the Envoy proxy, standard backend, sandbox backend, and the ML auth service:
```bash
docker compose up --build -d
```
*(Wait a few seconds for the containers to fully start).*

---

## 3. Launch the Live Dashboard

In the same terminal (with the virtual environment activated), start the Streamlit dashboard:
```bash
streamlit run dashboard.py
```
This will automatically open a browser window displaying the live metrics and charts.

---

## 4. Run the Attack Simulation

Open a **second terminal** window, navigate to the project, activate the virtual environment, and run the simulation script to generate traffic:

```bash
cd Envoy-Zero-Trust-Gateway-Nutanix-
source venv/bin/activate
python attack_simulation.py
```

### What happens during the simulation?
The script tests 3 scenarios:
1. **Normal Traffic:** 5 slow requests. The ML model keeps the trust score high (~0.7) and routes them to the STANDARD backend.
2. **Burst Attack:** 15 rapid requests from a suspicious identity. The trust score drops quickly as the rate increases, eventually crossing the `0.5` threshold and being dynamically routed to the SANDBOX.
3. **Sensitive Endpoint Probe:** A user attempts to access `/admin`. The ML model immediately recognizes this as a highly sensitive action and drops their trust score to `~0.1`, forcing them into the sandbox instantly.

**Watch your Streamlit dashboard** as you run this script to see the trust scores drop and route decisions change in real-time!

---

## 5. Teardown
When you are finished, you can stop the project by running:
```bash
docker compose down
```
