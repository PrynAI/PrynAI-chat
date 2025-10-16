// apps/chainlit-ui/src/public/login-redirect.js
// PrynAI Chat UI glue:
//  - Rebind OOB "New Chat" (create Gateway thread -> /open/t/<id>)
//  - Cancel Chainlit's "clear history" modal if it still appears
//  - Ensure a concrete thread cookie exists on first load (bootstrap)
//  - Sidebar: history/search/rename/delete (unchanged)
//  - 401/403 from /ui/* -> redirect to /auth (token refresh)

(function redirectChatLoginToAuth() {
    try {
        if (location.pathname === "/chat/login") {
            if (sessionStorage.getItem("pry_auth_just_logged") === "1") {
                sessionStorage.removeItem("pry_auth_just_logged");
                return;
            }
            location.replace("/auth/");
        }
    } catch (_) { }
})();

/* ---------- helpers ---------- */
async function apiAuthAware(path, opts) {
    const r = await fetch(path, { credentials: "include", cache: "no-store", ...opts });
    if (r.status === 401 || r.status === 403) {
        location.assign("/auth/");
        throw new Error(`auth_${r.status}`);
    }
    if (!r.ok) throw new Error(`${r.status}`);
    try { return await r.json(); } catch { return {}; }
}
function cookieGet(name) {
    const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return m ? decodeURIComponent(m[1]) : "";
}

