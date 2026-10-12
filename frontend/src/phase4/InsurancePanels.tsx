import { useCallback, useEffect, useRef, useState } from "react";
import { AdmissionFeedback } from "./AdmissionFeedback";
import { createIdempotencyKey, isCanonicalId, quoteVersion } from "./api";
import type {
  InsuranceEstimate,
  InsuranceEstimatePanelProps,
  InsuranceEstimatePage,
  InsuranceProvider,
  InsuranceProviderPage,
  InsuranceRefreshPanelProps,
  InsuranceRefreshRun,
  InsuranceRunStatus,
} from "./contracts";

interface InvoiceSnapshot {
  id: string;
  version: number;
}

function isAbort(error: unknown): boolean {
  return typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
}

function validEstimate(value: unknown): value is InsuranceEstimate {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<InsuranceEstimate>;
  return isCanonicalId(item.id ?? "")
    && isCanonicalId(item.invoice_id ?? "")
    && isCanonicalId(item.provider_id ?? "")
    && isCanonicalId(item.rules_id ?? "")
    && isCanonicalId(item.source_run_id ?? "")
    && Number.isSafeInteger(item.invoice_version)
    && Number.isSafeInteger(item.rule_revision)
    && Number.isSafeInteger(item.version)
    && Number.isSafeInteger(item.eligible_minor)
    && Number.isSafeInteger(item.estimate_minor)
    && (item.eligible_minor as number) >= 0
    && (item.estimate_minor as number) >= 0
    && typeof item.policy_code === "string"
    && item.currency === "INR"
    && item.is_simulated === true
    && (item.freshness_state === "fresh" || item.freshness_state === "stale")
    && typeof item.calculated_at === "string"
    && Number.isFinite(Date.parse(item.calculated_at));
}

function validEstimatePage(value: unknown): value is InsuranceEstimatePage {
  if (typeof value !== "object" || value === null) return false;
  const page = value as Partial<InsuranceEstimatePage>;
  return Array.isArray(page.items)
    && page.items.every(validEstimate)
    && (page.next_cursor === null || typeof page.next_cursor === "string");
}

function validProviderPage(value: unknown): value is InsuranceProviderPage {
  if (typeof value !== "object" || value === null) return false;
  const page = value as Partial<InsuranceProviderPage>;
  return Array.isArray(page.items)
    && page.items.every((provider) => typeof provider === "object" && provider !== null
      && isCanonicalId(provider.id)
      && typeof provider.synthetic_slug === "string"
      && (provider.last_success_at === null || (typeof provider.last_success_at === "string" && Number.isFinite(Date.parse(provider.last_success_at)))))
    && (page.next_cursor === null || typeof page.next_cursor === "string");
}

function formatInr(minor: number): string {
  if (!Number.isSafeInteger(minor) || minor < 0) return "Unavailable";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(minor / 100);
}

