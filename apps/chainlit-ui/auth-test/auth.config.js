// auth.config.js — fill with your real values
window.PRYNAI_AUTH = {
    tenantSubdomain: "chatprynai",                    // e.g., contoso
    tenantDomain: "chatprynai.onmicrosoft.com",       // e.g., contoso.onmicrosoft.com
    tenantId:"bff9cd6e-5793-4bdc-bffd-0efb12816a81",
    policy:"SignUpSignIn",           
    spaClientId: "ae480273-33ea-44be-8875-fcc7b4bcf9b6",
    apiScope: "api://76206f73-e73f-4722-b8b4-f97469fefcdf/chat.fullaccess",
    redirectUri: "http://localhost:3000/",                 // must be in SPA app’s Redirect URIs
    postLogoutRedirectUri: "http://localhost:3000/"
};