/* ---------- new-thread flow ---------- */
async function createThreadAndGo() {
    const r = await fetch("/ui/threads", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const t = await r.json();
    if (t && t.thread_id) {
        // Sets prynai_tid via server then Chainlit boots on that id
        location.assign(`/open/t/${t.thread_id}`);
        return true;
    }
    return false;
}

/* ---------- Rebind OOB "New Chat" (capture earliest) ---------- */
(function rebindNewChat() {
    // Decide whether an element or any ancestor in the event path looks like New Chat
    const isNewChatLabel = (s) =>
        (s || "").replace(/[+]/g, "").replace(/\s+/g, " ").trim().toLowerCase() === "new chat";
    function pathLooksLikeNewChat(ev) {
        const path = (ev.composedPath && ev.composedPath()) || [];
        for (const el of path) {
            if (!(el instanceof Element)) continue;
            const aria = (el.getAttribute("aria-label") || "").toLowerCase();
            const testid = (el.getAttribute("data-testid") || "").toLowerCase();
            const txt = (el.textContent || "").toLowerCase();
            if (isNewChatLabel(aria) || /new[_\-\s]?chat/.test(testid) || isNewChatLabel(txt)) return true;
            // A few common synonyms Chainlit has used
            if (/create new chat|start new chat|reset chat/.test(aria) || /create new chat/.test(txt)) return true;
        }
        return false;
    }

    async function intercept(ev) {
        try {
            if (!pathLooksLikeNewChat(ev)) return;
            ev.preventDefault?.();
            ev.stopImmediatePropagation?.();
            ev.stopPropagation?.();
            try {
                await createThreadAndGo();
            } catch (err) {
                console.warn("Create thread failed; letting default New Chat proceed", err);
                document.removeEventListener("pointerdown", intercept, true);
                document.removeEventListener("click", intercept, true);
                document.removeEventListener("keydown", intercept, true);
                // Re-dispatch original event so the app isn't stuck
                setTimeout(() => {
                    if (ev.type === "keydown") {
                        const k = new KeyboardEvent("keydown", { key: ev.key || "Enter", bubbles: true });
                        (ev.target || document.body).dispatchEvent(k);
                    } else {
                        const c = new MouseEvent("click", { bubbles: true });
                        (ev.target || document.body).dispatchEvent(c);
                    }
                }, 0);
            }
        } catch { }
    }

    // Chainlit opens confirm on pointerdown; capture phase
    document.addEventListener("pointerdown", intercept, true);
    document.addEventListener("click", intercept, true);
    document.addEventListener("keydown", (e) => {
        const key = e.key || e.code;
        if (key !== "Enter" && key !== " ") return;
        intercept(e);
    }, true);
})();

/* ---------- Modal watchdog (cancel "Create New Chat" dialog if it sneaks in) ---------- */
(function watchForNewChatModal() {
    const mo = new MutationObserver(async (muts) => {
        for (const m of muts) {
            for (const n of m.addedNodes) {
                if (!(n instanceof Element)) continue;
                const dlg = n.matches?.('[role="dialog"]') ? n : n.querySelector?.('[role="dialog"]');
                if (!dlg) continue;
                const text = (dlg.textContent || "").toLowerCase();
                if (!/create new chat/.test(text)) continue;
                // Click "Cancel" if present to dismiss Chainlit's confirm
                const btns = Array.from(dlg.querySelectorAll("button"));
                const cancel = btns.find((b) => /cancel/i.test(b.textContent || ""));
                try { cancel && cancel.click(); } catch { }
                // Now run our new-thread flow
                try { await createThreadAndGo(); } catch { }
            }
        }
    });
    mo.observe(document.body, { childList: true, subtree: true });
})();

/* ---------- Ensure a concrete thread cookie exists on /chat (first load) ---------- */
(function bootstrapThreadCookieIfMissing() {
    if (!location.pathname.startsWith("/chat")) return;
    if (cookieGet("prynai_tid")) return;               // already have an active thread cookie
    if (sessionStorage.getItem("pry_boot_tid") === "1") return; // guard against loops
    sessionStorage.setItem("pry_boot_tid", "1");
    // Use newest thread; if none exist yet, the first message will create one.
    apiAuthAware("/ui/threads").then((items) => {
        if (Array.isArray(items) && items.length) {
            location.replace(`/open/t/${items[0].thread_id}`);
        } else {
            sessionStorage.removeItem("pry_boot_tid"); // allow another try later
        }
    }).catch(() => {
        sessionStorage.removeItem("pry_boot_tid");
    });
})();

/* ---------- History Sidebar (search/list/rename/delete) ---------- */
(function initSidebar() {
    if (!location.pathname.startsWith("/chat")) return;
    if (document.getElementById("pry-sidebar")) return;

    const css = `
  body.pry-with-sidebar #root, body.pry-with-sidebar .cl-root { margin-left: 0; transition: margin-left .2s; }
  #pry-sidebar{position:fixed;left:0;top:0;height:100%;width:290px;background:#101014;color:#e6e6e6;z-index:9999;border-right:1px solid #2a2a2e;transform:translateX(-100%);transition:transform .2s;}
  body.pry-sb-open #pry-sidebar{transform:translateX(0);}
  @media (min-width: 900px){ body.pry-sb-open #root, body.pry-sb-open .cl-root { margin-left:290px; } }
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
    setOpen(localStorage.getItem("pry_sb_open") === "1");
    toggle.addEventListener("click", () => setOpen(!document.body.classList.contains("pry-sb-open")));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });

    async function refresh() {
        try { render(await apiAuthAware("/ui/threads")); }
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

                li.querySelector(".row").addEventListener("click", (ev) => {
                    ev.preventDefault();
                    location.assign(`/open/t/${t.thread_id}`);  // sets cookie then reload
                });
                li.querySelector(".rename").addEventListener("click", async (ev) => {
                    ev.preventDefault(); ev.stopPropagation();
                    const cur = t.title || "";
                    const next = (prompt("Rename chat:", cur) || "").trim();
                    if (next && next !== cur) {
                        await apiAuthAware(`/ui/threads/${t.thread_id}`, {
                            method: "PUT",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ title: next }),
                        });
                        await refresh();
                    }
                });
                li.querySelector(".del").addEventListener("click", async (ev) => {
                    ev.preventDefault(); ev.stopPropagation();
                    const name = t.title || t.thread_id.slice(0, 8);
                    if (!confirm(`Delete chat "${name}"? This cannot be undone.`)) return;
                    try { await apiAuthAware(`/ui/threads/${t.thread_id}`, { method: "DELETE" }); } catch { }
                    try { await apiAuthAware("/ui/clear_thread", { method: "POST" }); } catch { }
                    let items = [];
                    try { items = await apiAuthAware("/ui/threads"); } catch { }
                    if (items.length) { location.assign(`/open/t/${items[0].thread_id}`); return; }
                    try {
                        const created = await apiAuthAware("/ui/threads", { method: "POST" });
                        location.assign(`/open/t/${created.thread_id}`); return;
                    } catch { }
                    await refresh();
                });

                listEl.appendChild(li);
            });
    }
    searchEl.addEventListener("input", async (e) => {
        try { render(await apiAuthAware("/ui/threads"), e.target.value || ""); } catch { }
    });

    // If user bookmarked /chat/?t=<id>, convert to /open/t/<id> once (set cookie first)
    (function coerceBookmark() {
        const url = new URL(location.href);
        const tid = url.searchParams.get("t");
        if (!tid) return;
        const key = "pry_tid_applied";
        if (sessionStorage.getItem(key) === tid) return;
        sessionStorage.setItem(key, tid);
        location.replace(`/open/t/${tid}`);
    })();

    refresh();
})();

/* ---------- small plugin: profile menu ---------- */
(function loadProfileMenuPlugin() {
    try {
        if (!location.pathname.startsWith("/chat")) return;
        const s = document.createElement("script");
        s.src = "/chat/public/profile-menu.js";
        s.defer = true;
        document.head.appendChild(s);
    } catch (_) { }
})();