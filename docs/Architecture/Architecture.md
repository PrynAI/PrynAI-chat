# End-to-End (Single Region, pgvector)

# PrynAI Chat — End‑to‑End Architecture (Single Region, PGVector Memory)

## Overview
  ### Goal:
  - Multi‑tenant, low‑latency chat app (Chainlit UI) with auth via Microsoft Entra External ID (CIAM), API Gateway, and a LangGraph‑hosted agent.

### High‑level:
- Browser (MSAL SPA) → Chainlit UI → Gateway (FastAPI) → LangGraph RemoteGraph → OpenAI (Responses + tools) + LangGraph Store (pgvector).

## Components

- Chainlit UI (ca-chainlit)
    - FastAPI server mounting Chainlit at /chat and static /auth SPA.
    - MSAL SPA: loginRedirect + handleRedirectPromise + acquireTokenSilent, posts to /_auth/token (HttpOnly cookie). Logout with logoutRedirect.
    - Chainlit header_auth_callback consumes cookie/Authorization header to create a session. 
    - Proxies /ui/* to Gateway for thread CRUD and utilities.
    - Web‑search toggle in Chat Settings (default off).
    - SSE client renders streamed tokens.

- Gateway (ca-gateway)