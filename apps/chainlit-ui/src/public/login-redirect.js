// apps/chainlit-ui/src/public/login-redirect.js
(function () {
    try {
        var p = window.location.pathname;
        if (p === "/chat/login") {
            if (sessionStorage.getItem("pry_auth_just_logged") === "1") {
                sessionStorage.removeItem("pry_auth_just_logged");
                return; // allow Chainlit to finish loading
            }
            window.location.replace("/auth/");
        }
    } catch (_) { }
})();

/* ---------- History Sidebar (New Chat / Search / Chats) ---------- */
(function () {
    // Only render on the chat page
    if (!/\/chat\/?$/.test(window.location.pathname)) return;

    const css = `
  #pry-sidebar{position:fixed;left:0;top:0;height:100%;width:290px;background:#101014;color:#e6e6e6;z-index:9999;border-right:1px solid #2a2a2e;}
  #pry-sidebar header{display:flex;align-items:center;justify-content:space-between;padding:12px 12px;border-bottom:1px solid #2a2a2e;font-weight:600}
  #pry-sidebar .pry-body{padding:12px;display:flex;flex-direction:column;gap:10px}
  #pry-sidebar button.pry-new{width:100%;padding:8px 10px;border:1px dashed #7b5cff;background:transparent;color:#bfa8ff;border-radius:8px;cursor:pointer;font-weight:600}
  #pry-sidebar input.pry-search{width:100%;padding:8px;border:1px solid #2a2a2e;background:#141418;color:#ddd;border-radius:8px;outline:none}
  #pry-sidebar ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px;overflow:auto;max-height:calc(100vh - 170px)}
  #pry-sidebar li{display:flex;align-items:center;gap:8px;justify-content:space-between;padding:8px;border-radius:8px;cursor:pointer}
  #pry-sidebar li:hover{background:#17171c}
  #pry-sidebar .title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:190px}
  #pry-sidebar .meta{opacity:.6;font-size:.85em}
  #pry-sidebar .row{display:flex;align-items:center;gap:8px}
  #pry-sidebar .icon{opacity:.7}
  #pry-sidebar .rename{opacity:.6;cursor:pointer}
  #pry-sidebar .rename:hover{opacity:1}
  body:has(#pry-sidebar) #root, body:has(#pry-sidebar) .cl-root { margin-left: 290px; }`;

    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);

    const side = document.createElement("aside");
    side.id = "pry-sidebar";
    side.innerHTML = `
    <header>
      <span>Chats</span>
      <span class="meta">PrynAI</span>
    </header>
    <div class="pry-body">
      <button class="pry-new">➕ New Chat</button>
      <input class="pry-search" placeholder="Search chats"/>
      <ul class="pry-list" aria-label="Chat history"></ul>
    </div>
  `;
    document.body.appendChild(side);

    const listEl = side.querySelector(".pry-list");
    const searchEl = side.querySelector(".pry-search");
    const newBtn = side.querySelector(".pry-new");

    async function api(path, opts) {
        const r = await fetch(path, { credentials: "include", ...opts });
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
    }

    function render(items, q = "") {
        listEl.innerHTML = "";
        const qn = q.trim().toLowerCase();
        items
            .filter((t) => !qn || (t.title || t.thread_id).toLowerCase().includes(qn))
            .forEach((t) => {
                const li = document.createElement("li");
                li.innerHTML = `
          <div class="row">
            <span class="icon">💬</span>
            <div class="col">
              <div class="title" title="${t.title || t.thread_id}">${t.title || t.thread_id}</div>
              <div class="meta">${(t.updated_at || t.created_at || "").slice(0, 16).replace("T", " ")}</div>
            </div>
          </div>
          <span class="rename" title="Rename">✎</span>
        `;

                // Select thread via deep link (sets cookie server-side and keeps URL)
                li.addEventListener("click", (ev) => {
                    if (ev.target.classList.contains("rename")) return;
                    window.location.href = `/open/t/${t.thread_id}`;
                });

                // Rename
                li.querySelector(".rename").addEventListener("click", async (ev) => {
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

    async function refresh() {
        try {
            const items = await api("/ui/threads");
            render(items);
        } catch (e) {
            console.warn("History load failed", e);
        }
    }

    newBtn.addEventListener("click", async () => {
        const created = await api("/ui/threads", { method: "POST" });
        // Navigate through server deep link so cookie is set before Chainlit loads
        window.location.href = `/open/t/${created.thread_id}`;
    });

    searchEl.addEventListener("input", async (e) => {
        try {
            const items = await api("/ui/threads");
            render(items, e.target.value || "");
        } catch (_) { }
    });

    // Support manual deep-link: /chat/?t=<thread_id>
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
            // reload to ensure header_auth_callback sees cookie on first Chainlit probe
            window.location.replace(`/chat/?t=${tid}`);
        } catch (e) {
            console.warn("Failed to apply deep-link thread id", e);
        }
    })();

    refresh();
})();