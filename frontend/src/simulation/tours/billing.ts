import type { Tour } from "../types";

export const billingTour: Tour = {
  id: "billing",
  role: "billing_staff",
  workspace: "/billing",
  roleLabel: "Billing staff",
  title: "Bill a visit",
  goal: "Open an invoice, check its charges and record a payment.",
  summary: "You've seen how billing staff open an invoice, check its charge lines, record a payment and watch the balance update.",
  steps: [
    {
      id: "invoice", route: "/billing/dashboard", target: "invoice-option",
      title: "Select an invoice",
      body: "Each visit has one invoice. Open it at the cashier's desk.",
      advanceOn: { type: "click" },
    },
    {
      id: "import", target: "charge-import",
      title: "Import charges",
      body: "Consultation and pharmacy charges are imported from finalized records and completed dispensings, priced from the tariff list.",
      behindTheScenes: "Billing never reads the Records or Pharmacy databases. It imports by reference through their APIs, and each source can be imported only once.",
      advanceOn: { type: "manual" },
    },
    {
      id: "lines", target: "receipt-lines",
      title: "Check the receipt lines",
      body: "The receipt groups charges by where they came from.",
      advanceOn: { type: "manual" },
    },
    {
      id: "pay-review", target: "pay-review",
      title: "Record a payment",
      body: "The amount is filled in with the balance. Review it.",
      advanceOn: { type: "visible", value: "pay-confirm" },
    },
    {
      id: "pay-confirm", target: "pay-confirm", mutates: true,
      title: "Confirm the payment",
      body: "Confirm to record the payment. No card is charged.",
      behindTheScenes: "Money is stored as whole paise, never as decimals, and the payment is written with the invoice's new balance in one transaction.",
      advanceOn: { type: "event", value: "Submit payment" },
    },
    {
      id: "balance", target: "invoice-balance",
      title: "The balance updates",
      body: "Paid and balance due now include the payment.",
      advanceOn: { type: "manual" },
    },
  ],
};
