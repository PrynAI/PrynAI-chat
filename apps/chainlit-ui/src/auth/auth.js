// apps/chainlit-ui/src/auth/auth.js
(async () => {
    const C = window.PRYNAI_AUTH;

    // Your tenant-level CIAM authority (no policy segment).
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

    function goToChat() {
        set("Authenticated. Opening chat…");
        window.location.replace("/chat/");
    }

    async function refreshSilentlyAndGo() {
        const acct = app.getActiveAccount() || app.getAllAccounts()[0];
        if (!acct) return set("Sign in first.");
        try {
            const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct, authority });
            if (await saveAccessToken(res.accessToken)) {
                goToChat();
            } else {
                set("Saving token failed.");
            }
        } catch (e) {
            console.warn("Silent failed; falling back to redirect", e);
            await app.acquireTokenRedirect({ scopes: [C.apiScope], authority });
        }
    }

    try {
        // Complete any redirect, then try silent token (fresh or cached).
        const result = await app.handleRedirectPromise();
        const acct = result?.account || app.getActiveAccount() || app.getAllAccounts()[0];
        if (result?.account && !app.getActiveAccount()) app.setActiveAccount(result.account);
        if (acct) {
            try {
                const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct, authority });
                if (await saveAccessToken(res.accessToken)) {
                    goToChat();
                    return;
                }
                set("Token acquired but saving failed.");
            } catch (e) {
                console.warn("Silent token failed; user action required", e);
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

    $("tokenBtn").onclick = refreshSilentlyAndGo;

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