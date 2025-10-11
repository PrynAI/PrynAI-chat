// apps/chainlit-ui/src/public/login-redirect.js
(function () {
    try {
        var p = window.location.pathname;
        if (p === "/chat/login") {
            if (sessionStorage.getItem("pry_auth_just_logged") === "1") {
                sessionStorage.removeItem("pry_auth_just_logged");
                return; // allow Chainlit to finish loading
            }
            window.location.replace("/auth/");
        }
    } catch (_) { }
})();