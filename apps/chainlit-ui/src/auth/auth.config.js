// 


// apps/chainlit-ui/src/auth/auth.config.js
// Fill with real values from Entra External ID (CIAM)
window.PRYNAI_AUTH = {
    tenantSubdomain: "chatprynai",
    tenantId: "bff9cd6e-5793-4bdc-bffd-0efb12816a81",

    // IMPORTANT: exact user-flow (policy) id from the portal, e.g. "b2c_1_signupsigninv2".
    // If you truly don't want to use a policy in the path, set policy: "" (empty string).
    policy: "b2c_1_signupsigninv2",

    spaClientId: "ae480273-33ea-44be-8875-fcc7b4bcf9b6",
    apiScope: "api://76206f73-e73f-4722-b8b4-f97469fefcdf/chat.fullaccess",
    redirectUri: window.location.origin + "/auth/",
    postLogoutRedirectUri: window.location.origin + "/auth/"
};