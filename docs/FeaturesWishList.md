Functional Features:

Must Have
- Chat reponses with reasoning  - Done 
- Internet Search(OpenAI-"web-search") - Done 
- security gaurdrails - OpenAI moderation model - Done
- Microsoft entra external id setup with oauth 2.0 authentication with email and google - Done -  Done


- Profiles (Gateway) — create/read user profile in LangGraph Store - Done
- Threads API (Gateway) — create & list -Done
- UI bridge for tokens — Done
- Agent: enable the checkpointer (short‑term memory) -Done
- History pane (UI)
- Long‑term memory (after threads & history)



- Chat Persistance-InSession memory (ShortTerm memory)
- when closing the chat and reopening the chat session memory, should persist (LongTerm Memory)
- While selecting new chat , the current chat should go in to chat history with out loosing the chat content
- Ofcourse all these should be stored in a user profile that is logged in . Hence user profile should be created 
- File upload (pdfs, docx, txt)
- user profile settings
- Arcade Connectors
- user signup - signin
- user authentication through providers to signup
- pay pricing (subscrition or token based)
- vendor gateway payment


Should have :
- search chat history
- highlight the note to turn on internet search from setting if you want data from June 2024



Bugs to fix:

error : 

browsers were holding onto expired or mismatched credentials. The server was then closing the stream mid‑response, which surfaced as the “peer closed connection without sending complete message body” error.

Auth/session mismatch: The disconnect was triggered by invalid or stale auth state.

Symptom vs. cause: the underlying cause was authentication

Suggedted fixes:

Add a /logout endpoint in your FastAPI/Chainlit app that explicitly clears cookies and invalidates tokens, so users don’t get stuck with stale sessions.

Shorten cookie lifetime or add refresh logic so expired tokens don’t linger.

Better error handling: Instead of letting the server close the stream abruptly, log and return a structured error (e.g., 401 Unauthorized) so it’s clear to the client what happened.

Revision hygiene: Keep only one ingress‑enabled revision active to avoid routing users to older builds with different auth wiring.




