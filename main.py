import time
import asyncio
import httpx
from enum import Enum
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# This middleware adds the required X-Student-ID header to every response
class StudentIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Student-ID"] = "BSAI23023"
        return response


# Three states the circuit breaker can be in
class CBState(Enum):
    CLOSED    = "CLOSED"     # working normally
    OPEN      = "OPEN"       # too many failures, blocking calls
    HALF_OPEN = "HALF_OPEN"  # cooldown done, testing if service is back


class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=10, timeout_seconds=3.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.timeout_seconds   = timeout_seconds
        self.state             = CBState.CLOSED
        self.failure_count     = 0
        self.last_failure_time = 0.0

    def _should_attempt(self):
        if self.state == CBState.CLOSED:
            return True
        if self.state == CBState.OPEN:
            # check if enough time has passed to try again
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CBState.HALF_OPEN
                print("[CB] Cooldown done, moving to HALF_OPEN")
                return True
            return False
        # HALF_OPEN allows one trial request through
        return True

    def _on_success(self):
        self.failure_count = 0
        self.state         = CBState.CLOSED
        print("[CB] Call succeeded, back to CLOSED")

    def _on_failure(self):
        self.failure_count    += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold or self.state == CBState.HALF_OPEN:
            self.state = CBState.OPEN
            print(f"[CB] {self.failure_count} failures hit, circuit is now OPEN")
        else:
            print(f"[CB] Failure {self.failure_count}/{self.failure_threshold}")

    async def call(self, coro):
        if not self._should_attempt():
            raise CircuitOpenError("Circuit is OPEN")
        try:
            result = await asyncio.wait_for(coro, timeout=self.timeout_seconds)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e


class CircuitOpenError(Exception):
    pass


app = FastAPI(title="StudySync API")
app.add_middleware(StudentIDMiddleware)

# one circuit breaker instance shared across all requests to the LLM
llm_cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10, timeout_seconds=3.0)


async def call_llm_api(prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8001/llm",
            json={"prompt": prompt},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["response"]


@app.get("/")
async def root():
    return {"message": "StudySync API running", "student_id": "BSAI23023"}


@app.get("/cb/status")
async def cb_status():
    return {
        "state":         llm_cb.state.value,
        "failure_count": llm_cb.failure_count,
        "threshold":     llm_cb.failure_threshold,
        "recovery_in_s": max(
            0,
            round(llm_cb.recovery_timeout - (time.time() - llm_cb.last_failure_time), 1)
        ) if llm_cb.state == CBState.OPEN else 0,
    }


@app.post("/ai/suggest")
async def ai_suggest(request: Request):
    body   = await request.json()
    prompt = body.get("prompt", "Give me a study tip.")

    try:
        answer = await llm_cb.call(call_llm_api(prompt))
        return {
            "source":   "llm",
            "response": answer,
            "cb_state": llm_cb.state.value,
        }

    except CircuitOpenError:
        # circuit is open so we skip the network call entirely and return a fallback
        return JSONResponse(status_code=200, content={
            "source":   "fallback",
            "response": "AI suggestions are temporarily unavailable. Try: review your notes for 25 minutes, then take a 5-minute break (Pomodoro technique).",
            "cb_state": llm_cb.state.value,
        })

    except (asyncio.TimeoutError, httpx.TimeoutException):
        return JSONResponse(status_code=503, content={
            "source":   "fallback",
            "response": "Request timed out. Fallback: break your topic into smaller subtopics and tackle one at a time.",
            "cb_state": llm_cb.state.value,
        })

    except Exception as exc:
        return JSONResponse(status_code=503, content={
            "source":   "fallback",
            "response": "AI service is down. Fallback: use spaced repetition — review material at 1 day, 3 days, and 7 days intervals.",
            "cb_state": llm_cb.state.value,
            "detail":   str(exc),
        })
