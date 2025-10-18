## PrynAI Chat
- Agentic AI chat app with Chainlit UI → FastAPI Gateway → LangGraph agent, plus Microsoft Entra External ID (CIAM) sign‑in, streaming via SSE, file uploads, web search, and short‑ & long‑term memory. See the detailed system design in the Architecture doc. https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Architecture/Architecture.md

### Quick links
### Architecture (overview & diagrams)
- https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Architecture/Architecture.md
### Infrastructure setup (Azure, deploy, runtime config)
- https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Architecture/Infra-setup.md
### Feature docs (index below)
- https://github.com/PrynAI/PrynAI-chat/tree/main/docs/Features
### Issues / bug tracker
- https://github.com/PrynAI/PrynAI-chat/issues
### Roadmap / Feature wishlist
- https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/FeaturesWishList.md
### Project blog (architecture stories & ADRs)
- https://prynai.github.io/

## What is in this repository?
- This is a monorepo. At a glance (top‑level folders):
- apps/ – service apps (Chainlit UI and FastAPI Gateway).
- docs/ – all documentation (architecture, infra, features).

## Architecture at a glance

 ### UI:
- Chainlit served by a small FastAPI app (auth SPA + chat UI).
### Gateway:
- FastAPI API that validates tokens, streams responses over SSE, writes transcripts, and brokers to the agent.
- Full diagrams, flows, security notes, and config matrices live in the Architecture doc

## Getting started
 - Use Infra‑setup to provision Azure resources, configure environments, and deploy the two containers (UI and Gateway). That doc is the single source of truth for prerequisites, env vars, and scale settings - https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Architecture/Infra-setup.md

## Feature documentation (read me first ➜ then code)
- Each feature below links to a focused doc that explains what it does, how to use it, and where the code lives.
### Styled Chat Responses (HTML/Markdown)
- How assistant messages are rendered with clean HTML/Markdown and a lightweight theme—what’s allowed, and how to customize.- https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/ChatResponsesStyledHTML.md

### File Uploads
  - Upload pipeline, supported types, size limits, optional OCR, and how extracted text is injected as attachments context for the model. -https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/FileUploads.md

### Long‑Term Memory
 - Durable user & episodic memories backed by a vector store (pgvector). Retrieval at turn start; writes after the turn completes. - https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/LongTermMemory.md

### OpenAI Web Search
 - When/why we enable web search, how it’s toggled in the UI, and the behavior of “search‑backed” answers.
 - https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/OpenAIWebSearch.md

### Profile Menu (UI plugin)
- The customizable header/profile menu: entries, links, and how to extend it. - https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/ProfileMenu.md

### Safety & Guardrails
  - Input/output moderation, blocked categories, and how the Gateway surfaces safety notices in the stream. -
     https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/Safety%26Guardrails.md

### Authentication setup (Microsoft Entra External ID)
- CIAM sign‑in/signup via MSAL (browser redirect), token hand‑off to the UI, and Gateway JWT validation.-https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/authenticationsetup.md

### Short‑Term Memory
- How conversational state is preserved within a thread/session and how it differs from long‑term memory. - https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Features/shorttermmemory.md


## How to navigate this repo
- Start with Architecture for the mental model and diagrams. https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Architecture/Architecture.md
- Follow Infra‑setup to provision Azure and run locally or deploy.-https://github.com/PrynAI/PrynAI-chat/blob/main/docs/Architecture/Infra-setup.md
- Pick features from the list above—each doc points to the relevant code paths - https://github.com/PrynAI/PrynAI-chat/tree/main/docs
- Open an issue for bugs or questions; check existing issues first. - https://github.com/PrynAI/PrynAI-chat/issues

## Contributing & support
  - Issues: File bugs, questions, or enhancement requests in GitHub Issues (labels help triage)
  - Docs: If a page is unclear, propose an edit in docs/ with a small PR.
  - Roadmap: Discuss ideas against the Feature Wishlist before implementation.
  - Blog: Architecture deep‑dives and ADRs are published at prynai.github.io.
 
### Note:
 - If you landed here from the blog, start with Architecture.md for the big picture, then jump into the specific feature you care about using the index above.
  

    
