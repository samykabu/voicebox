import { type QueryClient, useQuery } from '@tanstack/react-query';
import { OpenAPI } from '@/lib/api/core/OpenAPI';
import { request } from '@/lib/api/core/request';
import type { EngineCapabilitiesResponse } from '@/lib/api/models/EngineCapabilitiesResponse';
import type { EngineCapabilityResponse } from '@/lib/api/models/EngineCapabilityResponse';
import { useServerStore } from '@/stores/serverStore';

/**
 * Fetch GET /models/engines through the generated client's request core.
 *
 * The generated services call the global `OpenAPI` config, whose BASE is never set in
 * this app, so they would hit the page origin instead of the backend. Passing a copy of
 * that config with BASE set to the user's configured server URL keeps the generated
 * request path and types while honouring the server the user chose.
 */
export function fetchEngineCapabilities(serverUrl: string): Promise<EngineCapabilitiesResponse> {
  return request<EngineCapabilitiesResponse>(
    { ...OpenAPI, BASE: serverUrl },
    { method: 'GET', url: '/models/engines' },
  );
}

/**
 * Engine capabilities reported by the backend, one entry per TTS engine.
 *
 * The UI decides what to show from these capability fields, never from engine names.
 */
export function useEngineCapabilities() {
  const serverUrl = useServerStore((state) => state.serverUrl);

  return useQuery({
    ...engineCapabilitiesQueryOptions(serverUrl),
    enabled: !!serverUrl,
  });
}

/** The query key, function and freshness shared by the hook and `loadEngineCapabilities`. */
export function engineCapabilitiesQueryOptions(serverUrl: string) {
  return {
    queryKey: ['engine-capabilities', serverUrl],
    queryFn: () => fetchEngineCapabilities(serverUrl),
    staleTime: 1000 * 60,
  };
}

/**
 * The capability list for a decision that must not guess (FR-018): the cached list when it is
 * fresh, otherwise fetched now through the same query. Resolves to undefined when it cannot be
 * loaded, so the caller can fail closed.
 */
export async function loadEngineCapabilities(
  queryClient: QueryClient,
  serverUrl: string,
): Promise<EngineCapabilitiesResponse | undefined> {
  if (!serverUrl) return undefined;
  try {
    return await queryClient.fetchQuery(engineCapabilitiesQueryOptions(serverUrl));
  } catch (error) {
    console.error('Failed to load engine capabilities:', error);
    return undefined;
  }
}

/** Find one engine's capabilities by its id, or undefined when it is not reported. */
export function findEngineCapability(
  capabilities: EngineCapabilitiesResponse | undefined,
  engineId: string | null | undefined,
): EngineCapabilityResponse | undefined {
  if (!capabilities || !engineId) return undefined;
  return capabilities.engines.find((entry) => entry.engine === engineId);
}
