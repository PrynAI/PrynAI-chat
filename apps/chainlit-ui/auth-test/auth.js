(async () => {
    const C = window.PRYNAI_AUTH;
    if (!C) throw new Error("Missing PRYNAI_AUTH config");

    // Policy-specific authority (External ID / CIAM uses ciamlogin.com + policy)
    const tenantPath = C.tenantId; // always use the GUID for CIAM
    const authority = `https://${C.tenantSubdomain}.ciamlogin.com/${tenantPath}/`
    
    const msalConfig = {
        auth: {
            clientId: C.spaClientId,
            authority,
            knownAuthorities: [`${C.tenantSubdomain}.ciamlogin.com`], // required for B2C/External ID
            redirectUri: C.redirectUri,
            postLogoutRedirectUri: C.postLogoutRedirectUri
        },
        cache: { cacheLocation: "localStorage" }
    };

    const loginRequest = { scopes: [C.apiScope] };   // ask for API scope up front
    const tokenRequest = { scopes: [C.apiScope] };

    const msalApp = new msal.PublicClientApplication(msalConfig);

    const $ = (id) => document.getElementById(id);
    const set = (id, text) => { $(id).textContent = typeof text === "string" ? text : JSON.stringify(text, null, 2); };
    const status = (cls, msg) => { const el = $("status"); el.className = cls; el.textContent = msg; };

    function getAccount() {
        const accounts = msalApp.getAllAccounts();
        return accounts && accounts.length ? accounts[0] : null;
    }

    async function showState() {
        const acct = getAccount();
        set("acct", acct || "(none)");
        if (acct && acct.idTokenClaims) {
            set("claims", acct.idTokenClaims);
        } else {
            set("claims", "(none)");
        }
    }

    // Handle the redirect back from CIAM (if any)
    try {
        const resp = await msalApp.handleRedirectPromise();
        if (resp && resp.account) {
            msalApp.setActiveAccount(resp.account);
            status("ok", "Signed in.");
        }
    } catch (e) {
        console.error(e);
        status("err", "Redirect handling failed. Check console.");
    }

    // Wire buttons
    $("loginBtn").onclick = async () => {
        const acct = getAccount();
        if (acct) { status("ok", "Already signed in."); await showState(); return; }
        status("warn", "Redirecting to sign-in…");
        await msalApp.loginRedirect(loginRequest);
    };

    $("logoutBtn").onclick = async () => {
        const acct = getAccount();
        await msalApp.logoutRedirect({ account: acct || undefined });
    };

    $("tokenBtn").onclick = async () => {
        const acct = getAccount();
        if (!acct) {
            status("warn", "Sign in first.");
            return;
        }
        try {
            const res = await msalApp.acquireTokenSilent({ ...tokenRequest, account: acct });
            set("token", res.accessToken || "(none)");
            status("ok", "Got access token.");
        } catch (e) {
            console.warn("Silent token failed, doing redirect:", e);
            await msalApp.acquireTokenRedirect(tokenRequest);
        }
    };

    // Initialize view
    await showState();
    if (!getAccount()) status("warn", "Not signed in.");
})();
