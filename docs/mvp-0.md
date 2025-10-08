
LangGraph **application structure**: graph modules, `langgraph.json` mapping, and Python deps. 

---

## Runtime configuration (cloud)

**Gateway env vars**

- `LANGGRAPH_URL` = LangGraph Cloud endpoint  
- `LANGGRAPH_GRAPH` = `chat`  
- `OPENAI_API_KEY` / `LANGSMITH_API_KEY` / `TAVILY_API_KEY` via **secretref**  
- `LANGSMITH_ENDPOINT=https://api.smith.langchain.com`, `LANGCHAIN_TRACING_V2=true`  
- `MODERATION_ENABLED=true`, `MODERATION_MODEL=omni-moderation-latest` (safety layer)

**Chainlit env vars**

- `GATEWAY_URL=https://<gateway-fqdn-or-custom-domain>`

Secret references and env var binding are configured on the Container Apps using Key Vault references (`keyvaultref:...,identityref:system`) and `secretref:` for environment usage. 

---

## How streaming works (end‑to‑end)

- **Gateway** calls `RemoteGraph(...).astream(..., stream_mode="messages")` and emits **SSE** frames (`data: <token>\n\n`) as tokens arrive.  
- **Chainlit** consumes `event:`/`data:` lines; tokens are appended with `msg.stream_token(...)` and finalized with `msg.update()`.  
- SSE messages use UTF‑8 and are delimited by a **blank line** per spec. 

---

## Safety & guardrails (enabled in MVP‑0)

We added **defense‑in‑depth**:

- **Input moderation** before calling the model; **Output moderation** after streaming; both use OpenAI’s **Moderation API** with `omni‑moderation‑latest`. 
- A **self‑harm crisis** safe‑completion route returns supportive language and resources (no instructions).  
- The gateway emits `event: policy` SSE when moderation intervenes; the UI shows a **“Safety notice”** banner.

OpenAI moderation docs & model page: see **Moderation guide** and the `omni‑moderation‑latest` model. 

> For production, keep building a small **LangSmith** safety eval set and tag traces so you can audit blocked/allowed decisions. 

---

## Local development

**Chainlit** (with a local gateway):

```bash
# In apps/chainlit-ui
chainlit run src/main.py
```

# Gateway:

## In apps/gateway-fastapi
- uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
- Ensure local env vars present (LANGGRAPH_URL, etc.), or point to a mock echo node.

## Cloud smoke tests

- curl -s https://<gateway-fqdn>/healthz

### SSE test (Windows):

```
curl.exe -N ^
  -H "Accept: text/event-stream" ^
  -H "Content-Type: application/json" ^
  -X POST "https://<gateway-fqdn>/api/chat/stream" ^
  --data "{\"message\":\"Write one sentence\"}"

```

## CI/CD summary

- Workflows authenticate with Azure Login using OIDC; images build server‑side in ACR; ACA revisions roll via az containerapp update.

- Alternative: the container‑apps‑deploy‑action also supports build + deploy in one step.

## Custom domain for the UI

- DNS (GoDaddy): CNAME chat → <app FQDN>, TXT asuid.chat → <verification id>.

- Bind with az containerapp hostname add/bind and request the managed certificate.

## Responsible AI mapping (what MVP‑0 already covers)

- Reliability & Safety: input/output moderation, crisis completions.

- Privacy & Security: Key Vault + Managed Identity (no secrets in code).

- Transparency & Accountability: show a “Safety notice”; LangSmith tracing for review.

## Known pitfalls & quick fixes

- ForbiddenByRbac when creating secret refs → assign Key Vault Secrets User to the app identity at the vault scope.

- Activating revision → check app logs; common causes are missing env vars or missing Python deps in pyproject.toml. ACA rolls a new revision on each image update.

- No stream visible → use curl.exe -N (Windows) to verify raw SSE framing; ensure gateway sends data: lines with \n\n separators.


