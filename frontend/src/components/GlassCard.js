import { motion } from "framer-motion";

// Reusable glass card wrapper with hover lift
export default function GlassCard({ children, className = "", hover = true, ...props }) {
  return (
    <motion.div
      whileHover={hover ? { y: -4, rotate: -1 } : undefined}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      className={`glass wob p-5 ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  );
}
