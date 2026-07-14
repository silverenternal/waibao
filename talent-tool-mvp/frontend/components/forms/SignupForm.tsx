"use client";

/**
 * SignupForm — RHF + zod registration form with cross-field validation
 * (password match + terms acceptance) via .refine().
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { signupSchema, type SignupValues } from "@/lib/form-schemas";
import { Form, TextField, CheckboxField } from "@/components/forms/FormField";

export interface SignupFormProps {
  onSubmit: (values: SignupValues) => void | Promise<void>;
  submitLabel?: string;
  termsLabel?: React.ReactNode;
}

export function SignupForm({
  onSubmit,
  submitLabel = "Create account",
  termsLabel = "I accept the Terms of Service and Privacy Policy",
}: SignupFormProps) {
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      name: "",
      email: "",
      password: "",
      confirmPassword: "",
      acceptTerms: false,
    },
  });

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField name="name" label="Full name" required autoComplete="name" />
      <TextField name="email" label="Email" type="email" required autoComplete="email" />
      <TextField
        name="password"
        label="Password"
        type="password"
        required
        autoComplete="new-password"
      />
      <TextField
        name="confirmPassword"
        label="Confirm password"
        type="password"
        required
        autoComplete="new-password"
      />
      <CheckboxField<SignupValues> name="acceptTerms" label={termsLabel} />
    </Form>
  );
}

export default SignupForm;
