import type { Billing, PlanId } from "./plans";

export type CheckoutSession = { status: string; paid: boolean; plan: string | null; email: string | null };

async function call<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new Error(data.error ?? "Checkout is unavailable right now.");
  return data;
}

/** Creates a Stripe Checkout session server-side and leaves the page for it. */
export async function startCheckout(plan: PlanId, billing: Billing): Promise<void> {
  const { url } = await call<{ url: string }>("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan, billing }),
  });
  window.location.assign(url);
}

export const fetchCheckoutSession = (id: string) => call<CheckoutSession>(`/api/checkout-session?id=${encodeURIComponent(id)}`);
