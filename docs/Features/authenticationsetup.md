# PrynAI — Authentication (Entra External ID → Chainlit UI → Gateway)

## Goal: 
- Public users sign in with Email or Google (via Microsoft Entra External ID for customers/CIAM), land in the Chainlit chat, and the UI streams replies through the Gateway to LangGraph/OpenAI—with durable user profiles and threads.

## Architecture (auth path)

```
Browser
  ⮕ /auth  (MSAL SPA) → saves CIAM access token as HttpOnly cookie
  ⮕ /chat  (Chainlit)  → header_auth_callback reads cookie/Bearer and sets session
  ⮕ Gateway (FastAPI)  → validates CIAM JWT (OIDC discovery + JWKS), streams to LangGraph

```

- MSAL Browser handles interactive login and logout in /auth. After login we save the access token to the UI server (/_auth/token) and pre‑establish a Chainlit session, then redirect to /chat/.

- Chainlit UI server serves /auth, manages the HttpOnly cookie, and authenticates incoming requests via @cl.header_auth_callback (reads cookie or an initial Bearer token) before mounting Chainlit at /chat.

- Gateway (FastAPI) validates CIAM access tokens (OIDC discovery document + JWKS, issuer/audience checks) then streams chat tokens to the UI. It also exposes profiles and threads APIs backed by the LangGraph Store.


## 1) Create/Configure Microsoft Entra External ID (CIAM)

### A. External tenant + user flow

- Create/confirm an External ID (customers) tenant and a Sign‑up/Sign‑in user flow that supports Email and Google. 


- Under Platforms → Single‑page application, add Redirect URI:

- https://chat.prynai.com/auth/ (required for MSAL redirect login & logout).

- Important discovery endpoint (works for CIAM):
https://<SUBDOMAIN>.ciamlogin.com/<TENANT-ID>/v2.0/.well-known/openid-configuration

### B. Applications (2 apps)

1) SPA app (front end /auth)

- App (client) ID: your SPA client ID.

- Redirect URIs (SPA): https://chat.prynai.com/auth/

- No secret needed (public client).

- Will request the API scope below.

2) API app (Gateway)

- App (client) ID: your API/Gateway app GUID.

- Expose an API → App ID URI: api://<GATEWAY-API-GUID>

- Add scope: chat.fullaccess

- Grant the SPA permission to this scope


## 2) Chainlit UI — MSAL SPA at /auth and session bridge

- /apps/chainlit-ui/src/auth/index.html — minimal sign‑in page that loads MSAL, config, and auth.js.

- /apps/chainlit-ui/src/auth/auth.config.js — tenant, SPA client ID, API scope, and redirect URIs. The authority we use at runtime is tenant‑level (no policy in the URL).

- /apps/chainlit-ui/src/auth/auth.js — MSAL bootstrap + bridging:

acquire token → 2) POST /_auth/token (HttpOnly cookie) →

POST /chat/auth/header with Authorization: Bearer … to create the Chainlit session →

verify with GET /chat/user → 5) redirect /chat/. It also performs logout (clears app cookie and calls logoutRedirect).

- /apps/chainlit-ui/src/public/login-redirect.js — If Chainlit shows /chat/login, move to /auth/ (with a short‑lived guard to avoid loops immediately after login).

- /apps/chainlit-ui/src/server.py — FastAPI wrapper that serves /auth, exposes /_auth/token and /_auth/logout, and implements @cl.header_auth_callback to read the HttpOnly cookie (or a first‑probe Bearer) and build cl.User. It then mounts Chainlit at /chat.

- /apps/chainlit-ui/src/main.py — Chainlit app: sends SSE requests to the Gateway with the access token carried on the Chainlit user’s metadata.

- /apps/chainlit-ui/config.toml — loads public/login-redirect.js into Chainlit and sets standard UI options.

### Env vars (Chainlit container):

| Name                         | Example                                     | Why                                                                                |
| ---------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| `GATEWAY_URL`                | `https://ca-gateway.…azurecontainerapps.io` | Where the UI streams chat.                                                         |
| `CHAINLIT_CUSTOM_AUTH`       | `true`                                      | Enables custom auth callbacks (required for `header_auth_callback`). ([GitHub][1]) |
| `CHAINLIT_AUTH_SECRET`       | Secret (Key Vault)                          | Required by Chainlit auth; we set via ACA secret.                                  |
| `COOKIE_DOMAIN` *(optional)* | `chat.prynai.com`                           | If you want the cookie scoped to the apex.                                         |

[1]: https://github.com/Chainlit/chainlit/issues/2309?utm_source=chatgpt.com "Header Auth callback function is not invoked · Issue #2309"

- Container command: uvicorn src.server:app --host 0.0.0.0 --port 8000 (we ship a FastAPI wrapper; don’t run chainlit run src/main.py directly in prod).

## 3) Gateway (FastAPI) — JWT validation + streaming + profiles/threads

Files (already in repo):

- /apps/gateway-fastapi/src/auth/entra.py — Pulls the OIDC discovery document from ciamlogin.com, fetches JWKS, and verifies signature, issuer, and audience (your GUID). Also supports an opt‑in dev bypass header for local smoke tests.

- /apps/gateway-fastapi/src/main.py — CORS for your chat origin(s), moderation hook, /api/chat/stream SSE endpoint, and routers for profiles and threads (LangGraph Store)

### Env vars (Gateway container):

