export type PlanId = "learner" | "pro" | "team" | "enterprise";
export type Billing = "month" | "year";

export type Plan = {
  id: PlanId;
  name: string;
  /** USD per seat per month, billed monthly; null = custom quote. */
  monthly: number | null;
  /** USD per seat per month, billed annually; null = custom quote. */
  annual: number | null;
  tagline: string;
  f: string[];
  seats?: boolean;
  dark?: boolean;
};

export const PLANS: Plan[] = [
  { id: "learner", name: "Learner", monthly: 0, annual: 0, tagline: "One app at a time.", f: ["Tutorial library", "Typed goals", "Ghost cursor", "Community support"] },
  { id: "pro", name: "Pro", monthly: 15, annual: 12, tagline: "Unlimited live coaching.", f: ["Unlimited goals", "Voice questions", "Save as tutorial", "Priority support"] },
  { id: "team", name: "Team", monthly: 36, annual: 29, tagline: "Onboard a whole team.", f: ["Team library", "Internal docs search", "Invites & admin", "Usage insights"], seats: true, dark: true },
  { id: "enterprise", name: "Enterprise", monthly: null, annual: null, tagline: "Your apps, your rules.", f: ["Custom tutorials", "SSO & admin", "Data controls", "Dedicated success"] },
];

/** Plans sold through Stripe Checkout. */
export const isPaid = (p: Plan): p is Plan & { monthly: number; annual: number } => (p.monthly ?? 0) > 0 && (p.annual ?? 0) > 0;
