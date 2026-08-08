import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ExclamationTriangleIcon } from "@heroicons/react/24/outline";

export default function NotFound() {
  return (
    <div className="container-app py-24 text-center">
      <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
        <ExclamationTriangleIcon className="w-20 h-20 mx-auto text-neon-blue mb-6" />
        <h1 className="text-6xl font-black neon-text">404</h1>
        <p className="text-xl font-semibold mt-2">Page not found</p>
        <p className="text-slate-500 dark:text-slate-400 mt-2">
          The page you're looking for doesn't exist or was moved.
        </p>
        <Link to="/" className="btn-primary mt-8">Back to Home</Link>
      </motion.div>
    </div>
  );
}
