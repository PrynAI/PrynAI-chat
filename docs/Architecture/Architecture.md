# End-to-End (Single Region, pgvector)

# PrynAI Chat — End‑to‑End Architecture (Single Region, PGVector Memory)

## Overview
  ### Goal:
  - Multi‑tenant, low‑latency chat app (Chainlit UI) with auth via Microsoft Entra External ID (CIAM), API Gateway, and a LangGraph‑hosted agent.

### High‑level:
- Browser (MSAL SPA) → Chainlit UI → Gateway (FastAPI) → LangGraph RemoteGraph → OpenAI (Responses + tools) + LangGraph Store (pgvector).

## Components

- ### Chainlit UI (ca-chainlit)
    - FastAPI server mounting Chainlit at /chat and static /auth SPA.
    - MSAL SPA: loginRedirect + handleRedirectPromise + acquireTokenSilent, posts to /_auth/token (HttpOnly cookie). Logout with logoutRedirect.
    - Chainlit header_auth_callback consumes cookie/Authorization header to create a session. 
    - Proxies /ui/* to Gateway for thread CRUD and utilities.
    - Web‑search toggle in Chat Settings (default off).
    - SSE client renders streamed tokens.

- ### Gateway (ca-gateway)
    - #### Auth:
        - Validates Bearer JWT (OIDC discovery + JWKS). Stores no secrets in browser storage beyond HttpOnly cookie
    - #### Chat streaming:
        - POST /api/chat/stream (SSE), POST /api/chat/stream_files (multipart + SSE).
        - Pre‑invoke input moderation; post‑stream output moderation (best‑effort).
        - Writes transcripts (user then assistant) to Store per thread.
        - Streams text/event-stream with spec‑compliant framing
    - #### Threads API:
       -  create/list/get/rename/delete with soft‑delete fallback.
    - #### Profile API:
       -  ensure/read/write user profile & settings.

 - ### Agent (LangGraph RemoteGraph: chat)
    - #### Web‑search feature flag:
       -  when enabled, LLM is bound to the OpenAI built‑in web_search tool using Responses API; can force a call on time‑sensitive queries.
    - #### Long‑term memory:
       - Retrieve: semantic search from LangGraph Store (pgvector) using an index declared in langgraph.json.
       - Write: (a) short durable “user” memories (structured extraction), (b) a 1‑line episodic summary after each turn.
   - #### Model:
       - OpenAI model via Responses API; temperature and reasoning profile tuned in code.
- ### Storage
   - #### LangGraph Store (Postgres + pgvector);
      -  vector index configured in deployment (embedding model + dims).
   - #### Namespaces:
      - ["users", <user_id>] → profile (settings).
      - ("users", <user_id>, "memories", "user" | "episodic") → memory items.
      - ["threads", <user_id>, <thread_id>] → transcript.
- ### Uploads
     - #### File limits:
        - count, bytes, extensions. Optional OCR. Converts to semantic context; never executes code/content.
      
## Request flows:
  ### Auth (SPA redirect) :
  - Browser → Entra (MSAL redirect) → returns tokens → SPA POSTs / _auth/token → Chainlit header auth → UI ready.
  ### Chat streaming (SSE)
  - UI → Gateway /api/chat/stream → RemoteGraph → Agent → (Store search, OpenAI, optional web_search) → stream back tokens → transcript write.
  ### Uploads
  - UI → Gateway /api/chat/stream_files (multipart) → extract → add ATTACHMENTS CONTEXT → same streaming path.
     
