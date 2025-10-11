// apps/chainlit-ui/src/public/login-redirect.js
(function () {
    try {
        var p = window.location.pathname;
        // Only redirect the built-in Chainlit login page
        if (p === "/chat/login") {
            window.location.replace("/auth/");
        }
    } catch (_) { }
})();