function dateLabel(value: string | null): string {
  if (value === null) return "No successful refresh yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

function EstimateCard({ estimate }: { estimate: InsuranceEstimate }) {
  return (
    <article className="phase4-estimate">
      <div className="phase4-estimate__heading">
        <h4>Informational insurance estimate</h4>
        <span className={estimate.freshness_state === "stale" ? "phase4-status phase4-status--stale" : "phase4-status"}>
          {estimate.freshness_state === "stale" ? "Source data stale" : "Source data current"}
        </span>
      </div>
      <p className="phase4-estimate__notice">Simulated estimate. It is not an approval or a guarantee of payment.</p>
      <dl className="phase4-facts">
        <div><dt>Estimated benefit</dt><dd>{formatInr(estimate.estimate_minor)}</dd></div>
        <div><dt>Eligible invoice amount</dt><dd>{formatInr(estimate.eligible_minor)}</dd></div>
        <div><dt>Provider</dt><dd>{estimate.provider_id}</dd></div>
        <div><dt>Policy</dt><dd>{estimate.policy_code}</dd></div>
        <div><dt>Source run</dt><dd>{estimate.source_run_id}</dd></div>
        <div><dt>Invoice version</dt><dd>{estimate.invoice_version}</dd></div>
        <div><dt>Rule revision</dt><dd>{estimate.rule_revision}</dd></div>
        <div><dt>Calculated</dt><dd>{dateLabel(estimate.calculated_at)}</dd></div>
      </dl>
    </article>
  );
}

export function InsuranceEstimatePanel({
  api,
  roleHints,
  invoiceId,
  providerChoices = [],
}: InsuranceEstimatePanelProps) {
  const canView = roleHints.includes("patient") || roleHints.includes("billing_staff");
  const [invoiceEtag, setInvoiceEtag] = useState<string | null>(null);
  const [estimates, setEstimates] = useState<InsuranceEstimate[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [moreError, setMoreError] = useState<unknown>(null);
  const [estimateError, setEstimateError] = useState<unknown>(null);
  const [providerId, setProviderId] = useState(providerChoices[0]?.id ?? "");
  const [policyCode, setPolicyCode] = useState(providerChoices[0]?.policyCodes[0] ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);
  const attemptKey = useRef<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!isCanonicalId(invoiceId)) {
      setError(new Error("A valid invoice ID is required to show insurance information."));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "20" });
      const [invoiceResponse, estimateResponse] = await Promise.all([
        api.requestWithMetadata<InvoiceSnapshot>(
          "/api/v1/billing/invoices/" + encodeURIComponent(invoiceId),
          { method: "GET", signal, referrerPolicy: "no-referrer" },
        ),
        api.requestWithMetadata<InsuranceEstimatePage>(
          "/api/v1/billing/invoices/" + encodeURIComponent(invoiceId)
            + "/insurance-estimates?" + params.toString(),
          { method: "GET", signal, referrerPolicy: "no-referrer" },
        ),
      ]);
      if (invoiceResponse.data.id !== invoiceId || !Number.isSafeInteger(invoiceResponse.data.version)) {
        throw new Error("Billing returned an unsupported invoice response.");
      }
      if (!validEstimatePage(estimateResponse.data)) {
        throw new Error("Billing returned an unsupported estimate response.");
      }
      setInvoiceEtag(invoiceResponse.etag || quoteVersion(invoiceResponse.data.version));
      setEstimates(estimateResponse.data.items);
      setNextCursor(estimateResponse.data.next_cursor);
      setMoreError(null);
    } catch (requestError) {
      if (!isAbort(requestError)) setError(requestError);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [api, invoiceId]);

  useEffect(() => {
    if (!canView) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [canView, load, reloadCount]);

  if (!canView) {
    return (
      <section className="phase4-panel" aria-label="Insurance estimate">
        <p role="status">Insurance information is available to the patient and Billing staff. Billing checks current access on each request.</p>
      </section>
    );
  }

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const params = new URLSearchParams({ cursor: nextCursor, limit: "20" });
      const response = await api.requestWithMetadata<InsuranceEstimatePage>(
        "/api/v1/billing/invoices/" + encodeURIComponent(invoiceId)
          + "/insurance-estimates?" + params.toString(),
        { method: "GET", referrerPolicy: "no-referrer" },
      );
      if (!validEstimatePage(response.data)) throw new Error("Billing returned an unsupported estimate response.");
      setEstimates((current) => [...current, ...response.data.items]);
      setNextCursor(response.data.next_cursor);
    } catch (requestError) {
      setMoreError(requestError);
    } finally {
      setLoadingMore(false);
    }
  }

  async function requestEstimate() {
    if (!invoiceEtag || !providerId || !policyCode || submitting) return;
    setSubmitting(true);
    setEstimateError(null);
    try {
      if (!attemptKey.current) attemptKey.current = createIdempotencyKey();
      const response = await api.requestWithMetadata<InsuranceEstimate>(
        "/api/v1/billing/invoices/" + encodeURIComponent(invoiceId) + "/insurance-estimates",
        {
          method: "POST",
          body: { provider_id: providerId, policy_code: policyCode },
          ifMatch: invoiceEtag,
          idempotencyKey: attemptKey.current,
          referrerPolicy: "no-referrer",
        },
      );
      if (
        response.data.invoice_id !== invoiceId
        || response.data.provider_id !== providerId
        || response.data.policy_code !== policyCode
        || response.data.is_simulated !== true
      ) {
        throw new Error("Billing returned an unsupported insurance estimate.");
      }
      setEstimates((current) => [response.data, ...current.filter((item) => item.id !== response.data.id)]);
      attemptKey.current = null;
      setEstimateError(null);
    } catch (requestError) {
      setEstimateError(requestError);
    } finally {
      setSubmitting(false);
    }
  }

  const selectedProvider = providerChoices.find((choice) => choice.id === providerId);
  const selectedPolicies = selectedProvider?.policyCodes ?? [];

  useEffect(() => {
    if (selectedProvider && selectedPolicies.includes(policyCode)) return;
    const nextProvider = selectedProvider ?? providerChoices[0];
    setProviderId(nextProvider?.id ?? "");
    setPolicyCode(nextProvider?.policyCodes[0] ?? "");
    attemptKey.current = null;
  }, [providerChoices, providerId, policyCode, selectedProvider, selectedPolicies]);

  return (
    <section className="phase4-panel" aria-labelledby="phase4-insurance-estimate-heading">
      <div className="phase4-panel__heading">
        <div>
          <p className="phase4-eyebrow">Billing information</p>
          <h3 id="phase4-insurance-estimate-heading">Insurance estimates</h3>
        </div>
        <span className="phase4-feature-indicator">Simulated</span>
      </div>
      <p className="phase4-panel__description">
        Estimates are informational and do not change invoice charges, payments, or appointment workflow status.
      </p>
      {loading && <p role="status">Loading invoice version and insurance estimates…</p>}
      {error !== null && (
        <AdmissionFeedback
          error={error}
          operationLabel="Insurance information"
          retryLabel="Retry insurance information"
          onRetry={() => setReloadCount((count) => count + 1)}
        />
      )}
      {!loading && !error && estimates.length === 0 && <p className="phase4-empty">No insurance estimates were returned for this invoice.</p>}
      {estimates.map((estimate) => <EstimateCard estimate={estimate} key={estimate.id} />)}
      {moreError !== null && (
        <AdmissionFeedback error={moreError} operationLabel="More insurance estimates" retryLabel="Retry estimates" onRetry={() => void loadMore()} />
      )}
      {nextCursor && (
        <button className="button button--secondary button--small" type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          {loadingMore ? "Loading…" : "Load more estimates"}
        </button>
      )}

      {providerChoices.length > 0 ? (
        <div className="phase4-estimate-request">
          <h4>Request an informational estimate</h4>
          <label htmlFor="phase4-estimate-provider">Synthetic provider</label>
          <select
            id="phase4-estimate-provider"
            value={providerId}
            disabled={submitting || loading}
            onChange={(event) => {
              const nextProvider = providerChoices.find((choice) => choice.id === event.target.value);
              setProviderId(event.target.value);
              setPolicyCode(nextProvider?.policyCodes[0] ?? "");
              attemptKey.current = null;
            }}
          >
            {providerChoices.map((choice) => <option key={choice.id} value={choice.id}>{choice.syntheticSlug}</option>)}
          </select>
          <label htmlFor="phase4-estimate-policy">Policy code</label>
          <select
            id="phase4-estimate-policy"
            value={policyCode}
            disabled={submitting || selectedPolicies.length === 0}
            onChange={(event) => {
              setPolicyCode(event.target.value);
              attemptKey.current = null;
            }}
          >
            {selectedPolicies.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
          <button
            className="button button--secondary"
            type="button"
            disabled={!invoiceEtag || !providerId || !policyCode || submitting || loading}
            onClick={() => void requestEstimate()}
          >
            {submitting ? "Requesting estimate…" : "Request estimate"}
          </button>
          {estimateError !== null && (
            <AdmissionFeedback
              error={estimateError}
              operationLabel="Estimate request"
              retryLabel="Retry estimate request"
              onRetry={() => void requestEstimate()}
            />
          )}
        </div>
      ) : (
        <p className="phase4-inline-status">
          Provider and policy choices are supplied by the coordinator. Existing estimates remain available above.
        </p>
      )}
    </section>
  );
}

