import axios from "axios";

// Backend base URL. Configure via .env (REACT_APP_API_URL).
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5000/api";

const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("deepguard-token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Global error handling - surfaces the backend message
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.message || "Network error. Please try again.";
    error.message = message;
    if (error.response?.status === 401) {
      localStorage.removeItem("deepguard-token");
    }
    return Promise.reject(error);
  }
);

export default api;
