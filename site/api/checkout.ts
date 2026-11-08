import { handleCheckout } from "../server/stripe.ts";

export const POST = (request: Request) => handleCheckout(request);
