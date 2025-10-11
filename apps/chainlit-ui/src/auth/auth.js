/* global msal */
(async () => {
    const C = window.PRYNAI_AUTH;

    // CIAM authority that matches your tenant-level discovery.
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

    // When we land here FROM Chainlit logout, redirect carries ?loggedout=1.
    function justLoggedOut() {
        const p = new URLSearchParams(location.search);
        if (p.get("loggedout") === "1") return true;
        if (sessionStorage.getItem("pry_logged_out") === "1") {
            sessionStorage.removeItem("pry_logged_out");
            return true;
        }
        return false;
    }

    async function saveAccessToken(accessToken) {
        const resp = await fetch("/_auth/token", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
            credentials: "same-origin",
            body: JSON.stringify({ access_token: accessToken })
        });
        return resp.ok;
    }

    // Create Chainlit session now, and verify before navigation.
    async function establishChainlitSession(accessToken) {
        let r = await fetch("/chat/auth/header", {
            method: "POST",
            credentials: "include",
            headers: { "Authorization": `Bearer ${accessToken}` }
        });
        if (r.ok) {
            const v = await fetch("/chat/user", {
                method: "GET",
                credentials: "include",
                headers: { "Authorization": `Bearer ${accessToken}` }
            });
            return v.ok;
        }
        return false;
    }

    function goToChat() {
        // Prevent /chat/login -> /auth -> /chat loop on that first load
        sessionStorage.setItem("pry_auth_just_logged", "1");
        set("Authenticated. Opening chat…");
        // Clean any residual query/hash from MSAL
        try { window.history.replaceState({}, "", "/auth/"); } catch { }
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

    // ---------- Page bootstrap ----------
    try {
        // If we reached here after logout, do nothing until the user clicks "Sign in".
        if (justLoggedOut()) {
            set("Signed out. Click Sign in to continue.");
            return;
        }

        // MUST run on every load with redirect flows.
        const result = await app.handleRedirectPromise();
        const acct = result?.account || app.getActiveAccount() || app.getAllAccounts()[0];
        if (result?.account && !app.getActiveAccount()) app.setActiveAccount(result.account);

        // If we have an account, silently acquire and bridge now.
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
            // Mark so /auth won’t auto-silent log back in
            sessionStorage.setItem("pry_logged_out", "1");
            set("Signing out…");
            const account = app.getActiveAccount() || app.getAllAccounts()[0] || undefined;
            await app.logoutRedirect({
                authority,
                account,
                postLogoutRedirectUri: C.postLogoutRedirectUri + "?loggedout=1"
            });
        } catch (e) {
            console.error("logoutRedirect failed", e);
            set(`Logout failed: ${e?.errorCode || e?.message || e}`);
        }
    };

    set("Ready.");
})();