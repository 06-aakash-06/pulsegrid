import { describe, expect, it, vi } from "vitest";
import { ApiConfigurationError, createApiClient } from "../src/api/client";
import { createAuthApi } from "../src/api/authApi";

describe("API client", () => {
  it("adds protocol identifiers and bearer authorization without persisting tokens", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "12345678901234567" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = createApiClient({ baseUrl: "https://pulsegrid.test", fetcher });

    await expect(client.request<{ id: string }>("/api/v1/example", {
      accessToken: "temporary-access-token",
      method: "GET",
    })).resolves.toEqual({ id: "12345678901234567" });

    const [url, init] = fetcher.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(url).toBe("https://pulsegrid.test/api/v1/example");
    expect(headers.get("Authorization")).toBe("Bearer temporary-access-token");
    expect(headers.get("X-Request-ID")).toMatch(/^[0-9a-f-]{36}$/i);
    expect(headers.get("X-Correlation-ID")).toMatch(/^[0-9a-f-]{36}$/i);
    expect(init?.credentials).toBe("omit");
  });

  it("exposes only the documented safe error envelope fields", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "conflict", message: "Request could not be applied.", request_id: "req-1", details: { private: "ignored" } } }), {
        status: 409,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = createApiClient({ fetcher });

    await expect(client.request("/api/v1/example")).rejects.toMatchObject({
      name: "ApiError",
      code: "conflict",
      message: "Request could not be applied.",
      requestId: "req-1",
      status: 409,
    });
  });

  it("preserves the ETag needed for conditional aggregate updates", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ version: 7 }), {
        status: 200,
        headers: { "content-type": "application/json", ETag: '"7"' },
      }),
    );
    const client = createApiClient({ fetcher });

    await expect(client.requestWithMetadata<{ version: number }>("/api/v1/example"))
      .resolves.toMatchObject({ data: { version: 7 }, etag: '"7"', status: 200 });
  });

  it("does not send cookie authentication requests without a CSRF provider", async () => {
    const fetcher = vi.fn<typeof fetch>();
    const client = createApiClient({ fetcher });
    const auth = createAuthApi(client);

    await expect(auth.login({ email: "synthetic@example.test", password: "test-only-password" }))
      .rejects.toBeInstanceOf(ApiConfigurationError);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("uses the proposed login route with cookies and injected CSRF headers", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ access_token: "token", token_type: "Bearer", expires_in: 600 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = createApiClient({ fetcher });
    const auth = createAuthApi(client, () => ({ "X-CSRF-Integration": "test-only" }));

    await auth.login({ email: "synthetic@example.test", password: "test-only-password" });

    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/auth/login");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("X-CSRF-Integration")).toBe("test-only");
  });

  it("uses cookie credentials and injected CSRF headers for refresh and logout", async () => {
    const tokenResponse = () => new Response(JSON.stringify({
      access_token: "short-lived-access-token",
      token_type: "Bearer",
      expires_in: 600,
    }), { status: 200, headers: { "content-type": "application/json" } });
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = createApiClient({ fetcher });
    const auth = createAuthApi(client, () => ({ "X-CSRF-Integration": "host-managed" }));

    await auth.refresh();
    await auth.logout();

    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/refresh",
      "/api/v1/auth/logout",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init?.credentials).toBe("include");
      expect(new Headers(init?.headers).get("X-CSRF-Integration")).toBe("host-managed");
    }
  });

  it("sends only contract registration fields without cookie authentication", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "1", user_id: "2", display_name: "Synthetic Patient", version: 1 }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    const auth = createAuthApi(createApiClient({ fetcher }));

    await auth.register({
      email: "patient@example.test",
      password: "synthetic passphrase",
      display_name: "Synthetic Patient",
      date_of_birth: "2000-01-02",
      synthetic_contact: "synthetic@example.test",
    });

    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/auth/register");
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "patient@example.test",
      password: "synthetic passphrase",
      display_name: "Synthetic Patient",
      date_of_birth: "2000-01-02",
      synthetic_contact: "synthetic@example.test",
    });
    expect(init?.credentials).toBe("omit");
  });

  it("normalizes network failures while preserving request cancellation", async () => {
    const unavailableFetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline"));
    const unavailableClient = createApiClient({ fetcher: unavailableFetcher });
    await expect(unavailableClient.request("/api/v1/example")).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      code: "network_error",
    });

    const abortFetcher = vi.fn<typeof fetch>().mockRejectedValue(new DOMException("Cancelled", "AbortError"));
    const abortClient = createApiClient({ fetcher: abortFetcher });
    await expect(abortClient.request("/api/v1/example")).rejects.toMatchObject({ name: "AbortError" });
  });

  it("rejects protocol-relative API paths before sending a request", async () => {
    const fetcher = vi.fn<typeof fetch>();
    const client = createApiClient({ fetcher });

    await expect(client.request("//untrusted.example/api/v1/auth/login"))
      .rejects.toBeInstanceOf(ApiConfigurationError);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
