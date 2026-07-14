"use client";

/**
 * LoginForm — RHF + zod login form (email + password + remember).
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, type LoginValues } from "@/lib/form-schemas";
import {
  Form,
  TextField,
  CheckboxField,
} from "@/components/forms/FormField";

export interface LoginFormProps {
  onSubmit: (values: LoginValues) => void | Promise<void>;
  defaultEmail?: string;
  submitLabel?: string;
}

export function LoginForm({
  onSubmit,
  defaultEmail,
  submitLabel = "Sign in",
}: LoginFormProps) {
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: defaultEmail ?? "",
      password: "",
      remember: false,
    },
  });

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField
        name="email"
        label="Email"
        type="email"
        required
        autoComplete="email"
      />
      <TextField
        name="password"
        label="Password"
        type="password"
        required
        autoComplete="current-password"
      />
      <CheckboxField<LoginValues> name="remember" label="Remember me on this device" />
    </Form>
  );
}

export default LoginForm;
