// apps/chainlit-ui/src/public/login-redirect.js
// Robust sidebar + auth helpers for PrynAI Chat UI.
// - Works on /chat, /chat/, and /chat/?t=<thread_id>
// - Never uses invalid CSS selectors in JS (no :contains())
// - Creates "New Chat / Search / Chats" sidebar and navigates via /open/t/<id>
// - Hides Chainlit's built-in "New Chat" header button defensively

(function redirectChatLoginToAuth() {
    try {
        const p = window.location.pathname;
        if (p === "/chat/login") {
            if (sessionStorage.getItem("pry_auth_just_logged") === "1") {
                sessionStorage.removeItem("pry_auth_just_logged");
                return; // allow Chainlit to finish loading once after login
            }
            window.location.replace("/auth/");
        }
    } catch (_) { }
})();

/* ---------- Hide built-in "New Chat" header button (Bug #2) ---------- */
(function hideBuiltInNewChat() {
    function scrub() {
        const header = document.querySelector("header");
        if (!header) return;

        // Hide by ARIA first (works on recent Chainlit)
        header.querySelectorAll('button[aria-label="New Chat"]').forEach((b) => {
            b.style.display = "none";
        });

        // Fallback: look for any header buttons whose visible text matches /new chat/i
        header.querySelectorAll("button").forEach((b) => {
            const label = (b.getAttribute("aria-label") || "") + " " + (b.textContent || "");
            if (/new\s+chat/i.test(label)) {
                b.style.display = "none";
            }
        });
    }
    const mo = new MutationObserver(scrub);
    mo.observe(document.documentElement, { childList: true, subtree: true });
    scrub();
})();

/* ---------- History Sidebar (New Chat / Search / Chats) ---------- */
(function initSidebar() {
    // Only render on /chat (with or without query string)
    if (!window.location.pathname.startsWith("/chat")) return;

    // Don't create twice
    if (document.getElementById("pry-sidebar")) return;

    // Light, safe CSS (no :has or :contains so older engines won't choke)
    const css = `
  body.pry-with-sidebar #root, body.pry-with-sidebar .cl-root { margin-left: 290px; }
  #pry-sidebar{position:fixed;left:0;top:0;height:100%;width:290px;background:#101014;color:#e6e6e6;z-index:9999;border-right:1px solid #2a2a2e;}
  #pry-sidebar header{display:flex;align-items:center;justify-content:space-between;padding:12px;border-bottom:1px solid #2a2a2e;font-weight:600}
  #pry-sidebar .pry-body{padding:12px;display:flex;flex-direction:column;gap:10px}
  #pry-sidebar a.pry-new{display:block;text-decoration:none;text-align:center;padding:8px 10px;border:1px dashed #7b5cff;background:transparent;color:#bfa8ff;border-radius:8px;cursor:pointer;font-weight:600}
  #pry-sidebar input.pry-search{width:100%;padding:8px;border:1px solid #2a2a2e;background:#141418;color:#ddd;border-radius:8px;outline:none}
  #pry-sidebar ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px;overflow:auto;max-height:calc(100vh - 170px)}
  #pry-sidebar li{display:flex;align-items:center;gap:8px;justify-content:space-between;padding:8px;border-radius:8px}
  #pry-sidebar li:hover{background:#17171c}
  #pry-sidebar .title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:190px}
  #pry-sidebar .meta{opacity:.6;font-size:.85em}
  #pry-sidebar .row{display:flex;align-items:center;gap:8px}
  #pry-sidebar .icon{opacity:.7}
  #pry-sidebar .rename{opacity:.6;cursor:pointer}
  #pry-sidebar .rename:hover{opacity:1}
  `;
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
    document.body.classList.add("pry-with-sidebar");

    const side = document.createElement("aside");
    side.id = "pry-sidebar";
    side.innerHTML = `
    <header>
      <span>Chats</span>
      <span class="meta">PrynAI</span>
    </header>
    <div class="pry-body">
      <a href="#" class="pry-new" data-new>➕ New Chat</a>
      <input class="pry-search" placeholder="Search chats"/>
      <ul class="pry-list" aria-label="Chat history"></ul>
    </div>`;
    document.body.appendChild(side);

    const listEl = side.querySelector(".pry-list");
    const searchEl = side.querySelector(".pry-search");
    const newLink = side.querySelector("a.pry-new");

    async function api(path, opts) {
        const r = await fetch(path, { credentials: "include", ...opts });
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
    }

    async function refresh() {
        try {
            const items = await api("/ui/threads"); // -> Gateway threads, newest first
            render(items);
        } catch (e) {
            console.warn("History load failed", e);
        }
    }

    function render(items, q = "") {
        listEl.innerHTML = "";
        const qn = q.trim().toLowerCase();
        items
            .filter((t) => !qn || (t.title || t.thread_id).toLowerCase().includes(qn))
            .forEach((t) => {
                const li = document.createElement("li");
                li.innerHTML = `
          <a class="row" href="/open/t/${t.thread_id}" style="display:flex;align-items:center;gap:8px;text-decoration:none;color:inherit">
            <span class="icon">💬</span>
            <div class="col">
              <div class="title" title="${t.title || t.thread_id}">${t.title || t.thread_id}</div>
              <div class="meta">${(t.updated_at || t.created_at || "").slice(0, 16).replace("T", " ")}</div>
            </div>
          </a>
          <span class="rename" title="Rename">✎</span>`;

                // Rename (no navigation)
                li.querySelector(".rename").addEventListener("click", async (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    const cur = t.title || "";
                    const next = window.prompt("Rename chat:", cur);
                    if (next && next.trim() && next.trim() !== cur) {
                        await api(`/ui/threads/${t.thread_id}`, {
                            method: "PUT",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ title: next.trim() }),
                        });
                        await refresh();
                    }
                });

                listEl.appendChild(li);
            });
    }

    // Create then navigate via /open/t/<id> (server sets cookie + redirects to /chat/?t=...)
    newLink.addEventListener("click", async (e) => {
        e.preventDefault();
        const created = await api("/ui/threads", { method: "POST" });
        window.location.assign(`/open/t/${created.thread_id}`);
    });

    searchEl.addEventListener("input", async (e) => {
        try {
            const items = await api("/ui/threads");
            render(items, e.target.value || "");
        } catch (_) { }
    });

    // If user hand-types /chat/?t=<thread_id>, apply the cookie then reload cleanly
    (async function ensureDeepLinkApplied() {
        const url = new URL(window.location.href);
        const tid = url.searchParams.get("t");
        if (!tid) return;
        const key = "pry_tid_applied";
        if (sessionStorage.getItem(key) === tid) return;
        try {
            await api("/ui/select_thread", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ thread_id: tid }),
            });
            sessionStorage.setItem(key, tid);
            window.location.replace(`/chat/?t=${tid}`);
        } catch (e) {
            console.warn("Failed to apply deep-link thread id", e);
        }
    })();

    refresh();
})();