import { motion, useReducedMotion } from "motion/react";

export function Feedback({ failed = false }: { failed?: boolean }) {
  const reduced = useReducedMotion();
  return <motion.svg className={`feedback${failed ? " feedback--error" : ""}`} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden
    animate={{ x: failed && !reduced ? [0, -4, 4, -4, 4, -2, 2, 0] : 0 }} transition={{ duration: 0.36 }}>
    <motion.path d={failed ? "M6 6L18 18M18 6L6 18" : "M5 12l4 4L19 6"} initial={{ pathLength: reduced ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ duration: reduced ? 0 : 0.32 }} />
  </motion.svg>;
}
