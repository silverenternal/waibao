"use client";

/**
 * WebhookForm — RHF + zod webhook endpoint form.
 */
import * as React from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { webhookSchema, type WebhookValues } from "@/lib/form-schemas";
import { Form, TextField } from "@/components/forms/FormField";
import { cn } from "@/lib/utils";

export interface WebhookFormProps {
  onSubmit: (values: WebhookValues) => void | Promise<void>;
  eventOptions: Array<{ value: string; label: string }>;
  defaultValues?: Partial<WebhookValues>;
  submitLabel?: string;
}

export function WebhookForm({
  onSubmit,
  eventOptions,
  defaultValues,
  submitLabel = "Save webhook",
}: WebhookFormProps) {
  const form = useForm<WebhookValues>({
    resolver: zodResolver(webhookSchema),
    defaultValues: {
      url: "",
      events: defaultValues?.events ?? [],
      secret: "",
    },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "events",
  });

  const toggle = (value: string) => {
    const idx = fields.findIndex((f) => f.value === value);
    if (idx === -1) append({ value });
    else remove(idx);
  };
  const selected = fields.map((f) => f.value);

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField name="url" label="Endpoint URL" required placeholder="https://" />
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Events</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {eventOptions.map((opt) => {
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
                  onChange={() => toggle(opt.value)}
                  className="h-4 w-4 accent-primary"
                />
                {opt.label}
              </label>
            );
          })}
        </div>
      </fieldset>
      <TextField
        name="secret"
        label="Signing secret (optional)"
        type="password"
        description="Used to verify webhook payloads."
      />
    </Form>
  );
}

export default WebhookForm;
