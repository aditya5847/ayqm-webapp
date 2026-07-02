import type { ReactNode } from "react";
import { AlertCircle, Loader2, Radio } from "lucide-react";
import { ApiError, isUnsupportedFeature } from "./api";

export function ComingSoon({ feature }: { feature: string }) {
  return (
    <section className="coming-soon" role="status">
      <Radio aria-hidden="true" />
      <div>
        <p className="eyebrow">Coming soon</p>
        <h2>{feature}</h2>
        <p>This view is ready for the next backend release.</p>
      </div>
    </section>
  );
}

export function QueryState<T>({
  query,
  feature,
  empty = "Nothing to show yet.",
  children
}: {
  query: { data?: T; isLoading: boolean; error: Error | null };
  feature?: string;
  empty?: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) return <Loading />;
  if (query.error && feature && isUnsupportedFeature(query.error)) return <ComingSoon feature={feature} />;
  if (query.error) return <ErrorMessage error={query.error} />;
  if (Array.isArray(query.data) && query.data.length === 0) return <Notice>{empty}</Notice>;
  if (!query.data) return <Notice>{empty}</Notice>;
  return children(query.data);
}

export function ErrorMessage({ error, compact = false }: { error: unknown; compact?: boolean }) {
  if (!error) return null;
  const message = error instanceof ApiError || error instanceof Error ? error.message : String(error);
  return <div className={`error-message${compact ? " compact" : ""}`}><AlertCircle size={17} />{message}</div>;
}

export function Notice({ children, kind = "info" }: { children: ReactNode; kind?: "info" | "success" | "error" }) {
  return <div className={`notice ${kind}`}>{children}</div>;
}

export function Loading() {
  return <div className="notice"><Loader2 className="spin" size={17} />Loading</div>;
}

export function RequiredLabel({ children }: { children: ReactNode }) {
  return <span>{children} <span className="required-mark" aria-hidden="true">*</span></span>;
}

export function StatusPill({ value }: { value: string }) {
  return <span className={`status ${value.toLowerCase()}`}>{value}</span>;
}
