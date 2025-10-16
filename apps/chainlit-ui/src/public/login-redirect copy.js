// apps/chainlit-ui/src/public/login-redirect.js
// Sidebar + auth helpers for PrynAI Chat UI.
// - Works on /chat, /chat/, and /chat/?t=<thread_id>
// - Sidebar: Search / Chats (list) / Rename / Delete  (no custom New Chat link)
// - Click: /open/t/<id> sets cookie BEFORE Chainlit loads
// - Rebinds Chainlit's built-in "New Chat" to create a thread via our gateway, then /open/t/<id>
// - Adds a left-docked toggle button; sidebar is CLOSED by default (mobile friendly)
// - Redirects /chat/login to /auth/, unless just logged in (flag set by auth.js)

(function redirectChatLoginToAuth() {
    try {
        const p = window.location.pathname;
        if (p === "/chat/login") {
            if (sessionStorage.getItem("pry_auth_just_logged") === "1") {
                sessionStorage.removeItem("pry_auth_just_logged");
                return;
            }
            window.location.replace("/auth/");
        }
    } catch (_) { }
})();

/* ---------- Rebind the OOB "New Chat" to our /ui/threads -> /open/t/<id> flow ---------- */
(function rebindNewChatToPrynAI() {
    // Identify "New Chat" no matter how Chainlit renders it (button, link, div[role=button], etc.)
    const isNewChatLabel = (s) =>
        (s || "")
            .replace(/[+]/g, "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase() === "new chat";

    const looksLikeNewChat = (el) => {
        if (!el || !(el instanceof Element)) return false;
        const aria = (el.getAttribute("aria-label") || "");
        const testid = (el.getAttribute("data-testid") || "");
        const txt = el.textContent || "";
        return (
            isNewChatLabel(aria) ||
            /new[_\-\s]?chat/i.test(testid) ||
            isNewChatLabel(txt)
        );
    };

    async function createThread() {
        const r = await fetch("/ui/threads", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const t = await r.json();
        if (t?.thread_id) {
            window.location.assign(`/open/t/${t.thread_id}`);
            return true;
        }
        return false;
    }

    // Intercept clicks before React gets them (capture phase) to prevent the default OOB behavior.
    async function onClick(e) {
        try {
            // Find the nearest actionable element the user clicked on.
            const target =
                e.target.closest('[data-testid], [aria-label], button, a, [role="button"]') ||
                e.target;
            if (!looksLikeNewChat(target)) return;

            e.preventDefault();
            e.stopImmediatePropagation();
            e.stopPropagation();

            try {
                await createThread();
            } catch (err) {
                console.warn("Create thread failed; falling back to default New Chat", err);
                // If our API fails for some reason, let Chainlit do its default thing:
                // remove the blockers and re-dispatch the click.
                document.removeEventListener("click", onClick, true);
                target.click();
            }
        } catch { }
    }

    // Also handle Enter/Space on focused New Chat elements for accessibility.
    async function onKeyDown(e) {
        const key = e.key || e.code;
        if (!key || (key !== "Enter" && key !== " ")) return;
        const target =
            e.target.closest('[data-testid], [aria-label], button, a, [role="button"]') ||
            e.target;
        if (!looksLikeNewChat(target)) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        e.stopPropagation();
        try {
            await createThread();
        } catch (err) {
            console.warn("Create thread (kbd) failed; falling back", err);
            document.removeEventListener("keydown", onKeyDown, true);
            target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
        }
    }

    document.addEventListener("click", onClick, true);   // capture
    document.addEventListener("keydown", onKeyDown, true);
})();

/* ---------- History Sidebar (toggleable) ---------- */
(function initSidebar() {
    if (!window.location.pathname.startsWith("/chat")) return;
    if (document.getElementById("pry-sidebar")) return;

    const css = `
  /* Layout & toggle */
  body.pry-with-sidebar #root, body.pry-with-sidebar .cl-root { margin-left: 0; transition: margin-left .2s; }
  #pry-sidebar{position:fixed;left:0;top:0;height:100%;width:290px;background:#101014;color:#e6e6e6;z-index:9999;border-right:1px solid #2a2a2e;transform:translateX(-100%);transition:transform .2s;}
  body.pry-sb-open #pry-sidebar{transform:translateX(0);}
  @media (min-width: 900px){
    body.pry-sb-open #root, body.pry-sb-open .cl-root { margin-left:290px; }
  }

  #pry-sb-toggle{position:fixed;left:10px;top:10px;z-index:10000;background:#15151a;border:1px solid #2a2a2e;color:#ddd;border-radius:8px;padding:6px 10px;font:600 14px system-ui;cursor:pointer}
  #pry-sb-toggle:hover{background:#1a1a20}

  #pry-sidebar header{display:flex;align-items:center;justify-content:space-between;padding:12px;border-bottom:1px solid #2a2a2e;font-weight:600}
  #pry-sidebar .pry-body{padding:12px;display:flex;flex-direction:column;gap:10px}
  #pry-sidebar input.pry-search{width:100%;padding:8px;border:1px solid #2a2a2e;background:#141418;color:#ddd;border-radius:8px;outline:none}
  #pry-sidebar ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px;overflow:auto;max-height:calc(100vh - 146px)}
  #pry-sidebar li{display:flex;align-items:center;gap:8px;justify-content:space-between;padding:8px;border-radius:8px}
  #pry-sidebar li:hover{background:#17171c}
  #pry-sidebar .title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px}
  #pry-sidebar .meta{opacity:.6;font-size:.85em}
  #pry-sidebar .row{display:flex;align-items:center;gap:8px;cursor:pointer}
  #pry-sidebar .icon{opacity:.7}
  #pry-sidebar .rename,.del{opacity:.6;cursor:pointer;padding:4px;border-radius:6px}
  #pry-sidebar .rename:hover,.del:hover{opacity:1;background:#1b1b20}
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
      <input class="pry-search" placeholder="Search chats"/>
      <ul class="pry-list" aria-label="Chat history"></ul>
    </div>`;
    document.body.appendChild(side);

    // Toggle button (default closed)
    const toggle = document.createElement("button");
    toggle.id = "pry-sb-toggle";
    document.body.appendChild(toggle);

    const listEl = side.querySelector(".pry-list");
    const searchEl = side.querySelector(".pry-search");

    function setOpen(open) {
        document.body.classList.toggle("pry-sb-open", !!open);
        toggle.textContent = open ? "✕" : "☰";
        localStorage.setItem("pry_sb_open", open ? "1" : "0");
    }
    setOpen(localStorage.getItem("pry_sb_open") === "1"); // default closed

    toggle.addEventListener("click", () => setOpen(!document.body.classList.contains("pry-sb-open")));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });

    async function api(path, opts) {
        const r = await fetch(path, { credentials: "include", ...opts });
        if (!r.ok) throw new Error(`${r.status}`);
        try { return await r.json(); } catch { return {}; }
    }

    async function refresh() {
        try { render(await api("/ui/threads")); }
        catch (e) { console.warn("History load failed", e); }
    }

    function render(items, q = "") {
        listEl.innerHTML = "";
        const qn = q.trim().toLowerCase();
        (items || [])
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
          <span class="rename" title="Rename">✎</span>
          <span class="del" title="Delete">🗑</span>`;

                // Open
                li.querySelector(".row").addEventListener("click", (ev) => {
                    ev.preventDefault();
                    window.location.assign(`/open/t/${t.thread_id}`);
                });

                // Rename
                li.querySelector(".rename").addEventListener("click", async (ev) => {
                    ev.preventDefault(); ev.stopPropagation();
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

                // Delete
                li.querySelector(".del").addEventListener("click", async (ev) => {
                    ev.preventDefault(); ev.stopPropagation();
                    const name = t.title || t.thread_id.slice(0, 8);
                    if (!confirm(`Delete chat "${name}"? This cannot be undone.`)) return;

                    try { await api(`/ui/threads/${t.thread_id}`, { method: "DELETE" }); } catch { }

                    // If this was the active one, clear cookie & navigate to newest (or create)
                    const url = new URL(window.location.href);
                    const activeId = url.searchParams.get("t");
                    if (activeId === t.thread_id) {
                        try { await api("/ui/clear_thread", { method: "POST" }); } catch { }
                        let items = [];
                        try { items = await api("/ui/threads"); } catch { }
                        if (items.length) { window.location.assign(`/open/t/${items[0].thread_id}`); return; }
                        try {
                            const created = await api("/ui/threads", { method: "POST" });
                            window.location.assign(`/open/t/${created.thread_id}`);
                            return;
                        } catch { }
                    }
                    await refresh();
                });

                listEl.appendChild(li);
            });
    }

    // Search filter
    searchEl.addEventListener("input", async (e) => {
        try { render(await api("/ui/threads"), e.target.value || ""); } catch { }
    });

    // If bookmarked /chat/?t=<id>, convert to /open/t/<id> once (sets cookie first)
    (function coerceBookmark() {
        const url = new URL(window.location.href);
        const tid = url.searchParams.get("t");
        if (!tid) return;
        const key = "pry_tid_applied";
        if (sessionStorage.getItem(key) === tid) return;
        sessionStorage.setItem(key, tid);
        window.location.replace(`/open/t/${tid}`);
    })();

    refresh();
})();

/* ---------- Load profile menu plugin (modular) ---------- */
(function loadProfileMenuPlugin() {
    try {
        if (!location.pathname.startsWith("/chat")) return;
        const s = document.createElement("script");
        s.src = "/chat/public/profile-menu.js";
        s.defer = true;
        document.head.appendChild(s);
    } catch (_) { }
})();