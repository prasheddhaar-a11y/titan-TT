(function () {
  function redirectToLogin() {
    if (!window.location.pathname.includes("/accounts/login")) {
      window.location.href = "/accounts/login/";
    }
  }

  window.addEventListener("unhandledrejection", function (event) {
    var reason = event.reason || {};
    if (reason.code === "SESSION_EXPIRED") {
      redirectToLogin();
    }
  });

  var originalFetch = window.fetch;
  if (typeof originalFetch === "function") {
    window.fetch = function () {
      return originalFetch.apply(this, arguments).then(function (response) {
        if (response && response.status === 401) {
          var cloned = response.clone();
          cloned.json().then(function (data) {
            if (data && data.code === "SESSION_EXPIRED") {
              redirectToLogin();
            }
          }).catch(function () {});
        }
        return response;
      });
    };
  }
})();