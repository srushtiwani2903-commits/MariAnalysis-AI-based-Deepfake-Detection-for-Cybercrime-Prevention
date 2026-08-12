import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  SunIcon,
  MoonIcon,
  UserIcon,
  ArrowRightOnRectangleIcon,
  Bars3Icon,
  XMarkIcon,
  ChartBarIcon,
  ClockIcon,
  BeakerIcon,
  ShieldExclamationIcon,
  VideoCameraIcon,
  FingerPrintIcon,
  BuildingOffice2Icon,
} from "@heroicons/react/24/outline";
import { useTheme } from "../context/ThemeContext";
import { useAuth } from "../context/AuthContext";
import { useLanguage } from "../context/LanguageContext";

const navLinks = [
  { to: "/verify", label: "Verify Proof", icon: ShieldExclamationIcon, protected: false },
  { to: "/dashboard", labelKey: "dashboard", icon: ChartBarIcon, protected: true },
  { to: "/detect", label: "Scan", icon: BeakerIcon, protected: true },
  { to: "/detect/realtime", label: "Live Cam", icon: VideoCameraIcon, protected: true },
  { to: "/history", labelKey: "history", icon: ClockIcon, protected: true },
  { to: "/evidence", label: "Report Fraud", icon: FingerPrintIcon, protected: true },
  { to: "/org-dashboard", label: "Org View", icon: BuildingOffice2Icon, protected: true },
];

export default function Navbar() {
  const { dark, toggle } = useTheme();
  const { user, logout, isAuthenticated } = useAuth();
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const navigate = useNavigate();

  const filtered = navLinks.filter(
    (l) => !l.protected || isAuthenticated
  );

  const handleLogout = () => {
    logout();
    setOpen(false);
    navigate("/");
  };

  return (
    <header className="sticky top-0 z-50 glass-strong border-b border-slate-200 dark:border-white/10">
      <nav className="container-app flex items-center justify-between h-16">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 group">
          <span className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-neon-blue to-neon-purple text-white">
            <ShieldExclamationIcon className="w-5 h-5" />
          </span>
          <span className="font-bold text-lg tracking-tight">
            Mari<span className="neon-text">Analysis</span>
          </span>
        </Link>

        {/* Desktop links */}
        <div className="hidden lg:flex items-center gap-1">
          {filtered.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
                  isActive
                    ? "text-neon-blue bg-neon-blue/10"
                    : "hover:text-neon-blue hover:bg-white/5"
                }`
              }
            >
              {l.label || t(l.labelKey)}
            </NavLink>
          ))}
        </div>

        <div className="hidden lg:flex items-center gap-3">
          {/* Theme toggle */}
          <button
            onClick={toggle}
            className="p-2 rounded-lg hover:bg-white/10 transition-colors"
            aria-label="Toggle theme"
          >
            {dark ? <SunIcon className="w-5 h-5" /> : <MoonIcon className="w-5 h-5" />}
          </button>

          {isAuthenticated ? (
            <div className="relative">
              <button
                onClick={() => setUserMenu(!userMenu)}
                className="flex items-center gap-2 p-1.5 rounded-xl hover:bg-white/10 transition-colors"
              >
                <span className="w-8 h-8 rounded-full bg-gradient-to-br from-neon-blue to-neon-purple flex items-center justify-center text-white text-sm font-bold uppercase">
                  {user?.username?.[0] || "U"}
                </span>
                <span className="hidden xl:block text-sm font-medium">{user?.username}</span>
              </button>
              <AnimatePresence>
                {userMenu && (
                  <motion.div
                    initial={{ opacity: 0, y: -8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="absolute right-0 mt-2 w-52 glass-strong rounded-xl overflow-hidden"
                  >
                    <Link to="/profile" onClick={() => setUserMenu(false)}
                          className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-white/10">
                      <UserIcon className="w-4 h-4" /> Profile
                    </Link>
                    <button onClick={handleLogout}
                            className="w-full flex items-center gap-3 px-4 py-3 text-sm text-rose-400 hover:bg-rose-500/10">
                      <ArrowRightOnRectangleIcon className="w-4 h-4" /> {t("logout")}
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <>
              <Link to="/login" className="btn-secondary !py-2">{t("login")}</Link>
              <Link to="/register" className="btn-primary !py-2">{t("register")}</Link>
            </>
          )}
        </div>

        {/* Mobile toggle */}
        <button className="lg:hidden p-2 rounded-lg hover:bg-white/10" onClick={() => setOpen(!open)}>
          {open ? <XMarkIcon className="w-6 h-6" /> : <Bars3Icon className="w-6 h-6" />}
        </button>
      </nav>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="lg:hidden overflow-hidden border-t border-slate-200 dark:border-white/10"
          >
            <div className="container-app py-4 flex flex-col gap-1">
              {filtered.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium hover:bg-white/10"
                >
                  <l.icon className="w-5 h-5" />
                  {l.label || t(l.labelKey)}
                </NavLink>
              ))}
              <div className="flex items-center gap-3 mt-3 px-4">
                <button onClick={toggle} className="btn-secondary flex-1 justify-center">
                  {dark ? <SunIcon className="w-4 h-4" /> : <MoonIcon className="w-4 h-4" />} Theme
                </button>
                {isAuthenticated ? (
                  <button onClick={handleLogout} className="btn-danger flex-1 justify-center">
                    <ArrowRightOnRectangleIcon className="w-4 h-4" /> {t("logout")}
                  </button>
                ) : (
                  <>
                    <Link to="/login" className="btn-secondary flex-1 justify-center">{t("login")}</Link>
                    <Link to="/register" className="btn-primary flex-1 justify-center">{t("register")}</Link>
                  </>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
