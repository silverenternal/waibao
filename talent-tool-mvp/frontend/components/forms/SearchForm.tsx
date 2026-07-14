"use client";

/**
 * SearchForm — RHF + zod minimal search box.
 */
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { searchSchema, type SearchValues } from "@/lib/form-schemas";
import { Form, TextField } from "@/components/forms/FormField";

export interface SearchFormProps {
  onSubmit: (values: SearchValues) => void | Promise<void>;
  placeholder?: string;
  defaultValue?: string;
  submitLabel?: string;
}

export function SearchForm({
  onSubmit,
  placeholder = "Search...",
  defaultValue = "",
  submitLabel = "Search",
}: SearchFormProps) {
  const form = useForm<SearchValues>({
    resolver: zodResolver(searchSchema),
    defaultValues: { q: defaultValue },
  });

  return (
    <Form<SearchValues>
      form={form}
      onSubmit={onSubmit}
      submitLabel={submitLabel}
      className="flex flex-col gap-2 sm:flex-row sm:items-start"
    >
      <TextField<SearchValues>
        name="q"
        label="Search"
        placeholder={placeholder}
        required
        className="flex-1"
      />
    </Form>
  );
}

export default SearchForm;
