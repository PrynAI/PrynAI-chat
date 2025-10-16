// apps/chainlit-ui/src/public/login-redirect.js
// PrynAI Chat UI glue:
//  - Rebind OOB "New Chat" (create Gateway thread -> /open/t/<id>)
//  - Intercept ANY click to /chat/?t=<id> and reroute to /open/t/<id> (sets cookie first)
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

/* ---------- Utility: detect a thread id in anchors/elements ---------- */
function tidFromElement(el) {
    if (!(el instanceof Element)) return "";
    // <a href="/chat/?t=<uuid>">...</a> or ancestor clickable without href but with data-url
    const href = el.getAttribute?.("href") || el.dataset?.url || "";
    const text = el.textContent || "";
    const tryStr = (s) => {
        const m = s.match(/\/chat\/?\?t=([0-9a-f-]{36})/i);
        return m ? m[1] : "";
    };
    return tryStr(href) || tryStr(text);
}

/* ---------- Rebind OOB "New Chat" (capture earliest) ---------- */
(function rebindNewChat() {
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

/* ---------- Intercept ANY click that would go to /chat/?t=<id> ---------- */
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
                    location.assign(`/open/t/${tid}`); // sets cookie before Chainlit boots
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
                const btns = Array.from(dlg.querySelectorAll("button"));
                const cancel = btns.find((b) => /cancel/i.test(b.textContent || ""));
                try { cancel && cancel.click(); } catch { }
                try { await createThreadAndGo(); } catch { }
            }
        }
    });
    mo.observe(document.body, { childList: true, subtree: true });
})();

/* ---------- Ensure a concrete thread cookie exists on /chat (first load) ---------- */
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
    }).catch(() => {
        sessionStorage.removeItem("pry_boot_tid");
    });
})();

/* ---------- History Sidebar (search/list/rename/delete) ---------- */
// (unchanged, your custom sidebar remains)
(function initSidebar() {
    if (!location.pathname.startsWith("/chat")) return;
    if (document.getElementById("pry-sidebar")) return;
    // ...  << keep your existing sidebar code verbatim >>
})();
(function loadProfileMenuPlugin() {
    try {
        if (!location.pathname.startsWith("/chat")) return;
        const s = document.createElement("script");
        s.src = "/chat/public/profile-menu.js";
        s.defer = true;
        document.head.appendChild(s);
    } catch (_) { }
})();