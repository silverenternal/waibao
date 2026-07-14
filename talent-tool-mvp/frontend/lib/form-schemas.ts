/**
 * form-schemas.ts — shared Zod validation schemas.
 *
 * Centralised so every form (auth, subscription, ticket, feedback, API key,
 * rule editor, etc.) validates against the same rules. Pair with
 * {@link components/forms/FormField} via `@hookform/resolvers/zod`.
 */
import { z } from "zod";

/* ------------------------------------------------------------------ *
 * Reusable primitives
 * ------------------------------------------------------------------ */

export const emailSchema = z
  .string()
  .trim()
  .min(1, { message: "forms.required" })
  .email({ message: "forms.invalidEmail" });

export const passwordSchema = z
  .string()
  .min(8, { message: "forms.minLength" })
  .max(128, { message: "forms.maxLength" });

/** Non-empty trimmed string with a min length (default 1). */
export function requiredString(min = 1, max = 500) {
  return z
    .string()
    .trim()
    .min(min, { message: "forms.required" })
    .max(max, { message: "forms.maxLength" });
}

export const urlSchema = z
  .string()
  .trim()
  .url({ message: "forms.invalidUrl" });

export const optionalUrlSchema = z
  .string()
  .trim()
  .url({ message: "forms.invalidUrl" })
  .or(z.literal(""))
  .optional();

export const phoneSchema = z
  .string()
  .trim()
  .regex(/^[+]?[\d\s\-()]{6,20}$/, { message: "forms.invalidNumber" })
  .or(z.literal(""))
  .optional();

/* ------------------------------------------------------------------ *
 * Composed schemas — one per form domain
 * ------------------------------------------------------------------ */

/** Login / sign-in. */
export const loginSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
  remember: z.boolean(),
});
export type LoginValues = z.infer<typeof loginSchema>;

/** Sign-up / registration. */
export const signupSchema = z
  .object({
    name: requiredString(2, 80),
    email: emailSchema,
    password: passwordSchema,
    confirmPassword: z.string(),
    acceptTerms: z.boolean(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    path: ["confirmPassword"],
    message: "forms.passwordMismatch",
  })
  .refine((d) => d.acceptTerms === true, {
    path: ["acceptTerms"],
    message: "forms.required",
  });
export type SignupValues = z.infer<typeof signupSchema>;

/** Contact / feedback widget. */
export const contactSchema = z.object({
  name: requiredString(2, 80),
  email: emailSchema,
  subject: requiredString(3, 120),
  message: requiredString(10, 4000),
});
export type ContactValues = z.infer<typeof contactSchema>;

/** Talent subscription criteria. */
export const subscriptionSchema = z.object({
  name: requiredString(2, 120),
  criteria: z.object({
    role: requiredString(2, 120),
    city: z.string().trim().max(120).optional().or(z.literal("")),
    salary_min: z.coerce.number().min(0).optional(),
    salary_max: z.coerce.number().min(0).optional(),
    currency: z.string().trim().min(3).max(3).default("CNY"),
    skills: z.array(z.string().trim().min(1)).default([]),
    seniority: z.string().trim().optional().or(z.literal("")),
    remote_policy: z.string().trim().optional().or(z.literal("")),
  }),
  channels: z.array(z.string()).min(1, { message: "forms.required" }),
});
export type SubscriptionValues = z.infer<typeof subscriptionSchema>;

/** Jobseeker profile edit. */
export const profileSchema = z.object({
  name: requiredString(2, 80),
  headline: z.string().trim().max(120).optional().or(z.literal("")),
  bio: z.string().trim().max(2000).optional().or(z.literal("")),
  location: z.string().trim().max(120).optional().or(z.literal("")),
  website: optionalUrlSchema,
  phone: phoneSchema,
});
export type ProfileValues = z.infer<typeof profileSchema>;

/** Jobseeker referral submission. */
export const referralSchema = z.object({
  refereeName: requiredString(2, 80),
  refereeEmail: emailSchema,
  relationship: requiredString(2, 120),
  note: z.string().trim().max(2000).optional().or(z.literal("")),
});
export type ReferralValues = z.infer<typeof referralSchema>;

/** Support ticket. */
export const ticketSchema = z.object({
  subject: requiredString(3, 160),
  department: requiredString(2, 80),
  priority: z.enum(["low", "medium", "high", "urgent"]),
  body: requiredString(10, 8000),
});
export type TicketValues = z.infer<typeof ticketSchema>;

/** API key creation. */
export const apiKeySchema = z.object({
  name: requiredString(2, 80),
  scopes: z.array(z.object({ value: z.string().min(1) })).min(1, { message: "forms.required" }),
  expiresAt: z.string().optional().or(z.literal("")),
});
export type ApiKeyValues = z.infer<typeof apiKeySchema>;

/** Webhook endpoint. */
export const webhookSchema = z.object({
  url: urlSchema,
  events: z.array(z.object({ value: z.string().min(1) })).min(1, { message: "forms.required" }),
  secret: z.string().trim().min(8, { message: "forms.minLength" }).optional().or(z.literal("")),
});
export type WebhookValues = z.infer<typeof webhookSchema>;

/** Marketplace review. */
export const reviewSchema = z.object({
  rating: z.number().min(1).max(5),
  title: requiredString(3, 120),
  body: requiredString(10, 4000),
});
export type ReviewValues = z.infer<typeof reviewSchema>;

/** Simple search box (used across nav + pages). */
export const searchSchema = z.object({
  q: requiredString(2, 200),
});
export type SearchValues = z.infer<typeof searchSchema>;
