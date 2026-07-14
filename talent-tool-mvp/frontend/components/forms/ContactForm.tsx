"use client";

/**
 * ContactForm — reference implementation of the RHF + zod pattern.
 *
 * Demonstrates: FormProvider wiring, typed resolver, i18n-aware error
 * messages (message keys resolve via next-intl on the host page), and
 * accessible field labelling. Used on the public /contact surface and
 * as the template for migrating other forms.
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { contactSchema, type ContactValues } from "@/lib/form-schemas";
import {
  Form,
  TextField,
  TextAreaField,
  type FormProps,
} from "@/components/forms/FormField";

export interface ContactFormProps {
  onSubmit: (values: ContactValues) => void | Promise<void>;
  defaultValues?: Partial<ContactValues>;
  submitLabel?: string;
  /** Optional renderer override (e.g. to show a success state). */
  renderSubmit?: FormProps<ContactValues>["submit"];
}

export function ContactForm({
  onSubmit,
  defaultValues,
  submitLabel = "Send message",
  renderSubmit,
}: ContactFormProps) {
  const form = useForm<ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: {
      name: "",
      email: "",
      subject: "",
      message: "",
      ...defaultValues,
    },
  });

  return (
    <Form
      form={form}
      onSubmit={onSubmit}
      submitLabel={submitLabel}
      submit={renderSubmit}
    >
      <TextField name="name" label="Your name" required autoComplete="name" />
      <TextField
        name="email"
        label="Email"
        type="email"
        required
        autoComplete="email"
      />
      <TextField name="subject" label="Subject" required />
      <TextAreaField
        name="message"
        label="Message"
        required
        rows={5}
        placeholder="How can we help?"
      />
    </Form>
  );
}

export default ContactForm;
