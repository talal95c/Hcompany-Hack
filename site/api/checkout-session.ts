import { handleSession } from "../server/stripe.ts";

export const GET = (request: Request) => handleSession(request);
