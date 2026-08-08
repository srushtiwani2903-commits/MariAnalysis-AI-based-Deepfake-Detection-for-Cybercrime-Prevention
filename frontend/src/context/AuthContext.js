import { createContext, useContext, useEffect, useState } from "react";
import api from "../api/api";

const AuthContext = createContext({});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("deepguard-token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((res) => setUser(res.data.user))
      .catch(() => {
        localStorage.removeItem("deepguard-token");
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const saveSession = (token, user) => {
    localStorage.setItem("deepguard-token", token);
    setToken(token);
    setUser(user);
  };

  const login = async (identifier, password) => {
    const { data } = await api.post("/auth/login", { identifier, password });
    saveSession(data.token, data.user);
    return data;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    saveSession(data.token, data.user);
    return data;
  };

  const logout = () => {
    localStorage.removeItem("deepguard-token");
    setToken(null);
    setUser(null);
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
