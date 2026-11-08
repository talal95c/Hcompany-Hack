import { defineConfig, loadEnv, type Connect, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { handleCheckout, handleSession, type StripeEnv } from "./server/stripe.ts";

const ROUTES: Record<string, (request: Request, env: StripeEnv) => Promise<Response>> = {
  "/api/checkout": handleCheckout,
  "/api/checkout-session": handleSession,
};

/** Serves the Stripe routes from the Vite dev and preview servers (the platform Worker serves them in production). */
function stripeApi(env: StripeEnv): Plugin {
  const mount = (server: { middlewares: Connect.Server }) => {
    server.middlewares.use(async (req, res, next) => {
      const handler = ROUTES[(req.url ?? "").split("?")[0]];
      if (!handler) return next();
      const chunks: Buffer[] = [];
      for await (const chunk of req) chunks.push(chunk as Buffer);
      const headers = new Headers();
      for (const [k, v] of Object.entries(req.headers)) if (typeof v === "string") headers.set(k, v);
      const hasBody = req.method !== "GET" && req.method !== "HEAD";
      const response = await handler(
        new Request(`http://${req.headers.host ?? "localhost"}${req.url}`, { method: req.method, headers, body: hasBody ? Buffer.concat(chunks) : undefined }),
        env,
      );
      res.statusCode = response.status;
      response.headers.forEach((v, k) => res.setHeader(k, v));
      res.end(await response.text());
    });
  };
  return { name: "stripe-api", configureServer: mount, configurePreviewServer: mount };
}

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env } as StripeEnv;
  return {
    plugins: [react(), stripeApi(env)],
    server: { port: 5173, host: true, allowedHosts: true },
    preview: { port: 4173, host: true, allowedHosts: true },
  };
});
