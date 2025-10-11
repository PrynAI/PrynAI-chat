
/* PrynAI — CIAM/MSAL bridge (finalized)
    - Auto-redirects to /chat after login (no manual "Refresh token")
    - Cleanly returns to /auth after logout
    - Robust to redirect loops and query flags
    */
(async () => {
  const C = window.PRYNAI_AUTH;

  // Tenant-level CIAM authority that matches your working discovery URL:
  // https://chatprynai.ciamlogin.com/<tenantId>/v2.0/.well-known/openid-configuration
        const authority = `https://${C.tenantSubdomain}.ciamlogin.com/${C.tenantId}/`;

        const msalConfig = {
            auth: {
            clientId: C.spaClientId,
        authority,
        knownAuthorities: [`${C.tenantSubdomain}.ciamlogin.com`],
        redirectUri: C.redirectUri,
        postLogoutRedirectUri: C.postLogoutRedirectUri, // we'll add a flag dynamically
        navigateToLoginRequestUrl: false
    },
        cache: {cacheLocation: "localStorage" }
  };

        const app = new msal.PublicClientApplication(msalConfig);
  const $ = (id) => document.getElementById(id);
  const set = (txt) => { const el = $("status"); if (el) el.textContent = txt; };

        // ---- helpers --------------------------------------------------------------

        // Remove ?loggedout=1 so we don’t keep thinking we’re "just logged out".
        function stripLoggedOutFlag() {
    const url = new URL(window.location.href);
        if (url.searchParams.has("loggedout")) {
            url.searchParams.delete("loggedout");
        history.replaceState({ }, document.title, url.pathname + (url.search ? "?" + url.searchParams.toString() : "/"));
    }
  }

        async function saveAccessToken(accessToken) {
    const resp = await fetch("/_auth/token", {
            method: "POST",
        headers: {"Content-Type": "application/json", "Cache-Control": "no-store" },
        credentials: "same-origin",
        body: JSON.stringify({access_token: accessToken })
    });
        return resp.ok;
  }

        // Create/verify the Chainlit session before navigating to /chat.
        async function establishChainlitSession(accessToken) {
            // 1) Prefer explicit header-auth (Chainlit 2.x).
            let r = await fetch("/chat/auth/header", {
            method: "POST",
        credentials: "include",
        headers: {"Authorization": `Bearer ${accessToken}` }
    });

        // 2) Verify session exists; keep Authorization for first probe just in case.
        if (r.ok) {
      const v = await fetch("/chat/user", {
            method: "GET",
        credentials: "include",
        headers: {"Authorization": `Bearer ${accessToken}` }
      });
        return v.ok;
    }
        return false;
  }

        function goToChat() {
            // Prevent /chat/login → /auth → /chat loop on first load
            sessionStorage.setItem("pry_auth_just_logged", "1");
        set("Authenticated. Opening chat…");
        window.location.replace("/chat/");
  }

        async function acquireAndBridge(acct) {
    // MSAL pattern: try silent first, fall back to redirect if needed
    const res = await app.acquireTokenSilent({scopes: [C.apiScope], account: acct, authority });
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

        // ---- page bootstrap -------------------------------------------------------

        try {
            stripLoggedOutFlag();

        // Always await redirect resolution before doing anything else.
        // If non-null, this holds fresh tokens + account after loginRedirect.
        const result = await app.handleRedirectPromise();  // MSAL v2 SPA guidance
        const acct = result?.account || app.getActiveAccount() || app.getAllAccounts()[0];
        if (result?.account && !app.getActiveAccount()) app.setActiveAccount(result.account);

        // If we already have an account (cached or just from redirect), auto-bridge.
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

  // ---- buttons --------------------------------------------------------------

  $("loginBtn").onclick = async () => {
    try {
            set("Redirecting to sign-in…");
        await app.loginRedirect({scopes: [C.apiScope], authority });
    } catch (e) {
            console.error("loginRedirect failed", e);
        set(`Login failed: ${e?.errorCode || e?.message || e}`);
    }
  };

  $("tokenBtn").onclick = async () => {
    const acct = app.getActiveAccount() || app.getAllAccounts()[0];
        if (!acct) return set("Sign in first.");
        try {await acquireAndBridge(acct); }
        catch (e) {
            console.warn("Silent failed; falling back to redirect", e);
        await app.acquireTokenRedirect({scopes: [C.apiScope], authority });
    }
  };

  $("logoutBtn").onclick = async () => {
    try {
            // Clear our app cookie immediately (so /chat refuses access).
            await fetch("/_auth/logout", { method: "POST", credentials: "same-origin" });
        set("Signing out…");
        // Tell CIAM to finish signout, then land on /auth?loggedout=1
        await app.logoutRedirect({
            authority,
            account: app.getActiveAccount() || app.getAllAccounts()[0] || undefined,
        postLogoutRedirectUri: C.postLogoutRedirectUri + "?loggedout=1"
      });
    } catch (e) {
            console.error("logoutRedirect failed", e);
        set(`Logout failed: ${e?.errorCode || e?.message || e}`);
    }
  };

        set("Ready.");
})();