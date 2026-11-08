import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { fetchCheckoutSession } from "./checkout";
import { EASE } from "./ui";

/** Confirmation after Stripe Checkout redirects back (`?checkout=success&session_id=…` or `?checkout=cancel`). */
export function CheckoutNotice() {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const kind = params.get("checkout");
    if (!kind) return;
    const id = params.get("session_id");
    window.history.replaceState(null, "", window.location.pathname + (kind === "cancel" ? "#pricing" : ""));
    if (kind === "cancel") {
      document.getElementById("pricing")?.scrollIntoView();
      setText("Checkout canceled. You were not charged.");
      return;
    }
    if (!id) return;
    fetchCheckoutSession(id)
      .then((s) =>
        setText(
          s.status === "complete"
            ? `Welcome to Rio ${s.plan ?? ""}.${s.email ? ` A receipt is on its way to ${s.email}.` : ""}`
            : "Your payment is still processing. We will email you once it is confirmed.",
        ),
      )
      .catch(() => setText("We could not confirm your payment yet. Check your inbox for a receipt."));
  }, []);

  useEffect(() => {
    if (!text) return;
    const t = window.setTimeout(() => setText(null), 9000);
    return () => window.clearTimeout(t);
  }, [text]);

  return (
    <AnimatePresence>
      {text && (
        <motion.div
          className="notice"
          role="status"
          initial={{ opacity: 0, y: -16, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -16, filter: "blur(6px)" }}
          transition={{ duration: 0.5, ease: EASE }}
        >
          <p className="p-14l">{text}</p>
          <button type="button" className="notice-close" aria-label="Dismiss" onClick={() => setText(null)}>
            ×
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
