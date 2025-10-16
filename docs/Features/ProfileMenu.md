# Profile Menu & Help Links

## What we shipped

### Inside the avatar dropdown (top‑right):

- Display name (built‑in)
- Email (only when we can prove it’s the real email; otherwise we hide it)
- Help Center → https://prynai.github.io
- Release Notes → https://github.com/PrynAI/PrynAI-chat/releases
- Subscription → https://chat.prynai.com/subscription
- Logout (built‑in)

#### Implementation lives entirely in a small, modular JS plugin loaded by Chainlit’s custom_js hook. No forking of Chainlit’s frontend.


### Why this approach?

- Chainlit doesn’t expose a public API to customize the avatar menu. We use the documented custom_js hook to augment the DOM when the menu opens (MutationObserver). This keeps us on the upgrade path.
- Our UI is mounted under /chat, but we serve static assets from /public (and /icons) as well. This avoids fragile “/chat/public/…” links and fixes the 404s seen earlier when the app assumed a root path. Chainlit itself is mounted at /chat by our FastAPI wrapper.
- The email line only shows if we can extract a human email from Entra claims; we refuse onmicrosoft/UPN‑ish GUIDs to avoid confusing users.


### File map (added/changed)

| File                                                    | Purpose                                                                                                                                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/chainlit-ui/src/public/profile-menu.js`           | DOM plugin that augments the profile dropdown: inject email (when valid), Help, Release Notes, Subscription; hides email if it looks synthetic.                                                                                 |
| `apps/chainlit-ui/src/public/login-redirect.js`         | Existing sidebar/auth bootstrap. At the bottom it dynamically loads `profile-menu.js` so we keep one `custom_js` entry. (Two variants in repo point to `/public/...` or `/chat/public/...` depending on static routing choice.) |
| `apps/chainlit-ui/src/server.py`                        | FastAPI wrapper that mounts Chainlit at `/chat`, handles cookie/session, and **prefers a real email claim**: `email` first, then `emails[0]`, else fallbacks; exposes that in `cl.User.metadata`.                               |
| `apps/chainlit-ui/config.toml`                          | Loads our `custom_js` and CSS; declares optional **header links** (“Help Center”, “Release Notes”). (Two variants in repo: icons loaded from `/icons/...` or `/chat/public/icons/...`.)                                         |
| `apps/chainlit-ui/src/public/hide-default-new-chat.css` | Imports our markdown theme via `/public/markdown-theme.css`. 404s here were a clue that `/public` wasn’t mounted at root.                                                                                                       |
| `apps/chainlit-ui/src/public/markdown-theme.css`        | Code‑block & Markdown styling.                                                                                                                                                                                                  |


### How it works (logic & data flow)

#### Getting identity information into the browser (no extra calls)

- During login on /auth, MSAL acquires a CIAM access token; we store it as an HttpOnly cookie via /_auth/token. Chainlit then creates a session from that token at /chat.

- On each request, our @cl.header_auth_callback decodes (locally, unverified) the token payload to build cl.User and prefers a human email if present:
email → first of emails[] → name/UPN/sub (fallback). We place these in User.metadata for the UI.

- The plugin later fetches /chat/user to read User.metadata (no new backend work required).


#### Rendering the menu items (client‑side, progressive)

- A tiny MutationObserver watches for the avatar menu to appear (it contains the built‑in Logout item).

- We inject:

- Email: only if it passes filters → not an onmicrosoft.com domain and not a GUID‑like local part (synthetic UPN). Otherwise we omit it.

- Help Center, Release Notes (new tab), Subscription (same tab).

- The plugin is loaded from login-redirect.js so we keep one custom_js in Chainlit config.


#### Fixing /public 404s (static routing)

- Chainlit is mounted under /chat (see mount_chainlit(path="/chat")). When assets were referenced at /public/..., the server didn’t serve them → 404.

- (scoped URLs): keep static under /chat/public/... and update references accordingly (see alt config.toml and login-redirect.js samples).

### Email behavior (details)

#### Goal:
- show the user’s real email if available; never show synthetic UPNs such as GUID@tenant.onmicrosoft.com.

#### Extraction logic (server):

- Prefer email claim; if empty, prefer first of emails[].

- If neither is present we fall back to name/preferred_username for display_name only.

#### Rendering rule (client):

- If email domain ends with onmicrosoft.com or the local part looks like a GUID → don’t render an email row at all; the menu then shows only display name + links + Logout.


- Optional identity tweak: In Entra External ID, add optional claim email to the access token for the SPA → API scope, and include email (and/or emails) in your user flow “application claims” so the token reliably contains a real email. Our code already uses these claims when present. Architecture notes and the auth flow are in our auth README.

#### Chainlit UI config (header links + single custom_js):

```

# apps/chainlit-ui/config.toml
[UI]
custom_css = "/public/hide-default-new-chat.css"
custom_js  = "/public/login-redirect.js"

[[UI.header_links]]
name = "Help"
display_name = "Help Center"
url = "https://prynai.github.io"
target = "_blank"
icon_url = "/chat/public/icons/question-mark-circle.svg"

[[UI.header_links]]
name = "ReleaseNotes"
display_name = "Release Notes"
url = "https://github.com/PrynAI/PrynAI-chat/releases"
target = "_blank"
icon_url = "/chat/public/icons/release-notes-line.svg"

```



#### Plugin loader (tail of custom JS):

```
/* apps/chainlit-ui/src/public/login-redirect.js */
(function loadProfileMenuPlugin() {
  try {
    if (!location.pathname.startsWith("/chat")) return;
    const s = document.createElement("script");
    s.src = "/public/profile-menu.js";  // or "/chat/public/profile-menu.js" if using scoped paths
    s.defer = true;
    document.head.appendChild(s);
  } catch (_) {}
})();

```
#### Token → user metadata (server):

```
# apps/chainlit-ui/src/server.py (excerpt)
emails_claim = claims.get("emails")
primary_email = claims.get("email") or (emails_claim[0] if isinstance(emails_claim, (list, tuple)) and emails_claim else None)
return cl.User(identifier=claims.get("name") or primary_email or claims.get("preferred_username") or claims.get("sub") or "user",
               metadata={ "email": primary_email, "emails": emails_claim, ... })

```
### Non‑functional considerations

- Zero impact on TTFT/TPOT (DOM‑only injection; no extra backend calls besides /chat/user, which Chainlit already hits). Streaming, moderation, memory, and thread logic are unchanged.

- Code is modular: remove the menu plugin by deleting the loader snippet at the bottom of login-redirect.js. The rest of the chat UI continues to work.


### Future small enhancement (nice‑to‑have)

- Manage Profile modal (edit display_name) that PATCHes /api/profile—the gateway & store logic already exist; we’d only add a tiny UI dialog.

