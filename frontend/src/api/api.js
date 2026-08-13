import axios from "axios";

// Backend base URL. The dev server proxies /api -> localhost:5001 (CRA proxy),
// so the browser only ever talks to one origin and the HttpOnly session cookie
// flows automatically. In production set REACT_APP_API_URL to the same-origin
// API path (or a co-origin URL that mirrors cookies).
const API_URL = process.env.REACT_APP_API_URL || "/api";

const getCookie = (name) => {
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = document.cookie.match(new RegExp("(?:^|; )" + esc + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
};

const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// The session token is an HttpOnly cookie - JS never reads it. We only:
// 1) tag requests as coming from the SPA (so the backend keeps the raw JWT
//    out of JSON responses), and
// 2) mirror the double-submit CSRF cookie into a header for state-changing calls.
api.interceptors.request.use((config) => {
  config.headers["X-Requested-With"] = "XMLHttpRequest";
  const method = (config.method || "get").toLowerCase();
  if (!["get", "head", "options", "trace"].includes(method)) {
    const csrf = getCookie("deepguard_csrf");
    if (csrf) config.headers["X-CSRF-TOKEN"] = csrf;
  }
  return config;
});

// Global error handling - surfaces the backend message. A 401 clears the
// session state (the cookie is server-side only) and redirects to login.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.message || "Network error. Please try again.";
    error.message = message;
    if (error.response?.status === 401) {
      window.dispatchEvent(
        new CustomEvent("deepguard:unauthorized", { detail: { message, status: 401 } })
      );
    }
    return Promise.reject(error);
  }
);

export default api;
