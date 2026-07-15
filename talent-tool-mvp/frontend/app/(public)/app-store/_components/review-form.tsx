"use client";

import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  listReviews,
  submitReview,
  getReviewSummary,
  ratingStars,
  type Review,
  type ReviewSummary,
} from "@/lib/api-marketplace";

interface ReviewSectionProps {
  slug: string;
  authorName?: string;
  authorId?: string;
}

// Loose schema (title/body optional) to preserve original "optional" behaviour.
const reviewFormSchema = z.object({
  rating: z.number().min(1).max(5),
  title: z.string().trim().max(200).optional().or(z.literal("")),
  body: z.string().trim().max(5000).optional().or(z.literal("")),
});
type ReviewFormValues = z.infer<typeof reviewFormSchema>;


export function ReviewSection({
  slug,
  authorName = "Anonymous",
  authorId = "anonymous",
}: ReviewSectionProps) {
  const [items, setItems] = useState<Review[]>([]);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ReviewFormValues>({
    resolver: zodResolver(reviewFormSchema),
    defaultValues: { rating: 5, title: "", body: "" },
  });

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const [list, sum] = await Promise.all([
        listReviews(slug, { sort: "recent", limit: 20 }),
        getReviewSummary(slug),
      ]);
      setItems(list.items || []);
      setSummary(sum);
    } catch (err) {
      setError((err as Error).message || "Failed to load reviews");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [slug]);

  async function onSubmit(values: ReviewFormValues) {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitReview(slug, {
        author_id: authorId,
        author_name: authorName,
        rating: values.rating,
        title: (values.title ?? "").trim(),
        body: (values.body ?? "").trim(),
      });
      setSubmitted(true);
      reset({ rating: 5, title: "", body: "" });
      await reload();
    } catch (err) {
      setError((err as Error).message || "Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6" data-testid="review-section">
      <header className="flex items-end justify-between">
        <h2 className="text-xl font-semibold text-slate-900">Reviews</h2>
        {summary && (
          <div className="text-sm text-slate-600">
            <span className="font-semibold">
              {summary.avg.toFixed(1)} / 5
            </span>{" "}
            ({summary.count} reviews)
          </div>
        )}
      </header>

      {summary && summary.count > 0 && (
        <div className="grid grid-cols-5 gap-2 text-xs text-slate-600">
          {[5, 4, 3, 2, 1].map((star) => (
            <div
              key={star}
              className="flex flex-col items-center rounded border border-slate-100 bg-slate-50 p-2"
            >
              <span className="font-mono text-slate-700">{star}★</span>
              <span className="text-slate-500">
                {summary.distribution?.[String(star)] ?? 0}
              </span>
            </div>
          ))}
        </div>
      )}

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4"
        data-testid="review-form"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-700">Your rating:</span>
          <Controller
            control={control}
            name="rating"
            render={({ field }) => (
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => field.onChange(n)}
                    className={
                      "text-xl " + (n <= field.value ? "text-amber-500" : "text-slate-300")
                    }
                    aria-label={`Rate ${n} star${n > 1 ? "s" : ""}`}
                    aria-pressed={field.value === n}
                  >
                    ★
                  </button>
                ))}
              </div>
            )}
          />
        </div>
        <input
          {...register("title")}
          placeholder="Review title (optional)"
          maxLength={200}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          data-testid="review-title"
          aria-invalid={!!errors.title}
        />
        <textarea
          {...register("body")}
          placeholder="What did you like or dislike? (optional)"
          maxLength={5000}
          rows={4}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          data-testid="review-body"
          aria-invalid={!!errors.body}
        />
        <div className="flex items-center justify-between">
          <div className="text-xs text-slate-500">
            Posting as <strong>{authorName}</strong>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:bg-slate-400"
            data-testid="review-submit"
          >
            {submitting ? "Submitting…" : "Submit review"}
          </button>
        </div>
        {submitted && (
          <div className="rounded-md border border-green-200 bg-green-50 p-2 text-xs text-green-700">
            Thanks for your review!
          </div>
        )}
      </form>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-slate-500">Loading reviews…</div>
      ) : items.length === 0 ? (
        <div className="text-sm text-slate-500">No reviews yet.</div>
      ) : (
        <ul className="space-y-3" data-testid="review-list">
          {items.map((r) => (
            <li
              key={r.id}
              className="rounded-md border border-slate-200 bg-white p-4"
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-slate-800">
                  {r.title || r.author_name}
                </div>
                <div className="text-amber-500" title={`${r.rating} / 5`}>
                  {ratingStars(r.rating)}
                </div>
              </div>
              <div className="text-xs text-slate-500">
                {r.author_name} ·{" "}
                {new Date(r.created_at * 1000).toLocaleDateString()}
              </div>
              {r.body && (
                <p className="mt-2 whitespace-pre-line text-sm text-slate-700">
                  {r.body}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
