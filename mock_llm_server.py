"""
Fake LLM server to simulate the external API.
Mode can be switched at runtime by calling POST /set_mode {"mode": "ok"|"crash"|"flaky"}
The test script does this automatically so you don't have to restart anything.
"""
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock LLM Server")

request_count = 0
current_mode  = "ok"  # changed at runtime via /set_mode


@app.post("/set_mode")
async def set_mode(body: dict):
    global current_mode
    current_mode = body.get("mode", "ok")
    print(f"[MockLLM] Mode switched to: {current_mode}")
    return {"mode": current_mode}


@app.post("/llm")
async def mock_llm(request_body: dict):
    global request_count
    request_count += 1

    print(f"[MockLLM] Request #{request_count}, mode={current_mode}")

    if current_mode == "crash":
        print("[MockLLM] Simulating crash, sleeping 30s...")
        await asyncio.sleep(30)
        return JSONResponse({"response": "too late"})

    if current_mode == "flaky":
        if request_count % 3 != 0:
            print(f"[MockLLM] Flaky mode: failing request #{request_count}")
            await asyncio.sleep(30)

    prompt = request_body.get("prompt", "")
    return {"response": f"LLM answer for: '{prompt[:50]}'"}


@app.get("/health")
async def health():
    return {"status": "ok", "mode": current_mode}
