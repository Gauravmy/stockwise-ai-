"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => Promise<void>;
}

/** Fetch data on mount and whenever `deps` change; exposes loading/error/reload. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = [], enabled = true): ApiState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError>();
  const [loading, setLoading] = useState(enabled);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(undefined);
    try {
      const result = await fetcherRef.current();
      if (id === requestId.current) setData(result);
    } catch (e) {
      if (id === requestId.current) {
        setError(e instanceof ApiError ? e : new ApiError(String(e), 0, "client_error"));
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled) void load();
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, load, ...deps]);

  return { data, error, loading, reload: load };
}
