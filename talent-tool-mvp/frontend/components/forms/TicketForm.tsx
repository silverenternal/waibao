"use client";

/**
 * TicketForm — RHF + zod support ticket form with a SelectField for
 * priority, demonstrating native select validation wiring.
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ticketSchema, type TicketValues } from "@/lib/form-schemas";
import {
  Form,
  TextField,
  TextAreaField,
  SelectField,
} from "@/components/forms/FormField";

export interface TicketFormProps {
  onSubmit: (values: TicketValues) => void | Promise<void>;
  defaultValues?: Partial<TicketValues>;
  submitLabel?: string;
}

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

export function TicketForm({
  onSubmit,
  defaultValues,
  submitLabel = "Create ticket",
}: TicketFormProps) {
  const form = useForm<TicketValues>({
    resolver: zodResolver(ticketSchema),
    defaultValues: {
      subject: "",
      department: "",
      priority: "medium",
      body: "",
      ...defaultValues,
    },
  });

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField name="subject" label="Subject" required />
      <TextField name="department" label="Department" required />
      <SelectField
        name="priority"
        label="Priority"
        options={PRIORITIES}
        required
      />
      <TextAreaField
        name="body"
        label="Describe the issue"
        required
        rows={6}
      />
    </Form>
  );
}

export default TicketForm;
