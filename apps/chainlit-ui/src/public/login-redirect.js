// apps/chainlit-ui/src/public/login-redirect.js
// Sidebar + auth helpers for PrynAI Chat UI.
// - Works on /chat, /chat/, and /chat/?t=<thread_id>
// - Creates "New Chat / Search / Chats" sidebar
// - On click: POST /ui/select_thread to set cookie, then navigate to /chat/?t=<id>
// - Hides Chainlit's built-in "New Chat" button(s) in header/body

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

/* ---------- Hide built-in "New Chat" controls (Bug #2) ---------- */
(function hideBuiltInNewChat() {
    function scrub() {
        // Hide anything that looks like a "New Chat" button via stable attributes
        document.querySelectorAll('[data-testid="new-chat-button"], button[aria-label="New Chat"]').forEach((b) => {
            b.style.display = "none";
        });
    }
    const mo = new MutationObserver(scrub);
    mo.observe(document.documentElement, { childList: true, subtree: true });
    scrub();
})();

/* ---------- History Sidebar (New Chat / Search / Chats) ---------- */
(function initSidebar() {
    if (!window.location.pathname.startsWith("/chat")) return;
    if (document.getElementById("pry-sidebar")) return;

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
  #pry-sidebar .row{display:flex;align-items:center;gap:8px;cursor:pointer}
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
            const items = await api("/ui/threads");
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
          <div class="row" data-tid="${t.thread_id}">
            <span class="icon">💬</span>
            <div class="col">
              <div class="title" title="${t.title || t.thread_id}">${t.title || t.thread_id}</div>
              <div class="meta">${(t.updated_at || t.created_at || "").slice(0, 16).replace("T", " ")}</div>
            </div>
          </div>
          <span class="rename" title="Rename">✎</span>`;

                // Navigate deterministically: set cookie, then go to /chat/?t=<id>
                li.querySelector(".row").addEventListener("click", async (ev) => {
                    ev.preventDefault();
                    try {
                        await api("/ui/select_thread", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ thread_id: t.thread_id }),
                        });
                    } catch (_) { }
                    window.location.assign(`/chat/?t=${t.thread_id}`);
                });

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

    // Create → select → navigate
    newLink.addEventListener("click", async (e) => {
        e.preventDefault();
        const created = await api("/ui/threads", { method: "POST" });
        await api("/ui/select_thread", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: created.thread_id }),
        });
        window.location.assign(`/chat/?t=${created.thread_id}`);
    });

    searchEl.addEventListener("input", async (e) => {
        try {
            const items = await api("/ui/threads");
            render(items, e.target.value || "");
        } catch (_) { }
    });

    // If user hand-typed /chat/?t=<thread_id>, apply cookie and reload once
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