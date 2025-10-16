/* PrynAI — Profile Menu Plugin
   Adds email + Help Center + Release Notes + Subscription into Chainlit's
   avatar dropdown without forking the frontend.

   Safe assumptions:
   - We are mounted at /chat (FastAPI wrapper) and authenticated via cookie.
   - /chat/user returns the Chainlit User object (we used it in auth.js already).
   - header_auth_callback injected email/preferred_username in User.metadata.
*/

(function enhanceProfileMenu() {
    // Only on chat routes.
    if (!location.pathname.startsWith("/chat")) return;

    // Fetch & cache current user (email lives in metadata).
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

    // Minimal styles to match dark header; we avoid depending on internal classnames.
    const STYLE = `
    .pry-menu-item { display:block; padding:8px 12px; text-decoration:none; color:inherit; border-radius:6px; }
    .pry-menu-item:hover { background:#1b1b20; }
    .pry-menu-sep { height:1px; background:#2a2a2e; margin:4px 8px; }
    .pry-menu-email { padding:8px 12px; opacity:.8; font-size:.9em; }
  `;
    function ensureStyleTag() {
        if (document.getElementById("pry-menu-style")) return;
        const s = document.createElement("style");
        s.id = "pry-menu-style";
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    function makeSep() {
        const d = document.createElement("div");
        d.className = "pry-menu-sep";
        return d;
    }
    function makeLink(label, href, target) {
        const a = document.createElement("a");
        a.className = "pry-menu-item";
        a.textContent = label;
        a.href = href;
        a.target = target || "_blank";
        a.rel = "noopener";
        a.setAttribute("role", "menuitem");
        return a;
    }
    function makeEmailItem(email) {
        const d = document.createElement("div");
        d.className = "pry-menu-email";
        d.textContent = email;
        d.setAttribute("role", "menuitem");
        d.setAttribute("aria-disabled", "true");
        return d;
    }

    // Try to locate the dropdown menu element that contains the built-in "Logout".
    function findProfileMenu(root) {
        const candidates = (root || document).querySelectorAll('[role="menu"]');
        for (const el of candidates) {
            const txt = (el.textContent || "").toLowerCase();
            if (txt.includes("logout")) return el;
        }
        return null;
    }

    async function injectInto(menu) {
        if (!menu || menu.dataset.pryProfileMenu === "1") return;
        menu.dataset.pryProfileMenu = "1";
        ensureStyleTag();

        const user = await getUser();
        const email =
            user?.metadata?.email ||
            user?.metadata?.preferred_username ||
            "";

        // Prefer inserting above the Logout item.
        const items = Array.from(menu.querySelectorAll("button, a, div[role='menuitem']"));
        const logout = items.find((x) => /logout/i.test(x.textContent || ""));

        const insertBeforeOrAppend = (node) => {
            if (logout && logout.parentElement === menu) {
                menu.insertBefore(node, logout);
            } else {
                menu.appendChild(node);
            }
        };

        if (email) {
            insertBeforeOrAppend(makeEmailItem(email));
            insertBeforeOrAppend(makeSep());
        }
        insertBeforeOrAppend(makeLink("Help Center", "https://prynai.github.io"));
        insertBeforeOrAppend(makeLink("Release Notes", "https://github.com/PrynAI/PrynAI-chat/releases"));
        insertBeforeOrAppend(makeLink("Subscription", "https://chat.prynai.com/subscription"));
    }

    // Watch for the dropdown being added to the DOM and enhance it once per open.
    const mo = new MutationObserver((mutations) => {
        for (const m of mutations) {
            for (const n of m.addedNodes) {
                if (!(n instanceof Element)) continue;
                const menu = n.matches?.('[role="menu"]') ? n : n.querySelector?.('[role="menu"]');
                if (menu && /logout/i.test(menu.textContent || "")) {
                    injectInto(menu);
                }
            }
        }
    });
    mo.observe(document.body, { childList: true, subtree: true });
})();