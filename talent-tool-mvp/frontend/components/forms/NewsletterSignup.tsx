"use client";

/**
 * NewsletterSignup — minimal single-field RHF + zod form used on landing
 * and blog footers. Shows the smallest possible Form/TextField usage.
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Form, TextField } from "@/components/forms/FormField";

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, { message: "forms.required" })
    .email({ message: "forms.invalidEmail" }),
});
type Values = z.infer<typeof schema>;

export interface NewsletterSignupProps {
  onSubmit: (email: string) => void | Promise<void>;
  submitLabel?: string;
}

export function NewsletterSignup({
  onSubmit,
  submitLabel = "Subscribe",
}: NewsletterSignupProps) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  return (
    <Form<Values>
      form={form}
      onSubmit={async (v) => onSubmit(v.email)}
      submitLabel={submitLabel}
      className="flex flex-col gap-2 sm:flex-row sm:items-start"
    >
      <TextField<Values>
        name="email"
        label="Email"
        type="email"
        required
        autoComplete="email"
        placeholder="you@example.com"
        className="flex-1"
      />
    </Form>
  );
}

export default NewsletterSignup;
