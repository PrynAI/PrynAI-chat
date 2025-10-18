# End-to-End (Single Region, pgvector)

# PrynAI Chat — End‑to‑End Architecture (Single Region, PGVector Memory)

### Edge & Identity
  • DNS (GoDaddy): CNAME chat.prynai.com → ACA public FQDN
  • Microsoft Entra External ID (CIAM): Google sign‑in → issues JWT

### Application — Azure Container Apps (one environment, two apps)
  • Chainlit (UI)
      – WebSocket streaming UI
      – Drag‑and‑drop files/images
      – Chat Settings toggle: “Web search: on/off”
  • FastAPI (Gateway)
      – Validates JWT (Entra)
      – Proxies/streams tokens end‑to‑end
      – Calls LangGraph Platform (Cloud)
      – Uses Managed Identity to read secrets from Key Vault

### Agent Runtime — LangGraph Platform (Cloud)
  • Orchestrator: LangGraph graph (nodes = LLM, tools, connectors)
  • Long‑term memory: LangGraph Postgres Store + pgvector (user/thread memories, RAG)
  • Observability: LangSmith tracing, dashboards, evals
### External Tools & Models
  • OpenAI API (chat/reasoning/embeddings; streamed responses)
  • Open AI Web search
  • MCP tools via Arcade:
      – Gmail, Google Calendar
      – Outlook Mail, Outlook Calendar
      – Microsoft Teams, LinkedIn
      – GitHub
      – Custom MCP: https://mcp.prynai.com/mcp

### Platform Services & CI/CD
  • Azure Key Vault (API keys, OAuth client secrets)
  • ACR (images) + GitHub Actions (OIDC) → ACA deploy
  • ACA autoscaling (KEDA): minReplicas > 0 for low TTFT, HTTP/CPU triggers

### Request path
  1) Browser → ACA public FQDN → Chainlit (ACA)
  2) Chainlit (WebSocket) → FastAPI (JWT)
  3) FastAPI → LangGraph Platform (invoke graph)
  4) LangGraph → (as needed) OpenAI  / Arcade MCP tools
  5) LangGraph ↔ Postgres Store (pgvector) for long‑term memory
  6) Streamed tokens ← FastAPI ← Chainlit ← Browser (TTFT-first)
