import time
import logging
import json
import os
import datetime
from fastapi import FastAPI, Response, Request
import joblib
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Phase 1/2: Per-Identity Rate Limiting
# In-memory fallback
request_history = {}
WINDOW_SECONDS = 10

# Redis connection
redis_host = os.environ.get("REDIS_HOST", "localhost")
try:
    r = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
    r.ping()
    logger.info("Connected to Redis for distributed rate limiting.")
except Exception as e:
    logger.warning(f"Could not connect to Redis: {e}")
    r = None

# Phase 3: ML Model
# Load trust_model at startup
model_path = os.path.join(os.path.dirname(__file__), 'trust_model.pkl')
try:
    trust_model = joblib.load(model_path)
    logger.info("Loaded ML trust model.")
except Exception as e:
    logger.warning(f"Could not load ML trust model, fallback to naive count: {e}")
    trust_model = None

# Phase 4: Logging setup
LOG_DIR = "/app/logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)
REQUESTS_LOG_FILE = os.path.join(LOG_DIR, "requests.log")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def authorize(request: Request, response: Response, path: str = ""):
    global request_history
    
    # PHASE 2: Identity from JWT
    jwt_claims_str = request.headers.get("x-forwarded-jwt-claims", "")
    caller_id = "unknown"
    if jwt_claims_str:
        try:
            claims = json.loads(jwt_claims_str)
            caller_id = claims.get("sub", "unknown")
        except json.JSONDecodeError:
            pass
            
    current_time = time.time()
    
    # Redis Sliding Window Rate Limiting
    request_rate = 1
    if r:
        try:
            pipeline = r.pipeline()
            # Remove timestamps older than WINDOW_SECONDS
            pipeline.zremrangebyscore(caller_id, 0, current_time - WINDOW_SECONDS)
            # Add current timestamp
            pipeline.zadd(caller_id, {str(current_time): current_time})
            # Count remaining timestamps
            pipeline.zcard(caller_id)
            # Set TTL so inactive keys expire (cleanup)
            pipeline.expire(caller_id, WINDOW_SECONDS + 1)
            results = pipeline.execute()
            request_rate = results[2]  # The result of zcard
        except Exception as e:
            logger.error(f"Redis error: {e}")
    else:
        # Fallback to in-memory
        timestamps = request_history.get(caller_id, [])
        timestamps = [ts for ts in timestamps if current_time - ts <= WINDOW_SECONDS]
        timestamps.append(current_time)
        request_history[caller_id] = timestamps
        request_rate = len(timestamps)
    
    # Compute features
    original_path = request.headers.get("x-envoy-original-path", request.url.path)
    is_sensitive = 1 if any(p in original_path.lower() for p in ["admin", "delete", "refund"]) else 0
    
    hour_of_day = datetime.datetime.now().hour
    
    trust_score = 1.0
    if trust_model:
        # LogisticRegression predict_proba expects 2D array
        # Returns [[prob_class_0, prob_class_1]]
        features = [[request_rate, is_sensitive, hour_of_day]]
        trust_score = trust_model.predict_proba(features)[0][1]
        
        if trust_score >= 0.5:
            route_to = "standard"
        else:
            route_to = "sandbox"
    else:
        # Fallback if model not loaded
        if request_rate > 5:
            route_to = "sandbox"
        else:
            route_to = "standard"

    logger.info(f"Caller: {caller_id} | Rate: {request_rate} | Sensitive: {is_sensitive} | Hour: {hour_of_day} | Score: {trust_score:.2f} | Routing to: {route_to}")
    
    response.headers["x-route-to"] = route_to
    response.headers["x-trust-score"] = f"{trust_score:.4f}"
    
    # PHASE 4: Log to JSON file for dashboard
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "caller_id": caller_id,
        "trust_score": float(trust_score),
        "route": route_to,
        "features": {
            "request_rate": request_rate,
            "is_sensitive": is_sensitive,
            "hour_of_day": hour_of_day
        }
    }
    try:
        with open(REQUESTS_LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to requests log: {e}")

    return {"status": "ok"}
