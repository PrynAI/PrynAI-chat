// apps/chainlit-ui/src/auth/auth.js
(async () => {
    const C = window.PRYNAI_AUTH;

    // Tenant-level CIAM authority that matches discovery working in your tenant
    // e.g. https://chatprynai.ciamlogin.com/bff9cd6e-.../v2.0/.well-known/openid-configuration
    const authority = `https://${C.tenantSubdomain}.ciamlogin.com/${C.tenantId}/`;

    const msalConfig = {
        auth: {
            clientId: C.spaClientId,
            authority,
            knownAuthorities: [`${C.tenantSubdomain}.ciamlogin.com`],
            redirectUri: C.redirectUri,
            postLogoutRedirectUri: C.postLogoutRedirectUri, // we’ll override per-call on logout to stamp ?loggedout=1
            navigateToLoginRequestUrl: false
        },
        cache: { cacheLocation: "localStorage" }
    };

    const app = new msal.PublicClientApplication(msalConfig);
    const $ = (id) => document.getElementById(id);
    const set = (txt) => { const el = $("status"); if (el) el.textContent = txt; };

    // --- Helpers --------------------------------------------------------------

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

    async function establishChainlitSession(accessToken) {
        // 1) Preferred: explicitly create Chainlit session via header-auth endpoint.
        let r = await fetch("/chat/auth/header", {
            method: "POST",
            credentials: "include",
            headers: { "Authorization": `Bearer ${accessToken}` }
        });
        // 2) Verify the session exists (and prime the UI) before we navigate.
        //    On this GET we still send Authorization as a belt-and-suspenders.
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
        // Prevent /chat/login -> /auth -> /chat loop
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

    // --- Page bootstrap -------------------------------------------------------

    try {
        // If this is the post-logout SPA load, do NOT auto-login silently.
        if (justLoggedOut()) {
            set("Signed out. Click Sign in to continue.");
            return;
        }

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
            // Clear our app cookie immediately
            await fetch("/_auth/logout", { method: "POST", credentials: "same-origin" });
            // Mark this navigation so we skip silent login on /auth
            sessionStorage.setItem("pry_logged_out", "1");
            set("Signing out…");
            // Hint MSAL/CIAM which account to end and land on /auth?loggedout=1
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