# FastAPI app (JWT verify, /chat stream -> RemoteGraph)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio, json


app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

# Minimal streaming endpoint to keep the plumbing honest.
# Later: verify Entra JWT then stream RemoteGraph deltas to Chainlit.
@app.post("/api/chat/stream")
async def stream_chat(req: Request):
    body = await req.json()
    text = (body.get("message") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")

    async def gen():
        for w in text.split():
            yield (w + " ").encode()
            await asyncio.sleep(0.03)
    return StreamingResponse(gen(), media_type="text/plain")

@app.post("/api/chat/invoke")
async def invoke_chat(req: Request):
    body = await req.json()
    text = (body.get("message") or "").strip()
    return JSONResponse({"echo": text, "note": "RemoteGraph coming soon"})