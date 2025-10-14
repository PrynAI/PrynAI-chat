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
- History pane (UI) - Done 
- Long‑term memory (after threads & history) -Done
- Response structure output:- Done
    The OpenAI API returns plain text with Markdown syntax.
    chat gpt renders that Markdown into styled HTML.
    If you want the same look:
	•	Use a Markdown renderer (like react-markdown, marked, or markdown-it)
- File upload (pdfs, docx, txt)
- user profile settings
- Arcade Connectors
- RAG integration with realtime enviornmental CO2 emission data 
- pay pricing (subscrition or token based)
- vendor gateway payment
- https://docs.langchain.com/oss/python/langgraph/persistence#replay


Should have :

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


next day i come and browse chat.prynai.com i can login to my profile there is not chat history and when do any prompt i get response as 

Error: peer closed connection without sending complete message body (incomplete chunked read)

to resolve this i had to . go to right profile and click sign out 
after clikcing to signout it takes me to auth page then i have to sign-in and then refresh token and then it takes me to chat.prynai.com profile page

now i can see my chat history now my prompts are working

how can we keep cookies forever with out expiry so that only when users signsout it should create new cookie . 

because chainlit ui expires every day but not Microsoft authentication . 

every deployment to container . app is being broken to fix i need to click signout and i get message on login so i click referesh login page then it redirects to auth and it automatically signs in and then load page and the prompt works

how come we browser retain cookies after deployments ? So that browser remain logged in




