// PrynAI Chat UI glue :
// 1) Rebind OOB "New Chat" to Gateway threads -> /open/t/<id>
// 2) Intercept ANY navigation to /chat/?t=<id> -> /open/t/<id> (cookie first)
// 3) Cancel Chainlit's "Create New Chat" modal
// 4) Ensure a concrete thread cookie exists on first load
// 5) Sidebar (search/list/rename/delete), closed by default
// 6) 401/403 from /ui/* -> /auth (re-login)

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
function fmt(ts) {
    if (!ts) return "";
    try { return new Date(ts).toISOString().replace("T", " ").slice(0, 16); } catch { return ""; }
}
function el(tag, attrs = {}, children = []) {
    const x = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
        if (k === "class") x.className = v;
        else if (k === "style") x.setAttribute("style", v);
        else x.setAttribute(k, v);
    });
    (Array.isArray(children) ? children : [children]).forEach(c => {
        if (c == null) return;
        if (typeof c === "string") x.appendChild(document.createTextNode(c));
        else x.appendChild(c);
    });
    return x;
}

/* ---------- new-thread flow ---------- */
async function createThreadAndGo() {
    const r = await fetch("/ui/threads", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" }
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const t = await r.json();
    if (t && t.thread_id) {
        location.assign(`/open/t/${t.thread_id}`); // sets prynai_tid cookie, then /chat/?t=<id>
        return true;
    }
    return false;
}

/* ---------- detect a thread id in anchors/elements ---------- */
function tidFromElement(el) {
    if (!(el instanceof Element)) return "";
    const href = el.getAttribute?.("href") || el.dataset?.url || "";
    const text = el.textContent || "";
    const tryStr = (s) => {
        const m = s.match(/\/chat\/?\?t=([0-9a-f-]{36})/i);
        return m ? m[1] : "";
    };
    return tryStr(href) || tryStr(text);
}

/* ---------- Rebind OOB "New Chat" ---------- */
(function rebindNewChat() {
    const isNewChatLabel = (s) =>
        (s || "").replace(/[+]/g, "").replace(/\s+/g, " ").trim().toLowerCase() === "new chat";

    function looksLikeNewChat(ev) {
        const path = (ev.composedPath && ev.composedPath()) || [];
        for (const el of path) {
            if (!(el instanceof Element)) continue;
            const aria = (el.getAttribute("aria-label") || "").toLowerCase();
            const testid = (el.getAttribute("data-testid") || "").toLowerCase();
            const txt = (el.textContent || "").toLowerCase();
            if (isNewChatLabel(aria) || /new[_\-\s]?chat/.test(testid) || isNewChatLabel(txt)) return true;
            if (/create new chat|start new chat|reset chat/.test(aria) || /create new chat/.test(txt)) return true;
        }
        return false;
    }

    async function intercept(ev) {
        try {
            if (!looksLikeNewChat(ev)) return;
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

    document.addEventListener("pointerdown", intercept, true);
    document.addEventListener("click", intercept, true);
    document.addEventListener("keydown", (e) => {
        const key = e.key || e.code;
        if (key !== "Enter" && key !== " ") return;
        intercept(e);
    }, true);
})();

/* ---------- Intercept any click to /chat/?t=<id> ---------- */
(function interceptThreadOpens() {
    function handler(ev) {
        try {
            const path = (ev.composedPath && ev.composedPath()) || [];
            for (const el of path) {
                const tid = tidFromElement(el);
                if (tid) {
                    ev.preventDefault?.();
                    ev.stopImmediatePropagation?.();
                    ev.stopPropagation?.();
                    location.assign(`/open/t/${tid}`); // set cookie before Chainlit boots
                    return;
                }
            }
        } catch { }
    }
    document.addEventListener("pointerdown", handler, true);
    document.addEventListener("click", handler, true);
    document.addEventListener("keydown", (e) => {
        const key = e.key || e.code;
        if (key !== "Enter" && key !== " ") return;
        handler(e);
    }, true);
})();

/* ---------- Cancel "Create New Chat" modal if Chainlit shows it ---------- */
(function watchForNewChatModal() {
    const mo = new MutationObserver(async (muts) => {
        for (const m of muts) {
            for (const n of m.addedNodes) {
                if (!(n instanceof Element)) continue;
                const dlg = n.matches?.('[role="dialog"]') ? n : n.querySelector?.('[role="dialog"]');
                if (!dlg) continue;
                const text = (dlg.textContent || "").toLowerCase();
                if (!/create new chat/.test(text)) continue;
                const btns = Array.from(dlg.querySelectorAll("button"));
                const cancel = btns.find((b) => /cancel/i.test(b.textContent || ""));
                try { cancel && cancel.click(); } catch { }
                try { await createThreadAndGo(); } catch { }
            }
        }
    });
    mo.observe(document.body, { childList: true, subtree: true });
})();

/* ---------- Ensure a thread cookie exists on first load ---------- */
(function bootstrapThreadCookieIfMissing() {
    if (!location.pathname.startsWith("/chat")) return;
    if (cookieGet("prynai_tid")) return;
    if (sessionStorage.getItem("pry_boot_tid") === "1") return;
    sessionStorage.setItem("pry_boot_tid", "1");
    apiAuthAware("/ui/threads").then((items) => {
        if (Array.isArray(items) && items.length) {
            location.replace(`/open/t/${items[0].thread_id}`);
        } else {
            sessionStorage.removeItem("pry_boot_tid");
        }
    }).catch(() => sessionStorage.removeItem("pry_boot_tid"));
})();

/* ---------- Sidebar: history/search/rename/delete ---------- */
(function initSidebar() {
    if (!location.pathname.startsWith("/chat")) return;
    if (document.getElementById("pry-sidebar")) return;

    // Root + toggle
    const root = el("aside", {
        id: "pry-sidebar",
        style:
            "position:fixed;left:0;top:0;bottom:0;width:320px;z-index:40;background:var(--background);" +
            "border-right:1px solid rgba(255,255,255,0.08);transform:translateX(-100%);transition:transform .2s ease"
    });
    const toggle = el("button", {
        id: "pry-sidebar-toggle",
        style:
            "position:fixed;left:8px;top:8px;z-index:41;padding:6px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);" +
            "background:rgba(0,0,0,.3);backdrop-filter:blur(6px);cursor:pointer"
    }, "☰");

    function openSidebar(v) {
        root.style.transform = v ? "translateX(0)" : "translateX(-100%)";
        sessionStorage.setItem("pry_sidebar_open", v ? "1" : "0");
    }
    toggle.addEventListener("click", () => openSidebar(root.style.transform !== "translateX(0)"));
    openSidebar(sessionStorage.getItem("pry_sidebar_open") === "1"); // closed by default

    // Header + search box
    const header = el("div", { style: "display:flex;align-items:center;gap:8px;padding:12px 10px;font-weight:600" }, [
        el("span", {}, "PrynAI"),
        el("div", { style: "flex:1" }),
    ]);
    const search = el("input", {
        type: "text",
        placeholder: "Search chats",
        style:
            "margin:8px 10px 6px 10px;width:calc(100% - 20px);padding:8px 10px;border-radius:8px;" +
            "border:1px solid rgba(255,255,255,0.12);background:transparent;color:inherit"
    });
    const list = el("div", { id: "pry-thread-list", style: "overflow:auto;position:absolute;top:86px;bottom:0;left:0;right:0" });

    root.appendChild(header);
    root.appendChild(search);
    root.appendChild(list);
    document.body.appendChild(root);
    document.body.appendChild(toggle);

    let items = [];
    async function load() {
        try { items = await apiAuthAware("/ui/threads"); render(); } catch (e) { console.warn(e); }
    }
    function row(item) {
        const rowEl = el("div", {
            class: "pry-row",
            style: "display:flex;gap:8px;align-items:center;padding:10px 12px;cursor:pointer"
        }, [
            el("div", { style: "opacity:.8" }, "💬"),
            el("div", { style: "flex:1;min-width:0" }, [
                el("div", { style: "white-space:nowrap;overflow:hidden;text-overflow:ellipsis" }, item.title || "(Untitled)"),
                el("div", { style: "opacity:.6;font-size:12px" }, fmt(item.updated_at || item.created_at))
            ]),
            el("button", { title: "Rename", style: "opacity:.6" }, "✎"),
            el("button", { title: "Delete", style: "opacity:.6" }, "🗑")
        ]);

        // open
        rowEl.addEventListener("click", (e) => {
            if (e.target.tagName === "BUTTON") return;
            location.assign(`/open/t/${item.thread_id}`);
        });

        // rename
        rowEl.querySelectorAll("button")[0].addEventListener("click", async (e) => {
            e.stopPropagation();
            const title = prompt("Rename chat", item.title || "");
            if (title == null) return;
            try {
                await apiAuthAware(`/ui/threads/${item.thread_id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    credentials: "include",
                    body: JSON.stringify({ title })
                });
                await load();
            } catch (err) { console.warn(err); }
        });

        // delete
        rowEl.querySelectorAll("button")[1].addEventListener("click", async (e) => {
            e.stopPropagation();
            if (!confirm("Delete this chat?")) return;
            try {
                await apiAuthAware(`/ui/threads/${item.thread_id}`, { method: "DELETE", credentials: "include" });
                // if deleting active thread, clear cookie to avoid reload loop
                if (cookieGet("prynai_tid") === item.thread_id) {
                    await apiAuthAware("/ui/clear_thread", { method: "POST" });
                }
                await load();
            } catch (err) { console.warn(err); }
        });

        return rowEl;
    }
    function render() {
        const q = (search.value || "").toLowerCase();
        list.innerHTML = "";
        const filtered = items
            .filter((x) => (x.title || "").toLowerCase().includes(q))
            .sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at));
        filtered.forEach((it) => list.appendChild(row(it)));
    }
    search.addEventListener("input", render);
    load();
})();

/* ---------- Profile menu plugin ---------- */
(function loadProfileMenuPlugin() {
    try {
        if (!location.pathname.startsWith("/chat")) return;
        const s = document.createElement("script");
        s.src = "/chat/public/profile-menu.js";
        s.defer = true;
        document.head.appendChild(s);
    } catch (_) { }
})();