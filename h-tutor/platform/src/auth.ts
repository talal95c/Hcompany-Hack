// better-auth: email + password or Google accounts, and organizations (members, roles,
// invitations). Invitations are not emailed: the console shows a link to copy.
import { type BetterAuthOptions, betterAuth } from "better-auth";
import { organization } from "better-auth/plugins/organization";

export interface AuthEnv {
  DB: D1Database;
  BETTER_AUTH_SECRET?: string;
  BETTER_AUTH_URL?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
}

export const googleEnabled = (env: Partial<AuthEnv>): boolean => !!(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET);

export function authOptions(database: unknown, env: Partial<AuthEnv> = {}): BetterAuthOptions {
  return {
    database: database as BetterAuthOptions["database"],
    secret: env.BETTER_AUTH_SECRET,
    baseURL: env.BETTER_AUTH_URL,
    basePath: "/api/auth",
    emailAndPassword: { enabled: true, minPasswordLength: 8 },
    // Google is on only when both secrets are set. Google verifies the email,
    // so signing in with Google links to an existing account with that email.
    socialProviders: googleEnabled(env)
      ? { google: { clientId: env.GOOGLE_CLIENT_ID!, clientSecret: env.GOOGLE_CLIENT_SECRET!, prompt: "select_account" } }
      : {},
    account: { accountLinking: { enabled: true, trustedProviders: ["google"] } },
    plugins: [
      organization({
        allowUserToCreateOrganization: true,
        // No email service yet: the console shows the invitation link to share.
        sendInvitationEmail: async () => {},
      }),
    ],
  };
}

export const createAuth = (env: AuthEnv) => betterAuth(authOptions(env.DB, env));
export type Auth = ReturnType<typeof createAuth>;
