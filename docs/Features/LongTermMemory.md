# Long‑Term Memory (LangGraph Store + pgvector)

## Goal

- Persist useful facts about the user and concise “episode” summaries across threads and sessions, and retrieve them semantically to personalize future responses. The memory lives in LangGraph Store (Postgres + pgvector) and is scoped per user (not per thread). We enable semantic search once at the app level and consume it inside the chat node.

## Architecture at a glance

### Where it runs

- Agent (LangGraph Cloud): chat graph reads/writes memory via the injected store object; it retrieves relevant memories before answering and writes new memories after answering.

- Gateway (FastAPI): attaches configurable.user_id and configurable.thread_id on every turn; the agent uses user_id to scope long‑term memory and thread_id for short‑term state.

### Semantic index (pgvector)

- Enabled in langgraph.json so store.search(...) uses OpenAI embeddings (text-embedding-3-small, 1536 dims) on all stored fields.


### Short‑term vs long‑term

- Short‑term memory = checkpointer (per‑thread). Different thread id ⇒ fresh context.

- Long‑term memory = Store (per‑user). Survives thread switches, page reloads, and container restarts

## What we store

- We store two kinds of memories in separate namespaces, both per user:

### User memories (durable facts/preferences)

- Namespace: ["users", <user_id>, "memories", "user"]

- Value shape: { "text": <short fact>, "type": "user", "source_thread": <thread_id>, "ts": <ISO> }

- Examples: “Lives in London”, “Nickname is DG”, “Prefers concise bullet answers”


### Episodic summaries (search‑friendly one‑liners of a turn)

- Namespace: ["users", <user_id>, "memories", "episodic"]

- Value shape: { "text": <one sentence>, "type": "episodic", "source_thread": <thread_id>, "ts": <ISO> }

- Both types are indexed on the text field so semantic search can retrieve them using pgvector.

## How it works (request lifecycle)

### Before the LLM call — retrieve

- We take the user’s latest utterance and search both namespaces (user and episodic) with store.search(...).

- We combine, rank by similarity score, and prepend a compact System message:
“You have durable memory about this user…” with bulleted items (trimmed to ~900 chars) so it remains a small, helpful hint.

### Answer as usual

- The rest of your graph (models, web‑search toggle) runs unchanged.

### After the LLM call — write back

- User memories: a tiny model extracts up to 3 durable facts/preferences from the user’s last message using structured output. The schema is strict (additionalProperties=false), enforced by Pydantic extra="forbid" + with_structured_output(..., strict=True). Each string becomes a memory item under the user namespace.

- Episodic summary: a one‑sentence summary of the user+assistant exchange is written under the episodic namespace.


## Files & key code paths

### Semantic index (enable once)

- apps/agent-langgraph/langgraph.json → store.index = OpenAI embeddings + pgvector (fields: "$", dims 1536).

### Chat graph (retrieve → answer → write)

- apps/agent-langgraph/my_agent/graphs/chat.py

- Accepts store: BaseStore (injected by platform).

- Retrieves memories → prepends system tip → invokes model → writes user + episodic memories.

### Memory helpers (namespaces, retrieval, extraction, summarization)

- apps/agent-langgraph/my_agent/features/lt_memory.py

- Namespaces: ns_user(...), ns_episodic(...)

- Retrieval: store.search(...) merge/sort

- System tip: compact bullets

- Extraction: Responses API + ExtractedMemories (Pydantic v2), strict schema

- Writeback: store.put(..., index=["text"]) for pgvector indexing.

### Deps

- Agent pyproject.toml includes langchain>=0.3.8, langchain-openai>=0.3.30, etc., so the embedding shorthand ("openai:...") and Responses API paths work as expected.

### Gateway (identity & threading)

- apps/gateway-fastapi/src/main.py

- Validates CIAM JWT; sets configurable.user_id and forwards thread_id in config for each turn (the agent uses these for scoping).

### Short‑term memory (for contrast)

- apps/agent-langgraph/my_agent/utils/checkpointer.py

- Local dev can opt into MemorySaver; on Cloud, LangGraph provides a durable Postgres checkpointer per thread_id.


## Data flow details

### Retrieval

```
hits = store.search(ns_user(user_id), query=last_user_text, limit=4)
# + same for episodic; combine + sort by score (desc)
tip = memory_context_system_message(hits, max_chars=900)
messages = [tip] + messages  # prepend when available

```

- The above runs inside the chat node before calling the LLM. It’s best‑effort and silent on failure.

### Writeback

- User memories (strict structured output):

```
parsed = llm.with_structured_output(ExtractedMemories, strict=True).invoke(doc)
for m in parsed.memories[:3]:
    store.put(ns_user(user_id), key=uuid4(), value={"text": m, ...}, index=["text"])

```

- ExtractedMemories uses Pydantic extra="forbid" so the Responses API accepts the schema (additionalProperties=false).

- Episodic (plain text):

```
summ = llm.invoke(doc).content.strip()
store.put(ns_episodic(user_id), key=uuid4(), value={"text": summ, ...}, index=["text"])

```

### How it differs from short‑term memory

- Short‑term: stored by the LangGraph checkpointer, scoped by thread_id. Switching threads resets context; it is ideal for ongoing task/plan state.

- Long‑term: stored in the Store under ["users", <user_id>, "memories", ...]; retrieved via semantic search; available across threads and restarts; strictly per user because the gateway always forwards

## Testing checklist

### Manual (UI)

- Thread‑A: “For future chats: I live in London, my nickname is RS, and I like concise bullet answers.”
Then: “Where do I live and what’s my nickname?” → Expect “London / RS”.

- New thread (Thread‑B): ask the same question → Expect recall (proves cross‑thread).

- Sign in as a different account → Ask again → Expect no recall (per‑user isolation).


### Observability

- In LangSmith, open the trace → the first model input should contain a System message starting “You have durable memory…” with bullets when retrieval hits. The gateway stream path is unchanged.

## Troubleshooting

### No cross‑thread recall

- Confirm the deployment picked up langgraph.json with the store.index block (pgvector enabled).

- Verify the gateway includes configurable.user_id and your UI/Gateway auth is passing a valid token.

### Structured‑output 400 from OpenAI

- Ensure ExtractedMemories uses Pydantic v2 config extra="forbid" and call with_structured_output(..., strict=True) so the server sees additionalProperties=false. This was the root cause of earlier schema errors and is fixed in our code.

### Performance & safety notes

- The prepended memory tip is small (≤ ~900 chars) and appears only when search returns hits, keeping TTFT/TPOT steady.

- Content moderation and streaming remain exactly as implemented in the gateway; memory writes happen after the turn and are best‑effort (never block or break chat).

### File map (quick reference)

```
apps/
  agent-langgraph/
    langgraph.json                     # enables pgvector semantic index            ⟶  store.index
    my_agent/
      graphs/chat.py                   # retrieve → answer → write (core node)
      features/lt_memory.py            # namespaces, search, extraction, summary
      utils/checkpointer.py            # short-term per-thread memory
  gateway-fastapi/
    src/main.py                        # sets configurable.user_id & thread_id

```

### Done criteria

- Cross‑thread recall of durable user facts and episodic summaries for the same user_id.

- Isolation across users.

- No changes required in UI flow; web‑search toggle and streaming path remain intact.

### The agent now remembers stable facts and past episodes in a pgvector‑backed store, retrieves them semantically per user, and feeds them to the model as lightweight context each turn.
