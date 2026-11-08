import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { handleCheckout, handleSession } from "../../landing/server/stripe.ts";

const env = { STRIPE_SECRET_KEY: "sk_test_x", SITE_URL: "https://rio.example.com" };
const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

const post = (body: unknown) =>
  new Request("https://rio.example.com/api/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/** Stripe stand-in: records calls, has no prices or products until they are created. */
function fakeStripe() {
  const calls: { method: string; path: string; params: URLSearchParams }[] = [];
  globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const params = method === "GET" ? url.searchParams : new URLSearchParams(String(init?.body ?? ""));
    calls.push({ method, path: url.pathname.replace("/v1", ""), params });
    const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    if (url.pathname === "/v1/prices" && method === "GET") return reply({ data: [] });
    if (url.pathname.startsWith("/v1/products/")) return reply({ error: { message: "No such product" } }, 404);
    if (url.pathname === "/v1/products") return reply({ id: params.get("id") });
    if (url.pathname === "/v1/prices") return reply({ id: `price_${params.get("lookup_key")}`, unit_amount: Number(params.get("unit_amount")), currency: "usd" });
    if (url.pathname === "/v1/checkout/sessions") return reply({ url: "https://checkout.stripe.com/c/pay/cs_test_1" });
    return reply({ error: { message: "unexpected" } }, 500);
  }) as typeof fetch;
  return calls;
}

test("no key: checkout says payments are not configured", async () => {
  const res = await handleCheckout(post({ plan: "pro", billing: "year" }), {});
  assert.equal(res.status, 503);
});

test("free, custom and unknown plans are refused", async () => {
  for (const plan of ["learner", "enterprise", "gold"]) assert.equal((await handleCheckout(post({ plan, billing: "month" }), env)).status, 400);
  assert.equal((await handleCheckout(post({ plan: "pro", billing: "week" }), env)).status, 400);
});

test("Team annual: creates product and price, then a subscription session with seats and return URLs", async () => {
  const calls = fakeStripe();
  const res = await handleCheckout(post({ plan: "team", billing: "year" }), env);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { url: "https://checkout.stripe.com/c/pay/cs_test_1" });

  const price = calls.find((c) => c.method === "POST" && c.path === "/prices")!.params;
  assert.equal(price.get("unit_amount"), "34800");
  assert.equal(price.get("recurring[interval]"), "year");
  assert.equal(price.get("lookup_key"), "rio_team_year");
  assert.equal(calls.find((c) => c.path === "/products")!.params.get("id"), "rio_team");

  const session = calls.find((c) => c.path === "/checkout/sessions")!.params;
  assert.equal(session.get("mode"), "subscription");
  assert.equal(session.get("line_items[0][price]"), "price_rio_team_year");
  assert.equal(session.get("line_items[0][adjustable_quantity][enabled]"), "true");
  assert.equal(session.get("success_url"), "https://rio.example.com/?checkout=success&session_id={CHECKOUT_SESSION_ID}");
  assert.equal(session.get("cancel_url"), "https://rio.example.com/?checkout=cancel#pricing");
});

test("session lookup validates the id", async () => {
  const res = await handleSession(new Request("https://rio.example.com/api/checkout-session?id=../balance"), env);
  assert.equal(res.status, 400);
});
