import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import FullPageLoader from "./FullPageLoader";

export default function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />;
}
