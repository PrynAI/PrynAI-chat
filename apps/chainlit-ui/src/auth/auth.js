// apps/chainlit-ui/src/auth/auth.js
(async () => {
    const C = window.PRYNAI_AUTH;

    // Preferred: authority includes policy (user-flow). If C.policy is falsy, use tenant-only.
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
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ access_token: accessToken })
        });
        return resp.ok;
    }

    async function clearCookie() {
        try { await fetch("/_auth/logout", { method: "POST", credentials: "same-origin" }); } catch { }
    }

    async function verifyAndGoWithAuth(accessToken) {
        // On this first probe, send Authorization too.
        const r = await fetch("/chat/user", {
            method: "GET",
            credentials: "include",
            headers: accessToken ? { "Authorization": `Bearer ${accessToken}` } : {}
        });
        if (r.status === 200) {
            set("Authenticated. Opening chat…");
            window.location.replace("/chat/");
        } else {
            set(`Saved token but header auth failed (${r.status}). Check server logs.`);
        }
    }

    try {
        const result = await app.handleRedirectPromise();
        const acct = result?.account || app.getActiveAccount() || app.getAllAccounts()[0];

        if (result?.account && !app.getActiveAccount()) {
            app.setActiveAccount(result.account);
        }

        if (acct) {
            try {
                const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct, authority });
                if (await saveAccessToken(res.accessToken)) {
                    await verifyAndGoWithAuth(res.accessToken);
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

    $("logoutBtn").onclick = async () => {
        try {
            await clearCookie();
            set("Signing out…");
            await app.logoutRedirect({ authority });
        } catch (e) {
            console.error("logoutRedirect failed", e);
            set(`Logout failed: ${e?.errorCode || e?.message || e}`);
        }
    };

    $("tokenBtn").onclick = async () => {
        const acct = app.getActiveAccount() || app.getAllAccounts()[0];
        if (!acct) return set("Sign in first.");
        try {
            const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct, authority });
            if (await saveAccessToken(res.accessToken)) {
                await verifyAndGoWithAuth(res.accessToken);
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
