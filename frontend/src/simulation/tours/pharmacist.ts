import type { Tour } from "../types";

export const pharmacistTour: Tour = {
  id: "pharmacist",
  role: "pharmacist",
  workspace: "/pharmacist",
  roleLabel: "Pharmacist",
  title: "Fill a prescription",
  goal: "Find a medicine, check its stock and dispense a reserved prescription.",
  summary: "You've seen how a pharmacist checks stock batch by batch, opens a patient's reservation and dispenses it.",
  steps: [
    {
      id: "inventory-nav", route: "/pharmacist/dashboard", target: "nav-inventory",
      title: "Open Inventory",
      body: "Inventory shows every medicine on the shelves.",
      advanceOn: { type: "route", value: "^/pharmacist/inventory" },
    },
    {
      id: "search", target: "medicine-search",
      title: "Search with autocomplete",
      body: "Start typing a medicine name to see matching suggestions, then press Next.",
      behindTheScenes: "Suggestions come from a cached autocomplete index; the cache only speeds up search and is never trusted for stock levels.",
      advanceOn: { type: "manual" },
    },
    {
      id: "shelf", target: "shelf-medicine",
      title: "Pick a medicine",
      body: "Select a carton on the shelf to open its catalog entry.",
      advanceOn: { type: "visible", value: "batch-ledger" },
    },
    {
      id: "batches", target: "batch-ledger",
      title: "Check its batches",
      body: "Each batch shows its expiry and how much is on hand, reserved and still available.",
      behindTheScenes: "Stock is tracked per batch in the Pharmacy database, so reservations take the earliest-expiring stock first.",
      advanceOn: { type: "manual" },
    },
    {
      id: "dispensing", target: "open-dispensing",
      title: "Open the dispensing workspace",
      body: "Dispensing happens against a patient's reservation.",
      advanceOn: { type: "route", value: "^/pharmacist/prescriptions" },
    },
    {
      id: "reservation", target: "reservation-option",
      title: "Open the reservation",
      body: "Review the patient's reserved medicines.",
      advanceOn: { type: "visible", value: "dispense-review" },
    },
    {
      id: "dispense-review", target: "dispense-review",
      title: "Review dispensing",
      body: "Check the quantities you are about to hand over.",
      advanceOn: { type: "visible", value: "dispense-confirm" },
    },
    {
      id: "dispense-confirm", target: "dispense-confirm", mutates: true,
      title: "Dispense",
      body: "Confirm to record the hand-over.",
      behindTheScenes: "Dispensing turns the reservation into a permanent stock movement in one transaction and emits an event so Billing can charge for it.",
      advanceOn: { type: "event", value: "Dispense reservation" },
    },
  ],
};
