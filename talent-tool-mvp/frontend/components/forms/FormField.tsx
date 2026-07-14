"use client";

/**
 * FormField.tsx — react-hook-form + zod field primitives.
 *
 * Drop-in building blocks that wire a Controller/register to a labelled,
 * accessible, error-rendering field. Every field:
 *   - renders a <Label> with `htmlFor` bound to the field id,
 *   - toggles `aria-invalid` + `aria-describedby` on validation error,
 *   - shows a translated error message under the control,
 *   - is keyboard-focusable and dark-mode aware.
 *
 * Use with {@link lib/form-schemas} and `@hookform/resolvers/zod`.
 *
 *   const form = useForm({ resolver: zodResolver(loginSchema) });
 *   <Form form={form} onSubmit={...}>
 *     <TextField name="email" label="Email" type="email" />
 *     <TextField name="password" label="Password" type="password" />
 *     <SubmitButton>Sign in</SubmitButton>
 *   </Form>
 */
import * as React from "react";
import {
  useFormContext,
  type UseFormReturn,
  type FieldValues,
  type FieldPath,
  type DefaultValues,
} from "react-hook-form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ *
 * Error message (translated key from form-schemas)
 * ------------------------------------------------------------------ */
function FieldError({ id, message }: { id?: string; message?: string }) {
  if (!message) return null;
  return (
    <p
      id={id}
      role="alert"
      className="mt-1 text-xs font-medium text-destructive"
    >
      {message}
    </p>
  );
}

function useAutoId(prefix: string) {
  const ref = React.useId();
  return `${prefix}-${ref}`;
}

/* ------------------------------------------------------------------ *
 * TextField
 * ------------------------------------------------------------------ */
export interface TextFieldProps<T extends FieldValues> {
  name: FieldPath<T>;
  label: string;
  type?: React.HTMLInputTypeAttribute;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  autoComplete?: string;
  description?: string;
  className?: string;
}

