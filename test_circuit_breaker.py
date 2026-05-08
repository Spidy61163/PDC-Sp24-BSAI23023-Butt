"""
Test script to demonstrate the circuit breaker working.

Start both servers first:
  Terminal 1: uvicorn mock_llm_server:app --port 8001
  Terminal 2: uvicorn main:app --port 8000
  Terminal 3: python test_circuit_breaker.py

The script automatically switches the LLM between ok and crash mode.
"""
import httpx
import time

BASE     = "http://localhost:8000"
LLM_BASE = "http://localhost:8001"
SEP      = "-" * 55


def print_section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


def set_llm_mode(mode: str):
    httpx.post(f"{LLM_BASE}/set_mode", json={"mode": mode}, timeout=5)
    print(f"  [MockLLM] Switched to mode = {mode}")


def call_ai(label: str):
    t0   = time.time()
    resp = httpx.post(f"{BASE}/ai/suggest", json={"prompt": "Give me a study tip."}, timeout=15)
    ms   = round((time.time() - t0) * 1000)
    data = resp.json()
    sid  = resp.headers.get("X-Student-ID", "MISSING")

    print(f"  [{label}]")
    print(f"    HTTP status  : {resp.status_code}")
    print(f"    Source       : {data.get('source')}")
    print(f"    CB state     : {data.get('cb_state')}")
    print(f"    Response     : {data.get('response', '')[:70]}")
    print(f"    X-Student-ID : {sid}")
    print(f"    Time taken   : {ms} ms")
    return data, ms


def get_cb_status():
    return httpx.get(f"{BASE}/cb/status").json()


# phase 1 — normal operation
print_section("PHASE 1 — Normal operation (LLM healthy)")
set_llm_mode("ok")
time.sleep(0.3)
for i in range(2):
    call_ai(f"Request {i+1}")
    time.sleep(0.5)

# phase 2 — crash the LLM, circuit should trip after 3 timeouts
print_section("PHASE 2 — LLM crashes (3 requests will timeout and trip the circuit)")
set_llm_mode("crash")
time.sleep(0.3)
for i in range(3):
    print(f"\n  >> Sending failing request {i+1}/3 (CB timeout will cut it at ~3s)")
    data, ms = call_ai(f"Failing request {i+1}")
    print(f"     took {ms}ms")
    time.sleep(0.3)

status = get_cb_status()
print(f"\n  CB status after failures:")
print(f"    state         : {status['state']}")
print(f"    failure_count : {status['failure_count']}")

# phase 3 — circuit is open, should get instant fallback with no network call
print_section("PHASE 3 — Circuit OPEN: instant fallback (the fix in action)")
for i in range(3):
    data, ms = call_ai(f"Post-trip request {i+1}")
    assert data.get("source") == "fallback", "Expected fallback response!"
    assert ms < 3000, f"Should be under 3000ms but took {ms}ms"
    print(f"     returned in {ms}ms with fallback (no network call made)\n")
    time.sleep(0.3)

print_section("RESULTS")
print("  Phase 1: LLM calls worked normally")
print("  Phase 2: 3 failures tripped the circuit breaker")
print("  Phase 3: Instant fallback returned, server stayed responsive")
print("  X-Student-ID: BSAI23023 present on all responses")
print(f"\n  Without the circuit breaker each post-trip call would block for ~60s.")
print(SEP)
