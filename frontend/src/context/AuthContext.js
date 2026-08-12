import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/api";

const AuthContext = createContext({});

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5001/api";

// Message the login page shows after a single-session forced logout.
const LOGOUT_MESSAGE = "You have been logged out because your account was signed in on another device.";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("deepguard-token"));
  const [loading, setLoading] = useState(true);
  const streamRef = useRef(null);
  const navigate = useNavigate();

  const clearSession = () => {
    closeStream();
    localStorage.removeItem("deepguard-token");
    sessionStorage.removeItem("deepguard-401-message");
    setToken(null);
    setUser(null);
  };

  const closeStream = () => {
    if (streamRef.current) {
      streamRef.current.abort();
      streamRef.current = null;
    }
  };

  // Single-session enforcement on the frontend:
  // 1) Every 401 from the backend clears local auth state and redirects.
  useEffect(() => {
    const onUnauthorized = (e) => {
      const msg = e?.detail?.message;
      const wasForced = msg && msg.includes("another device");
      closeStream();
      localStorage.removeItem("deepguard-token");
      if (wasForced) {
        // Remember the reason so the login page can display it after redirect.
        sessionStorage.setItem("deepguard-401-message", LOGOUT_MESSAGE);
      } else {
        sessionStorage.removeItem("deepguard-401-message");
      }
      setToken(null);
      setUser(null);
      if (window.location.pathname !== "/login") {
        navigate("/login", { replace: true });
      }
    };
    window.addEventListener("deepguard:unauthorized", onUnauthorized);
    return () => window.removeEventListener("deepguard:unauthorized", onUnauthorized);
  }, [navigate]);

  // 2) Real-time logout: subscribe to the backend SSE stream with the JWT in
  //    an Authorization header (never in the URL). When this account logs in
  //    elsewhere, the server deactivates this session and pushes the event.
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    streamRef.current = controller;
    const started = new Date();

    const connect = async () => {
      try {
        const res = await fetch(`${API_URL}/auth/events`, {
          headers: { Authorization: `Bearer ${token}` },
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
              localStorage.removeItem("deepguard-token");
              setToken(null);
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
  }, [token, navigate]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((res) => setUser(res.data.user))
      .catch(() => clearSession())
      .finally(() => setLoading(false));
  }, [token]);

  const saveSession = (token, user) => {
    sessionStorage.removeItem("deepguard-401-message");
    localStorage.setItem("deepguard-token", token);
    setToken(token);
    setUser(user);
  };

  const login = async (identifier, password) => {
    // Close this tab's stream first so re-login here doesn't kick itself.
    closeStream();
    const { data } = await api.post("/auth/login", { identifier, password });
    saveSession(data.token, data.user);
    return data;
  };

  const register = async (payload) => {
    closeStream();
    const { data } = await api.post("/auth/register", payload);
    if (data.token) {
      saveSession(data.token, data.user);
    }
    return data;
  };

  const logout = () => {
    api.post("/auth/logout").catch(() => {});
    clearSession();
  };

  const refreshUser = async () => {
    const { data } = await api.get("/auth/me");
    setUser(data.user);
    return data.user;
  };

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, register, logout, refreshUser, isAuthenticated: !!token }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