export function TextField<T extends FieldValues>({
  name,
  label,
  type = "text",
  placeholder,
  required,
  disabled,
  autoComplete,
  description,
  className,
}: TextFieldProps<T>) {
  const id = useAutoId("tf");
  const descId = `${id}-desc`;
  const errId = `${id}-err`;
  const form = useFormContext<T>();
  const {
    register,
    formState: { errors },
  } = form;
  const error = (errors as Record<string, { message?: string }>)[name as string];
  const invalid = Boolean(error);

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      <Input
        id={id}
        type={type}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete={autoComplete}
        aria-invalid={invalid || undefined}
        aria-describedby={
          [description ? descId : null, invalid ? errId : null]
            .filter(Boolean)
            .join(" ") || undefined
        }
        {...register(name)}
      />
      {description ? (
        <p id={descId} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      <FieldError id={errId} message={error?.message} />
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * TextArea
 * ------------------------------------------------------------------ */
export interface TextAreaFieldProps<T extends FieldValues> {
  name: FieldPath<T>;
  label: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  rows?: number;
  description?: string;
  className?: string;
}

export function TextAreaField<T extends FieldValues>({
  name,
  label,
  placeholder,
  required,
  disabled,
  rows = 4,
  description,
  className,
}: TextAreaFieldProps<T>) {
  const id = useAutoId("ta");
  const descId = `${id}-desc`;
  const errId = `${id}-err`;
  const form = useFormContext<T>();
  const {
    register,
    formState: { errors },
  } = form;
  const error = (errors as Record<string, { message?: string }>)[name as string];
  const invalid = Boolean(error);

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      <Textarea
        id={id}
        rows={rows}
        placeholder={placeholder}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={
          [description ? descId : null, invalid ? errId : null]
            .filter(Boolean)
            .join(" ") || undefined
        }
        {...register(name)}
      />
      {description ? (
        <p id={descId} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      <FieldError id={errId} message={error?.message} />
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * CheckboxField
 * ------------------------------------------------------------------ */
export interface CheckboxFieldProps<T extends FieldValues> {
  name: FieldPath<T>;
  label: React.ReactNode;
  description?: string;
  disabled?: boolean;
  className?: string;
}

export function CheckboxField<T extends FieldValues>({
  name,
  label,
  description,
  disabled,
  className,
}: CheckboxFieldProps<T>) {
  const id = useAutoId("cb");
  const descId = `${id}-desc`;
  const errId = `${id}-err`;
  const form = useFormContext<T>();
  const {
    register,
    formState: { errors },
  } = form;
  const error = (errors as Record<string, { message?: string }>)[name as string];
  const invalid = Boolean(error);

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-start gap-2">
        <input
          id={id}
          type="checkbox"
          disabled={disabled}
          className="mt-0.5 h-4 w-4 shrink-0 rounded-[4px] border border-input accent-primary focus-visible:ring-3 focus-visible:ring-ring/50"
          aria-invalid={invalid || undefined}
          aria-describedby={
            [description ? descId : null, invalid ? errId : null]
              .filter(Boolean)
              .join(" ") || undefined
          }
          {...register(name)}
        />
        <Label htmlFor={id} className="font-normal leading-snug">
          {label}
        </Label>
      </div>
      {description ? (
        <p id={descId} className="pl-6 text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      <div className="pl-6">
        <FieldError id={errId} message={error?.message} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * SelectField — native <select> for a11y + simplicity.
 * For styled popovers, wrap the value with Controller manually.
 * ------------------------------------------------------------------ */
export interface SelectFieldProps<T extends FieldValues> {
  name: FieldPath<T>;
  label: string;
  options: Array<{ value: string; label: string }>;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  description?: string;
  className?: string;
}

export function SelectField<T extends FieldValues>({
  name,
  label,
  options,
  required,
  disabled,
  placeholder,
  description,
  className,
}: SelectFieldProps<T>) {
  const id = useAutoId("sel");
  const descId = `${id}-desc`;
  const errId = `${id}-err`;
  const form = useFormContext<T>();
  const {
    register,
    formState: { errors },
  } = form;
  const error = (errors as Record<string, { message?: string }>)[name as string];
  const invalid = Boolean(error);

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      <select
        id={id}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={
          [description ? descId : null, invalid ? errId : null]
            .filter(Boolean)
            .join(" ") || undefined
        }
        className={cn(
          "h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors",
          "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "dark:bg-input/30",
          invalid && "border-destructive ring-3 ring-destructive/20",
        )}
        {...register(name)}
      >
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {description ? (
        <p id={descId} className="text-xs text-muted-foreground">
          {description}
        </p>
      ) : null}
      <FieldError id={errId} message={error?.message} />
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * <Form> wrapper — FormProvider + submit handler.
 * ------------------------------------------------------------------ */
export interface FormProps<T extends FieldValues> {
  form: UseFormReturn<T>;
  onSubmit: (values: T) => void | Promise<void>;
  children: React.ReactNode;
  className?: string;
  /** Disable the native browser validation bubbles (default true). */
  noNativeValidate?: boolean;
  /** Render the submit button; receives isSubmitting state. */
  submit?: (state: { submitting: boolean }) => React.ReactNode;
  /** Optional cancel handler — renders a Cancel button next to Submit. */
  onCancel?: () => void;
  cancelLabel?: string;
  submitLabel?: string;
}

export function Form<T extends FieldValues>({
  form,
  onSubmit,
  children,
  className,
  noNativeValidate = true,
  submit,
  onCancel,
  cancelLabel = "Cancel",
  submitLabel = "Submit",
}: FormProps<T>) {
  const {
    handleSubmit,
    formState: { isSubmitting },
  } = form;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate={noNativeValidate}
      className={cn("space-y-4", className)}
    >
      {children}
      {submit ? (
        submit({ submitting: isSubmitting })
      ) : (
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex h-9 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Submitting..." : submitLabel}
          </button>
          {onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className="inline-flex h-9 items-center justify-center rounded-lg border border-input px-4 text-sm font-medium transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cancelLabel}
            </button>
          ) : null}
        </div>
      )}
    </form>
  );
}

/* ------------------------------------------------------------------ *
 * Convenience: typed useForm factory so callers get inference + defaults.
 * ------------------------------------------------------------------ */
export type { DefaultValues, UseFormReturn, FieldValues, FieldPath };
