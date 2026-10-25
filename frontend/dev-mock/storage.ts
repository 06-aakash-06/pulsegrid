import { exportMockState, handleMockRequest, importMockState, type MockRequest, type MockResponse } from "./handlers";

export const MOCK_SESSION_KEY = "pulsegrid_mock_session";
/** Session credentials are separate from the persisted synthetic hospital data. */
export function clearMockSession(storage: Pick<Storage, "removeItem">) {
  storage.removeItem(MOCK_SESSION_KEY);
}

export const DEMO_STORE_KEY = "pulsegrid_demo_database_v1";
type DemoStorage = Pick<Storage, "getItem" | "setItem">;

/** Same-browser demo persistence, separate from the real API and from session credentials. */
export function createDemoStore(storage: () => DemoStorage) {
  let flight: Promise<unknown> = Promise.resolve();
  return (request: MockRequest): Promise<MockResponse> => {
    const transaction = async (): Promise<MockResponse> => {
      let previous: string | undefined;
      try {
        const database = storage();
        const saved = database.getItem(DEMO_STORE_KEY);
        if (saved) importMockState(saved);
        previous = exportMockState();
        const result = await handleMockRequest(request);
        if (request.method.toUpperCase() !== "GET") database.setItem(DEMO_STORE_KEY, exportMockState());
        return result;
      } catch {
        if (previous) importMockState(previous);
        return { status: 503, body: { error: { code: "demo_storage_unavailable", message: "This demo could not save your data in this browser. Allow site storage or free some browser storage, then retry.", request_id: "demo-storage" } } };
      }
    };
    const run = () => typeof navigator !== "undefined" && navigator.locks
      ? navigator.locks.request("pulsegrid-demo-database", transaction)
      : transaction();
    const result = flight.then(run, run);
    flight = result.catch(() => undefined);
    return result;
  };
}
