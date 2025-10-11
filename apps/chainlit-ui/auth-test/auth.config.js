// apps/chainlit-ui/src/auth/auth.config.js
// Microsoft Entra External ID (CIAM) SPA config.
// IMPORTANT: The discovery document that works in your tenant is the tenant-level one
// (no policy in path): https://<sub>.ciamlogin.com/<tenantId>/v2.0/.well-known/openid-configuration
window.PRYNAI_AUTH = {
    tenantSubdomain: "chatprynai",
    tenantId: "bff9cd6e-5793-4bdc-bffd-0efb12816a81",

    // Kept for reference (we won't use it in the authority since CIAM discovery works tenant-level).
    policy: "SignUpSignIn",

    spaClientId: "ae480273-33ea-44be-8875-fcc7b4bcf9b6",
    apiScope: "api://76206f73-e73f-4722-b8b4-f97469fefcdf/chat.fullaccess",

    // Absolute URLs remove any ambiguity behind proxies.
    redirectUri: window.location.origin + "/auth/",
    postLogoutRedirectUri: window.location.origin + "/auth/"
};
