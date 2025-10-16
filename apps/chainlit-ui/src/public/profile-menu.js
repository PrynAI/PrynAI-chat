/* apps/chainlit-ui/src/public/profile-menu.js */
(function enhanceProfileMenu() {
    if (!location.pathname.startsWith("/chat")) return;

    let userCached = null;
    async function getUser() {
        if (userCached) return userCached;
        try {
            const r = await fetch("/chat/user", { credentials: "include", cache: "no-store" });
            if (!r.ok) return null;
            userCached = await r.json();
            return userCached;
        } catch {
            return null;
        }
    }

    const STYLE = `
    .pry-menu-item { display:block; padding:8px 12px; text-decoration:none; color:inherit; border-radius:6px; }
    .pry-menu-item:hover { background:#1b1b20; }
    .pry-menu-sep { height:1px; background:#2a2a2e; margin:4px 8px; }
    .pry-menu-email { padding:8px 12px; opacity:.85; font-size:.9em; }
  `;
    function ensureStyleTag() {
        if (document.getElementById("pry-menu-style")) return;
        const s = document.createElement("style");
        s.id = "pry-menu-style";
        s.textContent = STYLE;
        document.head.appendChild(s);
    }
    const sep = () => Object.assign(document.createElement("div"), { className: "pry-menu-sep" });
    const link = (label, href, target) => {
        const a = document.createElement("a");
        a.className = "pry-menu-item";
        a.textContent = label;
        a.href = href;
        a.target = target || "_blank";
        a.rel = "noopener";
        a.setAttribute("role", "menuitem");
        return a;
    };
    const emailItem = (email) => {
        const d = document.createElement("div");
        d.className = "pry-menu-email";
        d.textContent = email;
        d.setAttribute("role", "menuitem");
        d.setAttribute("aria-disabled", "true");
        return d;
    };

    function looksLikeGuidLocalPart(s) {
        // 8-4-4-4-12 hex with hyphens
        return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test((s || "").trim());
    }
    function realEmailOrEmpty(u) {
        const md = (u && u.metadata) || {};
        let e = md.email;
        if (!e && Array.isArray(md.emails) && md.emails.length) e = md.emails[0];
        if (!e || typeof e !== "string" || !e.includes("@")) return "";
        const [local, domain] = e.split("@");
        if ((domain || "").toLowerCase().endsWith("onmicrosoft.com")) return "";
        if (looksLikeGuidLocalPart(local)) return "";
        return e;
    }

    async function injectInto(menu) {
        if (!menu || menu.dataset.pryProfileMenu === "1") return;
        menu.dataset.pryProfileMenu = "1";
        ensureStyleTag();

        const user = await getUser();
        const email = realEmailOrEmpty(user);

        const items = Array.from(menu.querySelectorAll("button, a, div[role='menuitem']"));
        const logout = items.find((x) => /logout/i.test(x.textContent || ""));
        const insert = (node) => (logout && logout.parentElement === menu ? menu.insertBefore(node, logout) : menu.appendChild(node));

        if (email) {
            insert(emailItem(email));
            insert(sep());
        }
        insert(link("Help Center", "https://prynai.github.io"));
        insert(link("Release Notes", "https://github.com/PrynAI/PrynAI-chat/releases"));
        insert(link("Subscription", "https://chat.prynai.com/subscription"));
    }

    const mo = new MutationObserver((muts) => {
        for (const m of muts) {
            for (const n of m.addedNodes) {
                if (!(n instanceof Element)) continue;
                const menu = n.matches?.('[role="menu"]') ? n : n.querySelector?.('[role="menu"]');
                if (menu && /logout/i.test(menu.textContent || "")) injectInto(menu);
            }
        }
    });
    mo.observe(document.body, { childList: true, subtree: true });
})();