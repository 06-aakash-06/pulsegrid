import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ApiClient, type ApiResponse } from "../../api/client";
import { useAuth } from "../../auth/authContext";
import { getErrorMessage } from "./api";
import type { Page } from "./contracts";

export type GateState = "checking" | "anonymous" | "forbidden" | "ready";

export function usePatientAccess(): {
  api: ApiClient;
  gate: GateState;
  sessionKey: string;
} {
  const { state, api } = useAuth();
  const gate: GateState = state.status === "checking"
    ? "checking"
    : state.status === "anonymous"
      ? "anonymous"
      : state.roleHints.includes("patient")
        ? "ready"
        : "forbidden";
  const sessionKey = state.status === "authenticated"
    ? `${state.accessToken}:${state.roleHints.join(",")}`
    : state.status;
  return { api, gate, sessionKey };
}

export interface LoadState<T> {
  data: T | null;
  etag: string | null;
  loading: boolean;
  error: string | null;
  reload(): void;
}

export function useLoad<T>(
  api: ApiClient,
  path: string | null,
  enabled: boolean,
): LoadState<T> {
  const [response, setResponse] = useState<ApiResponse<T> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setRevision((value) => value + 1);
  }, []);

  useEffect(() => {
    setResponse(null);
    setError(null);
    setLoading(Boolean(enabled && path));
    if (!enabled || !path) return;
    const controller = new AbortController();
    void api.requestWithMetadata<T>(path, { signal: controller.signal })
      .then((next) => {
        if (!controller.signal.aborted) setResponse(next);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(getErrorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, enabled, path, revision]);

  return {
    data: response?.data ?? null,
    etag: response?.etag ?? null,
    loading,
    error,
    reload,
  };
}

export interface PagedLoadState<T> {
  items: T[];
  nextCursor: string | null;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  loadMoreError: string | null;
  reload(): void;
  loadMore(): void;
}

export function usePagedItems<T>(
  api: ApiClient,
  path: string | null,
  enabled: boolean,
): PagedLoadState<T> {
  const [items, setItems] = useState<T[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const moreControllerRef = useRef<AbortController | null>(null);
  const reload = useCallback(() => {
    setItems([]);
    setNextCursor(null);
    setLoading(true);
    setError(null);
    setLoadMoreError(null);
    setLoadingMore(false);
    moreControllerRef.current?.abort();
    setRevision((value) => value + 1);
  }, []);

  useEffect(() => {
    setItems([]);
    setNextCursor(null);
    setError(null);
    setLoadMoreError(null);
    setLoadingMore(false);
    setLoading(Boolean(enabled && path));
    if (!enabled || !path) return;
    const controller = new AbortController();
    void api.request<Page<T>>(path, { signal: controller.signal })
      .then((page) => {
        if (controller.signal.aborted) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(getErrorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      moreControllerRef.current?.abort();
    };
  }, [api, enabled, path, revision]);

  async function loadMore() {
    if (!enabled || !path || !nextCursor || loadingMore) return;
    moreControllerRef.current?.abort();
    const controller = new AbortController();
    moreControllerRef.current = controller;
    setLoadingMore(true);
    setLoadMoreError(null);
    const separator = path.includes("?") ? "&" : "?";
    const cursorPath = `${path}${separator}cursor=${encodeURIComponent(nextCursor)}`;
    try {
      const page = await api.request<Page<T>>(cursorPath, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setItems((current) => [...current, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (reason) {
      if (!controller.signal.aborted) setLoadMoreError(getErrorMessage(reason));
    } finally {
      if (!controller.signal.aborted) setLoadingMore(false);
    }
  }

  return { items, nextCursor, loading, loadingMore, error, loadMoreError, reload, loadMore };
}

export interface PollState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  stopped: boolean;
  stale: boolean;
  lastSuccessAt: number | null;
  retryNow(): void;
}

export function usePolling<T>(
  api: ApiClient,
  key: string,
  enabled: boolean,
  poll: (signal: AbortSignal) => Promise<T>,
  intervalMs = 5000,
  merge?: (current: T | null, incoming: T) => T,
): PollState<T> {
  const [dataEnvelope, setDataEnvelope] = useState<{ key: string; data: T } | null>(null);
  const data = dataEnvelope?.key === key ? dataEnvelope.data : null;
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [stale, setStale] = useState(false);
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
  const [generation, setGeneration] = useState(0);
  const retryNow = useCallback(() => {
    setStopped(false);
    setGeneration((value) => value + 1);
  }, []);
  const pollRef = useRef(poll);
  const activeKeyRef = useRef<string | null>(null);
  pollRef.current = poll;

  useEffect(() => {
    const activeKey = enabled && key ? key : null;
    if (activeKeyRef.current !== activeKey) {
      activeKeyRef.current = activeKey;
      setDataEnvelope(null);
      setError(null);
      setLoading(false);
      setStopped(false);
      setStale(false);
      setLastSuccessAt(null);
    }
    if (!enabled || !key) return;

    let cancelled = false;
    let inFlight = false;
    let halted = false;
    let resumeRequested = false;
    let delayIndex = 0;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    const delays = [5000, 10000, 20000, 30000];

    const schedule = (delay: number) => {
      if (cancelled || document.hidden || halted) return;
      if (timer !== undefined) window.clearTimeout(timer);
      const jitter = 0.8 + Math.random() * 0.4;
      timer = window.setTimeout(() => void run(), Math.round(delay * jitter));
    };

    const run = async () => {
      if (cancelled || document.hidden || inFlight || halted) return;
      inFlight = true;
      controller = new AbortController();
      setLoading(data === null);
      try {
        const result = await pollRef.current(controller.signal);
        if (cancelled || controller.signal.aborted) return;
        setDataEnvelope((current) => {
          const currentData = current?.key === key ? current.data : null;
          return { key, data: merge ? merge(currentData, result) : result };
        });
        setError(null);
        setLastSuccessAt(Date.now());
        setStale(false);
        delayIndex = 0;
        schedule(intervalMs);
      } catch (reason) {
        if (cancelled || controller.signal.aborted) return;
        setError(getErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 403) {
          halted = true;
          setStopped(true);
          return;
        }
        const delay = delays[Math.min(delayIndex, delays.length - 1)];
        delayIndex = Math.min(delayIndex + 1, delays.length - 1);
        schedule(delay);
      } finally {
        inFlight = false;
        if (!cancelled && !controller?.signal.aborted) setLoading(false);
        if (resumeRequested && !cancelled && !halted && !document.hidden) {
          resumeRequested = false;
          queueMicrotask(() => void run());
        }
      }
    };

    const onVisibility = () => {
      if (document.hidden) {
        if (timer !== undefined) window.clearTimeout(timer);
        controller?.abort();
      } else {
        if (inFlight) resumeRequested = true;
        else void run();
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) void run();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  // `halted` is deliberately controlled inside a poll generation.
  }, [api, enabled, generation, intervalMs, key, merge]);

  useEffect(() => {
    if (lastSuccessAt === null) return;
    const updateStale = () => setStale(Date.now() - lastSuccessAt >= 15000);
    updateStale();
    const timer = window.setInterval(updateStale, 1000);
    return () => window.clearInterval(timer);
  }, [lastSuccessAt]);

  return { data, error, loading, stopped, stale, lastSuccessAt, retryNow };
}

export function PatientGate({ state }: { state: GateState }) {
  if (state === "checking") return <p role="status">Checking your session…</p>;
  if (state === "anonymous") {
    return <p role="alert">Sign in with a patient account to view this information.</p>;
  }
  if (state === "forbidden") {
    return <p role="alert">This patient workflow is available only to the signed-in patient.</p>;
  }
  return null;
}
