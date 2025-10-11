(async () => {
    const C = window.PRYNAI_AUTH;
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
    const set = (id, txt) => { $(id).textContent = txt; };

    try {
        const r = await app.handleRedirectPromise();
        if (r && r.account) app.setActiveAccount(r.account);
    } catch (e) {
        console.error(e);
        set("status", "Redirect handling failed.");
    }

    $("loginBtn").onclick = async () => {
        await app.loginRedirect({ scopes: [C.apiScope] });
    };
    $("logoutBtn").onclick = async () => {
        await app.logoutRedirect();
    };
    $("tokenBtn").onclick = async () => {
        const acct = app.getAllAccounts()[0];
        if (!acct) return set("status", "Sign in first.");
        try {
            const res = await app.acquireTokenSilent({ scopes: [C.apiScope], account: acct });
            // Bridge to server: set HttpOnly cookie so Python can read it
            const ok = await fetch("/auth/token", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ access_token: res.accessToken })
            });
            if (ok.ok) {
                set("status", "Token saved. Redirecting to chat…");
                window.location.href = "/chat/";
            } else {
                set("status", "Saving token failed.");
            }
        } catch (e) {
            console.warn("Silent token failed, doing redirect", e);
            await app.acquireTokenRedirect({ scopes: [C.apiScope] });
        }
    };

    set("status", "Ready.");
})();