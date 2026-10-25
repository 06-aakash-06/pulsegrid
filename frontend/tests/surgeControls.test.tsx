import { commandLabels } from "./commandLabels";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ApiError } from "../src/api/client";
const mocks = vi.hoisted(() => ({
  roles: ["ops"],
  requestWithMetadata: vi.fn(),
}));
vi.mock("../src/auth/authContext", () => ({
  useAuth: () => ({
    state: {
      status: "authenticated",
      user: { id: "21", roleHints: mocks.roles },
      roleHints: mocks.roles,
    },
    api: { requestWithMetadata: mocks.requestWithMetadata },
  }),
}));
import { SurgeModeControls } from "../src/ops/SurgeModeControls";
const snapshot = {
  state: "NORMAL",
  version: 4,
  changed_at: null,
  expires_at: null,
  reason_code: "recovery_elapsed",
};
function mount() {
  render(
    <MemoryRouter>
      <SurgeModeControls onChange={vi.fn()} />
    </MemoryRouter>,
  );
}
afterEach(cleanup);
beforeEach(() => {
  mocks.roles = ["ops"];
  mocks.requestWithMetadata.mockReset();
});
describe("owner-authorized Surge controls", () => {
  it("keeps the Operations role read-only and does not call the admin-only endpoint", () => {
    mount();
    expect(screen.queryByText(/Surge Mode controls/)).not.toBeInTheDocument();
    expect(mocks.requestWithMetadata).not.toHaveBeenCalled();
  });
  it("requires explicit incident override agreement and freezes the correct server command", async () => {
    mocks.roles = ["hospital_admin"];
    mocks.requestWithMetadata.mockResolvedValue({ data: snapshot, etag: null });
    mount();
    await screen.findByLabelText(/Requested operation/);
    fireEvent.change(screen.getByLabelText(/Requested operation/), {
      target: { value: "true" },
    });
    fireEvent.change(screen.getByLabelText(/Operational reason/), {
      target: { value: "incident_override" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Change Surge Mode").review }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "explicitly selected override policy",
    );
    expect(
      mocks.requestWithMetadata.mock.calls.filter(
        ([, options]) => options?.method === "POST",
      ),
    ).toHaveLength(0);
    fireEvent.change(screen.getByLabelText(/Transition policy/), {
      target: { value: "true" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Change Surge Mode").review }),
    );
    expect(screen.getByLabelText(/Requested operation/)).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Change Surge Mode").confirm }),
    );
    await waitFor(() =>
      expect(mocks.requestWithMetadata).toHaveBeenCalledWith(
        "/api/v1/appointments/operations/surge-mode",
        expect.objectContaining({
          method: "POST",
          body: {
            active: true,
            reason_code: "incident_override",
            override: true,
          },
          idempotencyKey: expect.any(String),
        }),
      ),
    );
  });
  it("does not render a command when the authoritative mode lookup fails", async () => {
    mocks.roles = ["hospital_admin"];
    mocks.requestWithMetadata.mockRejectedValue(
      new ApiError("Admission state unavailable", 503, "admission_unavailable"),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Admission state unavailable",
    );
    expect(
      screen.queryByRole("button", { name: commandLabels("Change Surge Mode").review }),
    ).not.toBeInTheDocument();
  });
});
