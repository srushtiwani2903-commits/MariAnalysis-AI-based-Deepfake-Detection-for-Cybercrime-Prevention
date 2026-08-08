import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import FullPageLoader from "./FullPageLoader";

export default function AdminRoute() {
  const { isAuthenticated, loading, user } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return user?.is_admin ? <Outlet /> : <Navigate to="/dashboard" replace />;
}
