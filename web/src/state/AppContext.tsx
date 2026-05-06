import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { ConfigImportResponse, ConfigsListResponse, SnapshotResponse } from "../api/types";

interface AppContextValue {
  snapshot: SnapshotResponse | null;
  bootStatus: "loading" | "live" | "error";
  bootError: string | null;
  refreshKey: number;
  refresh: () => Promise<void>;
  activeProviderId: string;
  setActiveProviderId: (id: string) => Promise<void>;
  diagnosisProvider: string;
  setDiagnosisProvider: (id: string) => void;
  configs: ConfigsListResponse | null;
  loadConfigs: () => Promise<ConfigsListResponse | null>;
  selectConfig: (choice: { id?: string; path?: string; source?: string }) => Promise<void>;
  importConfig: (payload: {
    name: string;
    yaml: string;
    overwrite?: boolean;
    select?: boolean;
  }) => Promise<ConfigImportResponse>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<SnapshotResponse | null>(null);
  const [bootStatus, setBootStatus] = useState<"loading" | "live" | "error">("loading");
  const [bootError, setBootError] = useState<string | null>(null);
  const [activeProviderId, setActiveProviderIdState] = useState<string>("");
  const [diagnosisProvider, setDiagnosisProvider] = useState<string>("rules");
  const [refreshKey, setRefreshKey] = useState(0);
  const [configs, setConfigs] = useState<ConfigsListResponse | null>(null);

  const applySnapshot = useCallback((data: SnapshotResponse) => {
    setSnapshot(data);
    setActiveProviderIdState(data.active_provider || (data.providers[0]?.id ?? ""));
    setDiagnosisProvider((current) =>
      current && data.diagnosis_providers.includes(current)
        ? current
        : data.diagnosis_provider || data.diagnosis_providers[0] || "rules",
    );
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await api.snapshot();
      applySnapshot(data);
      setBootStatus("live");
      setBootError(null);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "snapshot failed";
      setBootStatus("error");
      setBootError(msg);
    }
  }, [applySnapshot]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setActiveProviderId = useCallback(
    async (id: string) => {
      setActiveProviderIdState(id);
      try {
        await api.setActiveProvider(id);
        await refresh();
      } catch {
        /* keep local UI state, surfacing of errors handled per-page */
      }
    },
    [refresh],
  );

  const loadConfigs = useCallback(async () => {
    try {
      const list = await api.listConfigs();
      setConfigs(list);
      return list;
    } catch {
      return null;
    }
  }, []);

  const selectConfig = useCallback(
    async (choice: { id?: string; path?: string; source?: string }) => {
      await api.selectConfig(choice);
      await Promise.all([refresh(), loadConfigs()]);
    },
    [refresh, loadConfigs],
  );

  const importConfig = useCallback(
    async (payload: { name: string; yaml: string; overwrite?: boolean; select?: boolean }) => {
      const result = await api.importConfig(payload);
      await Promise.all([refresh(), loadConfigs()]);
      return result;
    },
    [refresh, loadConfigs],
  );

  const value = useMemo<AppContextValue>(
    () => ({
      snapshot,
      bootStatus,
      bootError,
      refreshKey,
      refresh,
      activeProviderId,
      setActiveProviderId,
      diagnosisProvider,
      setDiagnosisProvider,
      configs,
      loadConfigs,
      selectConfig,
      importConfig,
    }),
    [
      snapshot,
      bootStatus,
      bootError,
      refreshKey,
      refresh,
      activeProviderId,
      setActiveProviderId,
      diagnosisProvider,
      configs,
      loadConfigs,
      selectConfig,
      importConfig,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