| Name                 | Example                                                                              | Why                                                                             |
| -------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `OIDC_DISCOVERY_URL` | `https://chatprynai.ciamlogin.com/<TENANT-ID>/v2.0/.well-known/openid-configuration` | **Tenant‑level** discovery works with your CIAM tokens.  ([Microsoft Learn][1]) |
| `OIDC_AUDIENCE`      | `<Gateway API client ID GUID>`                                                       | Use the **GUID** as audience for validation.                                    |
| `LANGGRAPH_URL`      | URL from LangGraph Cloud                                                             | Remote graph endpoint.                                                          |
| `LANGGRAPH_GRAPH`    | `chat`                                                                               | Graph name.                                                                     |
| `MODERATION_ENABLED` | `true`                                                                               | Optional output filter.                                                         |

[1]: https://learn.microsoft.com/en-us/troubleshoot/entra/entra-id/app-integration/troubleshooting-signature-validation-errors?utm_source=chatgpt.com "Troubleshoot Access Token Signature Validation Errors"


- Token validation is straight OIDC (issuer/audience/signature via JWKS). The discovery shape shown above is the one Microsoft calls out for External ID

## 4) Azure Container Apps — config & deploy

- Set the env vars above on each container app (Chainlit & Gateway). You can add or update them on a new revision in ACA. 


- Ensure the Chainlit revision uses the uvicorn src.server:app … command.

- Give each app a managed identity and use Key Vault references for secrets (e.g., CHAINLIT_AUTH_SECRET)

## 5) End‑to‑end test

### Token flow & session

- Visit https://chat.prynai.com/ → you’re redirected to /auth/.

- Click Sign in, complete Email or Google, land back on /auth/.

The SPA:

- acquires an access token for the chat.fullaccess scope,

- calls /_auth/token (HttpOnly cookie),

- calls /chat/auth/header (pre‑establishes Chainlit session), then

navigates to /chat/.

- If Chainlit briefly shows /chat/login, our small script sends you back to /auth/ and then returns to /chat/ after the session is established.

### Gateway smoke test (from a dev shell with a valid CIAM access token):
```
curl.exe -H "Authorization: Bearer $TOKEN" https://<gateway-host>/api/whoami

```
- Chat: type in the box—Chainlit forwards your token to the Gateway and SSE streams back model output

## 6) Troubleshooting (common, fixed)

- endpoints_resolution_error on /auth: authority/discovery mismatch. Use the tenant‑level CIAM authority https://<sub>.ciamlogin.com/<tenant-id>/ (and the matching discovery doc). 
Microsoft Learn

- invalid_claims at Gateway: audience mismatch. Set OIDC_AUDIENCE to the Gateway API app GUID, not the api://… URI.

- Loop /chat/login ↔ /auth/: we set a sessionStorage guard and explicitly hit /chat/auth/header before navigating to /chat/. Keep public/login-redirect.js and the pre‑establish call in auth.js.

- “Could not reach server” in chat: usually means Chainlit didn’t attach the token. Confirm header_auth_callback is returning a User that includes metadata.access_token. Then Chainlit’s main.py will forward the token to the Gateway.

## 7) File map (for quick edits)

```

apps/
  chainlit-ui/
    src/
      auth/
        index.html            # MSAL SPA shell                   :contentReference[oaicite:43]{index=43}
        auth.config.js        # tenant/app IDs, scope, URIs       :contentReference[oaicite:44]{index=44}
        auth.js               # MSAL + cookie + session bridge    :contentReference[oaicite:45]{index=45}
      public/login-redirect.js # /chat/login → /auth guard        :contentReference[oaicite:46]{index=46}
      server.py               # serves /auth + header auth mount  :contentReference[oaicite:47]{index=47}
      main.py                 # Chainlit app → Gateway SSE        :contentReference[oaicite:48]{index=48}
    config.toml               # UI settings (+ custom JS)         :contentReference[oaicite:49]{index=49}

  gateway-fastapi/
    src/auth/entra.py         # CIAM OIDC/JWKS validator          :contentReference[oaicite:50]{index=50}
    src/main.py               # CORS, SSE, profiles, threads      :contentReference[oaicite:51]{index=51}

```
## 8) Minimal environment checklist

### Chainlit UI (ACA “ca‑chainlit”)

- GATEWAY_URL = https://<gateway-host>

- CHAINLIT_CUSTOM_AUTH = true

- CHAINLIT_AUTH_SECRET = <secret> (Key Vault reference)

- (Optional) COOKIE_DOMAIN = chat.prynai.com

### Gateway (ACA “ca‑gateway”)

- OIDC_DISCOVERY_URL = https://<sub>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration

- OIDC_AUDIENCE = <Gateway API client ID GUID>

- LANGGRAPH_URL = <from LangGraph Cloud>

- LANGGRAPH_GRAPH = chat

## 9) Operational notes

- Keep CORS in the Gateway limited to your origins: https://chat.prynai.com and http://localhost:3000 (dev).

- MSAL logout: we clear the app cookie and call logoutRedirect, landing back on /auth/?loggedout=1. You can change that target in auth.config.js.

- Chainlit auth requires a CHAINLIT_AUTH_SECRET—we store it in Key Vault and reference it from ACA.

- If you add new domains, add them to SPA Redirect URIs and to CORS.

## 10) Quick smoke tests

```
# Acquire a CIAM access token for the API scope (from /auth or MSAL)
curl.exe -H "Authorization: Bearer $TOKEN" https://<gateway-host>/api/whoami

```

### UI login path

- Open https://chat.prynai.com/ → auto‑redirects to /auth/.

- Click Sign in → complete flow → redirected to /chat/.

- Type a message → Gateway streams a response.



