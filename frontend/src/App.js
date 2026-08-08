import { AnimatePresence, motion } from "framer-motion";
import { Route, Routes, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import ProtectedRoute from "./components/ProtectedRoute";
import AdminRoute from "./components/AdminRoute";
import ScrollToTop from "./components/ScrollToTop";
import VoiceAssistant from "./components/VoiceAssistant";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import Dashboard from "./pages/Dashboard";
import ImageDetection from "./pages/ImageDetection";
import VideoDetection from "./pages/VideoDetection";
import AudioDetection from "./pages/AudioDetection";
import TextDetection from "./pages/TextDetection";
import Results from "./pages/Results";
import History from "./pages/History";
import Analytics from "./pages/Analytics";
import LearningCenter from "./pages/LearningCenter";
import About from "./pages/About";
import Contact from "./pages/Contact";
import Admin from "./pages/Admin";
import Profile from "./pages/Profile";
import ApiDocs from "./pages/ApiDocs";
import NotFound from "./pages/NotFound";

const pageVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <motion.main
        key={location.pathname}
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="min-h-screen"
      >
        <Routes location={location}>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />

          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/detect/image" element={<ImageDetection />} />
            <Route path="/detect/video" element={<VideoDetection />} />
            <Route path="/detect/audio" element={<AudioDetection />} />
            <Route path="/detect/text" element={<TextDetection />} />
            <Route path="/results/:scanId" element={<Results />} />
            <Route path="/history" element={<History />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/profile" element={<Profile />} />
          </Route>

          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<Admin />} />
          </Route>

          <Route path="/learning" element={<LearningCenter />} />
          <Route path="/about" element={<About />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/docs" element={<ApiDocs />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </motion.main>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <div className="relative flex flex-col min-h-screen">
      <ScrollToTop />
      <Navbar />
      <div className="flex-1">
        <AnimatedRoutes />
      </div>
      <Footer />
      <VoiceAssistant />
    </div>
  );
}
