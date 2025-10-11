// Fill with real values from Entra External ID (CIAM)
window.PRYNAI_AUTH = {
    tenantSubdomain: "chatprynai",
    tenantId: "bff9cd6e-5793-4bdc-bffd-0efb12816a81",
    policy: "SignUpSignIn",
    spaClientId: "ae480273-33ea-44be-8875-fcc7b4bcf9b6",
    apiScope: "api://76206f73-e73f-4722-b8b4-f97469fefcdf/chat.fullaccess",
    redirectUri: window.location.origin + "/auth/",             // served by the same app
    postLogoutRedirectUri: window.location.origin + "/auth/"
};