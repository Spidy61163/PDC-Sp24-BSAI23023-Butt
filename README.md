Sameer Butt — BSAI23023

# PDC-Sp24-BSAI23023-Butt

**Course:** Parallel and Distributed Computing (PDC)
**Assignment:** Building Resilient Distributed Systems — Part 3
**Problem solved:** Fault Tolerance via Circuit Breaker Pattern

---

## What this implements

A FastAPI application that wraps an external LLM API call with a **Circuit Breaker**.
Without the fix, a slow/crashed LLM blocks the server for up to 60 seconds per request.
With the fix, after 3 failures the circuit trips to OPEN and all subsequent calls return
an instant fallback response — the server stays fully responsive.

**States:**
- `CLOSED` → normal operation, calls go through
- `OPEN` → tripped, instant fallback returned, no network call made
- `HALF_OPEN` → after cooldown, one trial call allowed to test recovery

Every API response includes the required header: `X-Student-ID: BSAI23023`

---

## How to run

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the mock LLM server (Terminal 1)

Normal mode (LLM healthy):
```bash
LLM_MODE=ok uvicorn mock_llm_server:app --port 8001
```

Crash mode (LLM times out — simulates the bug):
```bash
LLM_MODE=crash uvicorn mock_llm_server:app --port 8001 --reload
```

### 3. Start the main API server (Terminal 2)
```bash
uvicorn main:app --port 8000 --reload
```

### 4. Run the automated test (Terminal 3)
```bash
python test_circuit_breaker.py
```

---

## Manual demo endpoints

| Endpoint | Description |
|---|---|
| `GET  /` | Health check |
| `GET  /cb/status` | Current circuit breaker state |
| `POST /ai/suggest` | LLM call protected by circuit breaker |

Example:
```bash
curl -s -X POST http://localhost:8000/ai/suggest \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Give me a study tip"}' | python -m json.tool

# Check the header too:
curl -I http://localhost:8000/
```

---

## Demo script for video

1. Start mock LLM in **normal mode** → show `/ai/suggest` returning real responses
2. Restart mock LLM in **crash mode** (`LLM_MODE=crash`)
3. Send 3 requests → watch them timeout and trip the circuit (`cb_state: OPEN`)
4. Send more requests → show **instant fallback** (< 100ms), server not blocked
5. Check `/cb/status` → confirms state is `OPEN`
6. Wait 10 seconds → state moves to `HALF_OPEN`, one trial goes through
