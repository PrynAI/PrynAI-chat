# PrynAI‑chat

- A production‑ready LLM assistant running on Azure Container Apps with a Chainlit UI, a FastAPI gateway, and a LangGraph Platform (Cloud) agent. It streams end‑to‑end, supports short‑term memory via threads + checkpointer, has chat history (list/select/rename/delete + search) with auto‑titles, persists a transcript for reloads, and optionally enables OpenAI Web Search.

## Short‑term memory (in‑session) with Threads + Checkpointer
- The graph is compiled with a checkpointer (MemorySaver for local dev; Cloud provides durable Postgres). We pass a concrete configurable.thread_id; keeping the same id resumes context across turns and restarts.

## Chat history UX (list / select / search / rename / delete)
- Left sidebar (toggleable; closed by default on mobile). “New Chat”, “Search chats”, then the user’s threads sorted newest‑first. Selecting a thread uses /open/t/<id> which sets a cookie before Chainlit loads; the Chainlit app reads that cookie and runs on that thread id. Rename and Delete are wired to gateway endpoints (hard‑delete if supported, soft‑delete fallback). The default Chainlit “New Chat” UI is hidden.

## Auto‑title
- First user turn sets a title (safe, deterministic: first ~7 words, title‑cased). Gateways’ rename route updates metadata.title


## Transcript persistence + reload - Did not worked - Bug
- Gateway appends {role, content, ts} to a per‑thread transcript in the LangGraph Store on both user and assistant turns. The UI replays this transcript after refresh so the page is never blank. Route: GET /api/threads/{thread_id}/messages

## Threads & short‑term memory (how it works)

- The gateway sends configurable.thread_id when streaming; the Cloud checkpointer persists per‑thread state. Keeping the same id resumes context. Switching ids starts fresh.

- The UI stores the active thread id in cookie prynai_tid via /open/t/<id>; Chainlit reads it on start, loads that thread, and replays the transcript.

- Threads API is scoped to the authenticated user (metadata.user_id). Newest first, soft‑deletes filtered out.


