import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

// Browser geometry and dialogs are exercised in live visual QA. jsdom supplies no implementations.
window.scrollTo = vi.fn();
