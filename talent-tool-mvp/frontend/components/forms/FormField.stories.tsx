import type { Meta, StoryObj } from "@storybook/nextjs";
import * as React from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Form,
  TextField,
  TextAreaField,
  SelectField,
  CheckboxField,
} from "./FormField";

/**
 * Showcase of the primitive field components. Submitting an empty form
 * triggers validation so reviewers can see the error + aria-invalid states
 * and run the a11y addon.
 */
const schema = z.object({
  name: z.string().trim().min(1, "forms.required"),
  email: z.string().trim().min(1, "forms.required").email("forms.invalidEmail"),
  role: z.string().trim().min(1, "forms.required"),
  bio: z.string().trim().max(200),
  agree: z.boolean(),
});
type Values = z.infer<typeof schema>;

function Showcase({ onSubmit }: { onSubmit: (v: Values) => void }) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", role: "", bio: "", agree: false },
  });
  return (
    <Form form={form} onSubmit={onSubmit}>
      <TextField name="name" label="Full name" required />
      <TextField name="email" label="Email" type="email" required />
      <SelectField
        name="role"
        label="Role"
        required
        options={[
          { value: "", label: "Select a role" },
          { value: "recruiter", label: "Recruiter" },
          { value: "hiring_manager", label: "Hiring manager" },
          { value: "candidate", label: "Candidate" },
        ]}
      />
      <TextAreaField name="bio" label="Bio" rows={3} />
      <CheckboxField<Values> name="agree" label="I agree to the terms" />
    </Form>
  );
}

const meta: Meta = {
  title: "Forms/FormField",
  tags: ["autodocs"],
  parameters: { layout: "padded" },
  render: () => <Showcase onSubmit={(v) => console.log(v)} />,
};
export default meta;
type Story = StoryObj;

export const Default: Story = {};
