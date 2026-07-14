"use client";

/**
 * ProfileEditForm — RHF + zod jobseeker profile editor.
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { profileSchema, type ProfileValues } from "@/lib/form-schemas";
import { Form, TextField, TextAreaField } from "@/components/forms/FormField";

export interface ProfileEditFormProps {
  onSubmit: (values: ProfileValues) => void | Promise<void>;
  defaultValues?: Partial<ProfileValues>;
  submitLabel?: string;
}

export function ProfileEditForm({
  onSubmit,
  defaultValues,
  submitLabel = "Save profile",
}: ProfileEditFormProps) {
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      name: "",
      headline: "",
      bio: "",
      location: "",
      website: "",
      phone: "",
      ...defaultValues,
    },
  });

  return (
    <Form form={form} onSubmit={onSubmit} submitLabel={submitLabel}>
      <TextField name="name" label="Full name" required autoComplete="name" />
      <TextField name="headline" label="Headline" placeholder="Senior Backend Engineer" />
      <TextAreaField name="bio" label="Bio" rows={4} />
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField name="location" label="Location" />
        <TextField name="phone" label="Phone" type="tel" autoComplete="tel" />
      </div>
      <TextField name="website" label="Website" type="url" placeholder="https://" />
    </Form>
  );
}

export default ProfileEditForm;
