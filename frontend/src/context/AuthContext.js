import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/api";

const AuthContext = createContext({});

// Message the login page shows after a single-session forced logout.
const LOGOUT_MESSAGE = "You have been logged out because your account was signed in on another device.";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const streamRef = useRef(null);
  const navigate = useNavigate();

  const clearSession = () => {
    closeStream();
    setUser(null);
  };

  const closeStream = () => {
    if (streamRef.current) {
      streamRef.current.abort();
      streamRef.current = null;
    }
  };

  // Restore the session on load: the JWT lives in an HttpOnly cookie, so the
  // only way to know who we are is to ask the backend.
  useEffect(() => {
    api
      .get("/auth/me")
      .then((res) => setUser(res.data.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // Single-session enforcement on the frontend:
  // Every 401 from the backend clears local auth state and redirects.
  useEffect(() => {
    const onUnauthorized = (e) => {
      const msg = e?.detail?.message;
      const wasForced = msg && msg.includes("another device");
      closeStream();
      if (wasForced) {
        // Remember the reason so the login page can display it after redirect.
        sessionStorage.setItem("deepguard-401-message", LOGOUT_MESSAGE);
      } else {
        sessionStorage.removeItem("deepguard-401-message");
      }
      setUser(null);
      if (window.location.pathname !== "/login") {
        navigate("/login", { replace: true });
      }
    };
    window.addEventListener("deepguard:unauthorized", onUnauthorized);
    return () => window.removeEventListener("deepguard:unauthorized", onUnauthorized);
  }, [navigate]);

  // 2) Real-time logout: subscribe to the backend SSE stream (auth via the
  //    HttpOnly cookie, never in a header/URL). When this account logs in
  //    elsewhere, the server deactivates this session and pushes the event.
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    streamRef.current = controller;
    const started = new Date();

    const connect = async () => {
      try {
        const res = await fetch("/api/auth/events", {
          credentials: "include",
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error("SSE failed");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf("\n\n")) >= 0) {
            const chunk = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            if (chunk.includes("event: session_revoked")) {
              sessionStorage.setItem("deepguard-401-message", LOGOUT_MESSAGE);
              closeStream();
              setUser(null);
              if (window.location.pathname !== "/login") {
                navigate("/login", { replace: true });
              }
              return;
            }
          }
        }
      } catch (err) {
        // Transient network error: retry unless the component unmounted.
        if (!controller.signal.aborted && Date.now() - started < 30000) {
          setTimeout(connect, 3000);
        }
      }
    };

    connect();
    return () => controller.abort();
  }, [user, navigate]);

  const login = async (identifier, password, rememberMe = false) => {
    // Close this tab's stream first so re-login here doesn't kick itself.
    closeStream();
    const { data } = await api.post("/auth/login", { identifier, password, remember_me: rememberMe });
    setUser(data.user);
    return data;
  };

  const register = async (payload) => {
    closeStream();
    const { data } = await api.post("/auth/register", payload);
    setUser(data.user);
    return data;
  };

  const logout = () => {
    api.post("/auth/logout").catch(() => {});
    closeStream();
    setUser(null);
  };

  const refreshUser = async () => {
    const { data } = await api.get("/auth/me");
    setUser(data.user);
    return data.user;
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, refreshUser, isAuthenticated: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
