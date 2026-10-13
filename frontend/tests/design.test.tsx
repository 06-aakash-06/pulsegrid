import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/authContext";
import { createApiClient } from "../src/api/client";
import { HospitalHeader } from "../src/design/HospitalHeader";
import { AvailabilityPicker } from "../src/hospital/patientDoctor";
import { CheckinScanner } from "../src/hospital/staffAdvanced/CheckinScanner";
import {
  publishHospitalIdentity,
  clearHospitalIdentity,
} from "../src/design/hospitalIdentity";
import { gsap } from "gsap";
import { ReceptionScene } from "../src/design/ReceptionScene";
const token = `header.${btoa(JSON.stringify({ sub: "21", roles: ["patient"] }))}.signature`;
const client = {
  refresh: async () => ({
    access_token: token,
    token_type: "Bearer" as const,
    expires_in: 600,
  }),
  login: async () => ({
    access_token: token,
    token_type: "Bearer" as const,
    expires_in: 600,
  }),
  register: async () => ({
    id: "1",
    user_id: "21",
    display_name: "Synthetic Design",
    version: 1,
  }),
  logout: async () => undefined,
};
function mount(
  children: React.ReactNode,
  fetcher: typeof fetch = vi.fn(
    async () =>
      new Response("{}", { headers: { "Content-Type": "application/json" } }),
  ),
) {
  return render(
    <AuthProvider client={client} apiClient={createApiClient({ fetcher })}>
      <MemoryRouter>{children}</MemoryRouter>
    </AuthProvider>,
  );
}
afterEach(() => {
  clearHospitalIdentity();
  vi.restoreAllMocks();
});
describe("hospital design integration", () => {
  it("search exposes only destinations for the authenticated role", async () => {
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute("open", "");
    };
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute("open");
    };
    mount(<HospitalHeader roleLabel="Patient" />);
    await screen.findByText("Account …21");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Search hospital departments and workflows",
      }),
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Appointments Patient/ }),
    ).toHaveAttribute("href", "/patient/appointments");
    expect(
      screen.queryByRole("link", { name: /Control Room/ }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search your available workflows"), {
      target: { value: "records" },
    });
    expect(
      screen.getByRole("link", { name: /Medical Records Patient/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Appointments Patient/ }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Close hospital search" }),
    );
    expect(dialog).not.toHaveAttribute("open");
  });
  it("uses only an owner-confirmed identity for the same subject without another request", async () => {
    const fetcher = vi.fn(async () => new Response("{}"));
    mount(<HospitalHeader roleLabel="Patient" />, fetcher);
    await screen.findByText("Account …21");
    act(() => publishHospitalIdentity("999", "Another account"));
    expect(screen.queryByText("Another account")).not.toBeInTheDocument();
    act(() => publishHospitalIdentity("21", "Synthetic Confirmed Name"));
    expect(screen.getByText("Synthetic Confirmed Name")).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("date selection sets a UTC interval without making a booking or fetching prematurely", async () => {
    const fetcher = vi.fn(
      async (_url: RequestInfo | URL) =>
        new Response(
          JSON.stringify({
            slots: [],
            accepted_revision: 1,
            observed_at: "2026-10-13T10:00:00Z",
          }),
          { headers: { "Content-Type": "application/json" } },
        ),
    );
    mount(<AvailabilityPicker doctorId="31" />, fetcher);
    fireEvent.change(screen.getByLabelText("Choose date (UTC)"), {
      target: { value: "2026-10-20" },
    });
    expect(screen.getByLabelText("From (UTC)")).toHaveValue(
      "2026-10-20T00:00:00Z",
    );
    expect(screen.getByLabelText("To (UTC)")).toHaveValue(
      "2026-10-21T00:00:00.000Z",
    );
    expect(fetcher).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Load availability" }));
    await screen.findByText("No available slots in this interval.");
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(String(fetcher.mock.calls[0]?.[0])).toContain("doctor_id=31");
  });
  it("does not run the reception scene introduction when motion is reduced", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
      })),
    );
    const animate = vi.spyOn(gsap, "fromTo");
    render(
      <MemoryRouter>
        <ReceptionScene publicView />
      </MemoryRouter>,
    );
    expect(animate).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
describe("camera permission lifecycle", () => {
  it("stops a camera stream whose permission resolves after the scanner unmounts", async () => {
    let resolve!: (stream: MediaStream) => void;
    const permission = new Promise<MediaStream>((r) => (resolve = r));
    const stop = vi.fn();
    const original = navigator.mediaDevices;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(() => permission) },
    });
    vi.stubGlobal(
      "BarcodeDetector",
      class {
        detect = async () => [];
      },
    );
    const view = render(<CheckinScanner onScan={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Scan check-in QR" }));
    await screen.findByRole("button", { name: "Cancel camera request" });
    view.unmount();
    await act(async () =>
      resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream),
    );
    await waitFor(() => expect(stop).toHaveBeenCalledOnce());
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: original,
    });
    vi.unstubAllGlobals();
  });
  it("allows cancelling a pending permission and keeps the manual fallback explicit", async () => {
    let resolve!: (stream: MediaStream) => void;
    const permission = new Promise<MediaStream>((r) => (resolve = r));
    const stop = vi.fn();
    const original = navigator.mediaDevices;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(() => permission) },
    });
    vi.stubGlobal(
      "BarcodeDetector",
      class {
        detect = async () => [];
      },
    );
    render(<CheckinScanner onScan={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Scan check-in QR" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Cancel camera request" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Camera request cancelled",
    );
    await act(async () =>
      resolve({ getTracks: () => [{ stop }] } as unknown as MediaStream),
    );
    await waitFor(() => expect(stop).toHaveBeenCalledOnce());
    expect(
      screen.getByRole("button", { name: "Scan check-in QR" }),
    ).toBeEnabled();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: original,
    });
    vi.unstubAllGlobals();
  });
});
