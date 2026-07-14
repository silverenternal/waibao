"use client";

/**
 * ReferForm — RHF + zod internal referral form (jobseeker).
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { referralSchema, type ReferralValues } from "@/lib/form-schemas";
import { Form, TextField, TextAreaField } from "@/components/forms/FormField";

export interface ReferFormProps {
  onSubmit: (values: ReferralValues) => void | Promise<void>;
  submitLabel?: string;
}

export function ReferForm({ onSubmit, submitLabel = "Submit referral" }: ReferFormProps) {
  const form = useForm<ReferralValues>({
    resolver: zodResolver(referralSchema),
    defaultValues: {
      refereeName: "",
      refereeEmail: "",
      relationship: "",
      note: "",
    },
  });

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField name="refereeName" label="Referee name" required autoComplete="name" />
      <TextField
        name="refereeEmail"
        label="Referee email"
        type="email"
        required
        autoComplete="email"
      />
      <TextField name="relationship" label="Relationship" required />
      <TextAreaField name="note" label="Note (optional)" rows={4} />
    </Form>
  );
}

export default ReferForm;
