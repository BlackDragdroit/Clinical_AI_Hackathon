// Remote test through ngrok's free plan: ngrok answers browser requests that carry neither its cookie nor this
// header with a warning page. Element's API calls carry no cookie, so every same-origin fetch gets the header.
// Served by deploy/public/nginx.conf and added to Element's page there; Element itself is unchanged.
(function () {
  var nativeFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || String(input);
    if (/^https?:/i.test(url) && url.indexOf(location.origin) !== 0) {
      return nativeFetch.call(this, input, init);
    }
    init = init || {};
    var headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
    headers.set("ngrok-skip-browser-warning", "1");
    init.headers = headers;
    return nativeFetch.call(this, input, init);
  };
})();
