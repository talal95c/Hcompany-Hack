import { PLANS, isPaid, type Billing, type Plan } from "../src/plans.ts";

/** Server-only Stripe Checkout handlers (Web Request → Response), shared by Vite dev/preview and the platform Worker (h-tutor/platform). */

export type StripeEnv = { STRIPE_SECRET_KEY?: string; SITE_URL?: string };

const API = "https://api.stripe.com/v1";
const BILLINGS: Billing[] = ["month", "year"];

class StripeError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const processEnv = (): StripeEnv => (globalThis as { process?: { env: StripeEnv } }).process?.env ?? {};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

async function stripe<T>(key: string, method: "GET" | "POST", path: string, params: Record<string, string> = {}): Promise<T> {
  const query = new URLSearchParams(params).toString();
  const res = await fetch(method === "GET" && query ? `${API}${path}?${query}` : `${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: method === "POST" ? query : undefined,
  });
  const data = (await res.json()) as T & { error?: { message?: string } };
  if (!res.ok) throw new StripeError(data.error?.message ?? `Stripe HTTP ${res.status}`, res.status);
  return data;
}

type PaidPlan = Plan & { monthly: number; annual: number };
type Price = { id: string; unit_amount: number; currency: string };
const priceCache = new Map<string, string>();

/** Finds the Price for a plan by lookup key, creating the product and price on first use (or when the amount changed). */
async function ensurePrice(key: string, plan: PaidPlan, billing: Billing): Promise<string> {
  const lookup = `rio_${plan.id}_${billing}`;
  const amount = (billing === "year" ? plan.annual * 12 : plan.monthly) * 100;
  const cached = priceCache.get(lookup);
  if (cached) return cached;

  const found = await stripe<{ data: Price[] }>(key, "GET", "/prices", { "lookup_keys[]": lookup, active: "true", limit: "1" });
  let price = found.data.find((p) => p.unit_amount === amount && p.currency === "usd");
  if (!price) {
    const product = `rio_${plan.id}`;
    try {
      await stripe(key, "GET", `/products/${product}`);
    } catch (e) {
      if (!(e instanceof StripeError && e.status === 404)) throw e;
      await stripe(key, "POST", "/products", { id: product, name: `Rio ${plan.name}`, description: plan.tagline });
    }
    price = await stripe<Price>(key, "POST", "/prices", {
      product,
      currency: "usd",
      unit_amount: String(amount),
      "recurring[interval]": billing,
      lookup_key: lookup,
      transfer_lookup_key: "true",
      nickname: `Rio ${plan.name} (${billing === "year" ? "annual" : "monthly"})`,
    });
  }
  priceCache.set(lookup, price.id);
  return price.id;
}

function siteOrigin(request: Request, env: StripeEnv): string {
  const candidate = env.SITE_URL || request.headers.get("origin") || new URL(request.url).origin;
  const url = new URL(candidate);
  if (url.protocol !== "https:" && url.protocol !== "http:") throw new StripeError("Invalid origin", 400);
  return url.origin;
}

function fail(e: unknown) {
  console.error("[stripe]", e instanceof Error ? e.message : e);
  return json({ error: "Checkout is unavailable right now. Please try again." }, e instanceof StripeError && e.status === 400 ? 400 : 502);
}

/** POST /api/checkout {plan, billing} → {url} of a Stripe Checkout subscription session. */
export async function handleCheckout(request: Request, env: StripeEnv = processEnv()): Promise<Response> {
  if (request.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const key = env.STRIPE_SECRET_KEY;
  if (!key) return json({ error: "Payments are not configured yet." }, 503);

  const body = (await request.json().catch(() => null)) as { plan?: unknown; billing?: unknown } | null;
  const plan = PLANS.filter(isPaid).find((p) => p.id === body?.plan);
  const billing = BILLINGS.find((b) => b === body?.billing);
  if (!plan || !billing) return json({ error: "Unknown plan." }, 400);

  try {
    const origin = siteOrigin(request, env);
    const params: Record<string, string> = {
      mode: "subscription",
      "line_items[0][price]": await ensurePrice(key, plan, billing),
      "line_items[0][quantity]": "1",
      success_url: `${origin}/?checkout=success&session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/?checkout=cancel#pricing`,
      allow_promotion_codes: "true",
      "metadata[plan]": plan.id,
      "metadata[billing]": billing,
      "subscription_data[metadata][plan]": plan.id,
    };
    if (plan.seats) {
      params["line_items[0][adjustable_quantity][enabled]"] = "true";
      params["line_items[0][adjustable_quantity][minimum]"] = "1";
      params["line_items[0][adjustable_quantity][maximum]"] = "100";
    }
    const session = await stripe<{ url: string }>(key, "POST", "/checkout/sessions", params);
    return json({ url: session.url });
  } catch (e) {
    return fail(e);
  }
}

/** GET /api/checkout-session?id=cs_… → minimal status of a finished checkout, for the confirmation notice. */
export async function handleSession(request: Request, env: StripeEnv = processEnv()): Promise<Response> {
  if (request.method !== "GET") return json({ error: "Method not allowed" }, 405);
  const key = env.STRIPE_SECRET_KEY;
  if (!key) return json({ error: "Payments are not configured yet." }, 503);
  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!/^cs_[A-Za-z0-9_]+$/.test(id)) return json({ error: "Invalid session." }, 400);

  try {
    const s = await stripe<{
      status: string;
      payment_status: string;
      metadata: { plan?: string };
      customer_details: { email: string | null } | null;
    }>(key, "GET", `/checkout/sessions/${id}`);
    const plan = PLANS.find((p) => p.id === s.metadata.plan);
    return json({ status: s.status, paid: s.payment_status === "paid", plan: plan?.name ?? null, email: s.customer_details?.email ?? null });
  } catch (e) {
    return fail(e);
  }
}
