// apps/chainlit-ui/src/auth/auth.js
(async () => {
    const C = window.PRYNAI_AUTH;

    // IMPORTANT: include the user flow (policy) in authority for CIAM/B2C
    const authority = `https://${C.tenantSubdomain}.ciamlogin.com/${C.tenantId}/`;
    const msalConfig = {
        auth: {
            clientId: C.spaClientId,
            authority,
            knownAuthorities: [`${C.tenantSubdomain}.ciamlogin.com`],
            redirectUri: C.redirectUri,
            postLogoutRedirectUri: C.postLogoutRedirectUri
        },
        cache: { cacheLocation: "localStorage" }
    };

    const app = new msal.PublicClientApplication(msalConfig);

    const $ = (id) => document.getElementById(id);
    const set = (txt) => { $("status").textContent = txt; };

    async function saveAccessToken(accessToken) {
        const resp = await fetch("/_auth/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // same-origin by default, explicit is fine
            credentials: "same-origin",
            body: JSON.stringify({ access_token: accessToken })
        });
        return resp.ok;
    }

    async function clearCookie() {
        try { await fetch("/_auth/logout", { method: "POST", credentials: "same-origin" }); } catch { }
    }

    async function verifyAndGo() {
        // Chainlit checks header auth at /chat/user. 200 => cookie recognized.
        const r = await fetch("/chat/user", { method: "GET", credentials: "include" });
        if (r.status === 200) {
            set("Authenticated. Opening chat…");
            window.location.replace("/chat/");
        } else {
            set(`Saved token but header auth failed (${r.status}).`);
        }
    }

    // --- Redirect handler then silent fallback ---
    try {
        const result = await app.handleRedirectPromise();
        let account = result?.account || app.getActiveAccount() || app.getAllAccounts()[0];

        if (result?.account && !app.getActiveAccount()) {
            app.setActiveAccount(result.account);
        }
        if (account) {
            try {
                const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account, authority });
                if (await saveAccessToken(res.accessToken)) {
                    await verifyAndGo();
                    return;
                }
            } catch { /* stay on page; user can click Sign in / Refresh */ }
        }
    } catch (e) {
        console.error("handleRedirectPromise error", e);
        set("Redirect handling failed.");
    }

    $("loginBtn").onclick = async () => {
        await app.loginRedirect({ scopes: [C.apiScope], authority });
    };

    $("logoutBtn").onclick = async () => {
        await clearCookie();
        await app.logoutRedirect({ authority });
    };

    $("tokenBtn").onclick = async () => {
        const acct = app.getActiveAccount() || app.getAllAccounts()[0];
        if (!acct) return set("Sign in first.");
        try {
            const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct, authority });
            if (await saveAccessToken(res.accessToken)) {
                await verifyAndGo();
            } else {
                set("Saving token failed.");
            }
        } catch (e) {
            console.warn("Silent failed; falling back to redirect", e);
            await app.acquireTokenRedirect({ scopes: [C.apiScope], authority });
        }
    };

    set("Ready.");
})();
