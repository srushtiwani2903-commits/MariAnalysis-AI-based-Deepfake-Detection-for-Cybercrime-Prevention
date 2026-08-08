import { createContext, useContext, useEffect, useRef, useState } from "react";
import api from "../api/api";

const AuthContext = createContext({});

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5000/api";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("deepguard-token"));
  const [loading, setLoading] = useState(true);
  const esRef = useRef(null);

  const clearSession = () => {
    closeSSE();
    localStorage.removeItem("deepguard-token");
    setToken(null);
    setUser(null);
  };

  const closeSSE = () => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  };

  useEffect(() => {
    const onUnauthorized = () => clearSession();
    window.addEventListener("deepguard:unauthorized", onUnauthorized);
    return () => window.removeEventListener("deepguard:unauthorized", onUnauthorized);
  }, []);

  useEffect(() => {
    if (!token) return;
    // Single-session: if this user logs in anywhere else, this tab is told to
    // log out on the spot (no refresh needed).
    const es = new EventSource(`${API_URL}/auth/events?token=${token}`);
    esRef.current = es;
    es.addEventListener("session_revoked", () => clearSession());
    es.onerror = () => {};
    return () => es.close();
  }, [token]);

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
    localStorage.setItem("deepguard-token", token);
    setToken(token);
    setUser(user);
  };

  const login = async (identifier, password) => {
    // Close this tab's stream first so re-login here doesn't kick itself.
    closeSSE();
    const { data } = await api.post("/auth/login", { identifier, password });
    saveSession(data.token, data.user);
    return data;
  };

  const register = async (payload) => {
    closeSSE();
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
