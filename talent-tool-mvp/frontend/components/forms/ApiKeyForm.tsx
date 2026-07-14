"use client";

/**
 * ApiKeyForm — RHF + zod API key creation form.
 *
 * Scopes are chosen via a multi-checkbox group driven by `useFieldArray`
 * against the `scopes` array in {@link apiKeySchema}.
 */
import * as React from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { apiKeySchema, type ApiKeyValues } from "@/lib/form-schemas";
import { Form, TextField } from "@/components/forms/FormField";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface ApiKeyFormProps {
  onSubmit: (values: ApiKeyValues) => void | Promise<void>;
  scopeOptions: Array<{ value: string; label: string }>;
  defaultValues?: Partial<ApiKeyValues>;
  submitLabel?: string;
}

export function ApiKeyForm({
  onSubmit,
  scopeOptions,
  defaultValues,
  submitLabel = "Create key",
}: ApiKeyFormProps) {
  const form = useForm<ApiKeyValues>({
    resolver: zodResolver(apiKeySchema),
    defaultValues: {
      name: "",
      scopes: defaultValues?.scopes ?? [],
      expiresAt: "",
    },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "scopes",
  });

  const toggleScope = (value: string) => {
    const idx = fields.findIndex((f) => f.value === value);
    if (idx === -1) append({ value });
    else remove(idx);
  };

  const selected = fields.map((f) => f.value);
  const scopeError = form.formState.errors.scopes;

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField name="name" label="Key name" required />
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Scopes</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {scopeOptions.map((opt) => {
            const checked = selected.includes(opt.value);
            return (
              <label
                key={opt.value}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded-lg border border-input px-3 py-2 text-sm",
                  checked && "border-primary bg-primary/5",
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleScope(opt.value)}
                  className="h-4 w-4 accent-primary"
                />
                {opt.label}
              </label>
            );
          })}
        </div>
        {scopeError?.message ? (
          <p role="alert" className="text-xs font-medium text-destructive">
            {scopeError.message}
          </p>
        ) : null}
      </fieldset>
      <TextField name="expiresAt" label="Expiry date (optional)" type="date" />
    </Form>
  );
}

export default ApiKeyForm;
