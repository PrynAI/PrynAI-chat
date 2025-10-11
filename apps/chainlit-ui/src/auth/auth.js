// apps/chainlit-ui/src/auth/auth.js
(async () => {
    const C = window.PRYNAI_AUTH;

    // Tenant-level CIAM authority (works with your discovery URL)
    const authority = `https://${C.tenantSubdomain}.ciamlogin.com/${C.tenantId}/`;

    const msalConfig = {
        auth: {
            clientId: C.spaClientId,
            authority,
            knownAuthorities: [`${C.tenantSubdomain}.ciamlogin.com`],
            redirectUri: C.redirectUri,
            postLogoutRedirectUri: C.postLogoutRedirectUri,
            navigateToLoginRequestUrl: false
        },
        cache: { cacheLocation: "localStorage" }
    };

    const app = new msal.PublicClientApplication(msalConfig);
    const $ = (id) => document.getElementById(id);
    const set = (txt) => { const el = $("status"); if (el) el.textContent = txt; };

    async function saveAccessToken(accessToken) {
        const resp = await fetch("/_auth/token", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
            credentials: "same-origin",
            body: JSON.stringify({ access_token: accessToken })
        });
        return resp.ok;
    }

    async function establishChainlitSession(accessToken) {
        // 1) Preferred in Chainlit 2.x: header-auth endpoint
        let r = await fetch("/chat/auth/header", {
            method: "POST",
            credentials: "include",
            headers: { "Authorization": `Bearer ${accessToken}` }
        });

        // 2) Fallback for older builds that don’t expose /chat/auth/header:
        if (r.status === 404) {
            r = await fetch("/chat/user", {
                method: "GET",
                credentials: "include",
                headers: { "Authorization": `Bearer ${accessToken}` }
            });
        }
        return r.ok;
    }

    function goToChat() {
        // Prevent the /chat/login -> /auth -> /chat loop on first load
        sessionStorage.setItem("pry_auth_just_logged", "1");
        set("Authenticated. Opening chat…");
        window.location.replace("/chat/");
    }

    async function acquireAndBridge(acct) {
        const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct, authority });
        if (!(await saveAccessToken(res.accessToken))) {
            set("Token acquired but saving failed.");
            return;
        }
        if (!(await establishChainlitSession(res.accessToken))) {
            set("Saved token but header auth failed (401). Check server logs.");
            return;
        }
        goToChat();
    }

    try {
        const result = await app.handleRedirectPromise();
        const acct = result?.account || app.getActiveAccount() || app.getAllAccounts()[0];
        if (result?.account && !app.getActiveAccount()) app.setActiveAccount(result.account);
        if (acct) {
            try {
                await acquireAndBridge(acct);
                return;
            } catch (e) {
                console.warn("Silent flow failed; user action required", e);
            }
        }
    } catch (e) {
        console.error("handleRedirectPromise error", e);
        set("Redirect handling failed (see console).");
    }

    $("loginBtn").onclick = async () => {
        try {
            set("Redirecting to sign-in…");
            await app.loginRedirect({ scopes: [C.apiScope], authority });
        } catch (e) {
            console.error("loginRedirect failed", e);
            set(`Login failed: ${e?.errorCode || e?.message || e}`);
        }
    };

    $("tokenBtn").onclick = async () => {
        const acct = app.getActiveAccount() || app.getAllAccounts()[0];
        if (!acct) return set("Sign in first.");
        try { await acquireAndBridge(acct); }
        catch (e) {
            console.warn("Silent failed; falling back to redirect", e);
            await app.acquireTokenRedirect({ scopes: [C.apiScope], authority });
        }
    };

    $("logoutBtn").onclick = async () => {
        try {
            await fetch("/_auth/logout", { method: "POST", credentials: "same-origin" });
            set("Signing out…");
            await app.logoutRedirect({ authority });
        } catch (e) {
            console.error("logoutRedirect failed", e);
            set(`Logout failed: ${e?.errorCode || e?.message || e}`);
        }
    };

    set("Ready.");
})();