function runStateLabel(state: InsuranceRunStatus["state"]): string {
  return state.replaceAll("_", " ");
}

export function InsuranceRefreshPanel({ api, roleHints }: InsuranceRefreshPanelProps) {
  const canRefresh = roleHints.includes("billing_staff") || roleHints.includes("hospital_admin");
  const [providers, setProviders] = useState<InsuranceProvider[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [providerEtag, setProviderEtag] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [refreshError, setRefreshError] = useState<unknown>(null);
  const [retryProviderId, setRetryProviderId] = useState<string | null>(null);
  const [pendingProvider, setPendingProvider] = useState<string | null>(null);
  const [runs, setRuns] = useState<Record<string, InsuranceRunStatus>>({});
  const [runErrors, setRunErrors] = useState<Record<string, unknown>>({});
  const [checkingRun, setCheckingRun] = useState<string | null>(null);
  const [loadCount, setLoadCount] = useState(0);
  const idempotencyKeys = useRef(new Map<string, string>());

  const loadProviders = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setLoadError(null);
    try {
      const params = new URLSearchParams({ limit: "20" });
      const response = await api.requestWithMetadata<InsuranceProviderPage>(
        "/api/v1/billing/insurance/providers?" + params.toString(),
        { method: "GET", signal, referrerPolicy: "no-referrer" },
      );
      if (!validProviderPage(response.data)) {
        throw new Error("Billing returned an unsupported insurance provider response.");
      }
      setProviders(response.data.items);
      setNextCursor(response.data.next_cursor);
      setProviderEtag(response.etag);
    } catch (requestError) {
      if (!isAbort(requestError)) setLoadError(requestError);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (!canRefresh) return;
    const controller = new AbortController();
    void loadProviders(controller.signal);
    return () => controller.abort();
  }, [canRefresh, loadProviders, loadCount]);

  if (!canRefresh) {
    return (
      <section className="phase4-panel" aria-label="Insurance provider refresh">
        <p role="status">Provider refresh controls are available to Billing staff and hospital administrators. Billing checks current authority on every request.</p>
      </section>
    );
  }

  async function loadMoreProviders() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setLoadError(null);
    try {
      const params = new URLSearchParams({ cursor: nextCursor, limit: "20" });
      const response = await api.requestWithMetadata<InsuranceProviderPage>(
        "/api/v1/billing/insurance/providers?" + params.toString(),
        { method: "GET", referrerPolicy: "no-referrer" },
      );
      if (!validProviderPage(response.data)) {
        throw new Error("Billing returned an unsupported insurance provider response.");
      }
      setProviders((current) => [...current, ...response.data.items]);
      setNextCursor(response.data.next_cursor);
      if (response.etag) setProviderEtag(response.etag);
    } catch (requestError) {
      setLoadError(requestError);
    } finally {
      setLoadingMore(false);
    }
  }

  async function requestRefresh(providerId: string) {
    const version=providers.find(provider => provider.id === providerId)?.version;
    const etag=version ? `"${version}"` : providerEtag;
    if (!etag || pendingProvider) {
      if (!providerEtag) setRefreshError(new Error("Billing did not provide a version for the provider list. Refresh cannot be requested safely."));
      return;
    }
    setPendingProvider(providerId);
    setRetryProviderId(providerId);
    setRefreshError(null);
    try {
      let key = idempotencyKeys.current.get(providerId);
      if (!key) {
        key = createIdempotencyKey();
        idempotencyKeys.current.set(providerId, key);
      }
      const response = await api.requestWithMetadata<InsuranceRefreshRun>(
        "/api/v1/billing/insurance/providers/" + encodeURIComponent(providerId) + "/refresh",
        {
          method: "POST",
          body: {},
          ifMatch: etag,
          idempotencyKey: key,
          referrerPolicy: "no-referrer",
        },
      );
      if (response.status !== 202 || response.data.provider_id !== providerId) {
        throw new Error("Billing did not accept the insurance refresh request.");
      }
      idempotencyKeys.current.delete(providerId);
      setRuns((current) => ({
        ...current,
        [providerId]: {
          id: response.data.run_id,
          provider_id: response.data.provider_id,
          state: response.data.state,
          pages_processed: 0,
          error_code: null,
          version: response.data.version,
        },
      }));
      setRefreshError(null);
      setRetryProviderId(null);
    } catch (requestError) {
      setRefreshError(requestError);
    } finally {
      setPendingProvider(null);
    }
  }

  async function checkRun(providerId: string) {
    const run = runs[providerId];
    if (!run) return;
    setCheckingRun(providerId);
    setRunErrors((current) => ({ ...current, [providerId]: null }));
    try {
      const response = await api.requestWithMetadata<InsuranceRunStatus>(
        "/api/v1/billing/insurance/runs/" + encodeURIComponent(run.id),
        { method: "GET", referrerPolicy: "no-referrer" },
      );
      if (
        response.data.id !== run.id
        || response.data.provider_id !== providerId
        || !["pending", "running", "complete", "partial", "failed"].includes(response.data.state)
        || !Number.isSafeInteger(response.data.pages_processed)
        || !Number.isSafeInteger(response.data.version)
      ) {
        throw new Error("Billing returned an unsupported insurance refresh status.");
      }
      setRuns((current) => ({ ...current, [providerId]: response.data }));
    } catch (requestError) {
      setRunErrors((current) => ({ ...current, [providerId]: requestError }));
    } finally {
      setCheckingRun(null);
    }
  }

  return (
    <section className="phase4-panel" aria-labelledby="phase4-insurance-refresh-heading">
      <div className="phase4-panel__heading">
        <div>
          <p className="phase4-eyebrow">Billing staff</p>
          <h3 id="phase4-insurance-refresh-heading">Synthetic provider sources</h3>
        </div>
        <span className="phase4-feature-indicator">Allowlisted sources</span>
      </div>
      <p className="phase4-panel__description">
        Refresh requests use the Billing provider catalog and never accept a URL or patient information.
      </p>
      {loading && <p role="status">Loading insurance providers…</p>}
      {loadError !== null && (
        <AdmissionFeedback
          error={loadError}
          operationLabel="Insurance providers"
          retryLabel="Retry provider list"
          onRetry={() => setLoadCount((count) => count + 1)}
        />
      )}
      {!loading && !loadError && providers.length === 0 && <p className="phase4-empty">No synthetic insurance providers were returned.</p>}
      {refreshError !== null && (
        <AdmissionFeedback
          error={refreshError}
          operationLabel="Insurance refresh"
          retryLabel="Retry refresh request"
          onRetry={() => retryProviderId && void requestRefresh(retryProviderId)}
        />
      )}
      <div className="phase4-provider-list">
        {providers.map((provider) => {
          const run = runs[provider.id];
          const runError = runErrors[provider.id];
          return (
            <article className="phase4-provider" key={provider.id}>
              <div>
                <h4>{provider.synthetic_slug}</h4>
                <p className="phase4-muted">Last successful refresh: {dateLabel(provider.last_success_at)}</p>
              </div>
              <button
                className="button button--secondary button--small"
                type="button"
                disabled={loading || pendingProvider !== null || (!provider.version && !providerEtag)}
                onClick={() => void requestRefresh(provider.id)}
              >
                {pendingProvider === provider.id ? "Requesting…" : "Refresh source"}
              </button>
              {run && (
                <div className="phase4-run-status">
                  <p role="status">
                    Latest run: {runStateLabel(run.state)} · {run.pages_processed} pages processed
                    {run.error_code ? " · " + run.error_code : ""}
                  </p>
                  {run.state === "pending" || run.state === "running" ? (
                    <button
                      className="phase4-text-button"
                      type="button"
                      disabled={checkingRun !== null}
                      onClick={() => void checkRun(provider.id)}
                    >
                      {checkingRun === provider.id ? "Checking…" : "Check refresh status"}
                    </button>
                  ) : null}
                  {runError != null && (
                    <AdmissionFeedback
                      error={runError}
                      operationLabel="Refresh status"
                      retryLabel="Retry status"
                      onRetry={() => void checkRun(provider.id)}
                    />
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
      {nextCursor && (
        <button className="button button--secondary button--small" type="button" disabled={loadingMore} onClick={() => void loadMoreProviders()}>
          {loadingMore ? "Loading…" : "Load more providers"}
        </button>
      )}
      {!providerEtag && providers.some(provider => !provider.version) && !loading && !loadError && providers.length > 0 && (
        <p className="phase4-inline-status">Provider refresh is unavailable because Billing did not return an ETag.</p>
      )}
    </section>
  );
}
