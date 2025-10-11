(async () => {
  // Config comes from apps/chainlit-ui/src/auth/auth.config.js
  const C = window.PRYNAI_AUTH;

        // MSAL (CIAM) setup
        const authority = `https://${C.tenantSubdomain}.ciamlogin.com/${C.tenantId}/`;
        const msalConfig = {
            auth: {
            clientId: C.spaClientId,
        authority,
        knownAuthorities: [`${C.tenantSubdomain}.ciamlogin.com`],
        redirectUri: C.redirectUri,           // e.g. "/auth/"
        postLogoutRedirectUri: C.postLogoutRedirectUri
    },
        cache: {cacheLocation: "localStorage" }
  };

        const app = new msal.PublicClientApplication(msalConfig);

  // Small DOM helpers
  const $  = (id) => document.getElementById(id);
  const set = (txt) => {$("status").textContent = txt; };

        // --- helpers to talk to FastAPI wrapper (cookie bridge) ---
        async function saveAccessToken(accessToken) {
    const resp = await fetch("/_auth/token", {
            method: "POST",
        headers: {"Content-Type": "application/json" },
        body: JSON.stringify({access_token: accessToken })
    });
        return resp.ok;
  }

        async function clearCookie() {
    try {await fetch("/_auth/logout", { method: "POST" }); } catch { }
  }

        // Handle the redirect back from CIAM and try to set cookie automatically
        try {
    const r = await app.handleRedirectPromise();
        if (r && r.account) {
            app.setActiveAccount(r.account);
        try {
        const res = await app.acquireTokenSilent({scopes: [C.apiScope], account: r.account });
        if (await saveAccessToken(res.accessToken)) {
            set("Token saved. Redirecting to chat…");
        window.location.href = "/chat/";
        return;
        }
      } catch {
            // ignore here; user can click "Refresh token"
        }
    }
  } catch (e) {
            console.error(e);
        set("Redirect handling failed.");
  }

  // --- Wire up UI buttons ---
  $("loginBtn").onclick = async () => {
            await app.loginRedirect({ scopes: [C.apiScope] });
  };

  $("logoutBtn").onclick = async () => {
            await clearCookie();                 // drop HttpOnly cookie on our domain
        await app.logoutRedirect();          // end CIAM session and return to /auth/
  };

  $("tokenBtn").onclick = async () => {
    const acct = app.getActiveAccount() || app.getAllAccounts()[0];
        if (!acct) return set("Sign in first.");
        try {
      // Best practice: silent first, then interactive fallback
      const res = await app.acquireTokenSilent({scopes: [C.apiScope], account: acct });
        if (await saveAccessToken(res.accessToken)) {
            set("Token saved. Redirecting to chat…");
        window.location.href = "/chat/";
      } else {
            set("Saving token failed.");
      }
    } catch (e) {
            console.warn("Silent token failed; falling back to redirect", e);
        await app.acquireTokenRedirect({scopes: [C.apiScope] });
    }
  };

        set("Ready.");
})();