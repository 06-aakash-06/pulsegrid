import type { Tour } from "../types";

export const doctorTour: Tour = {
  id: "doctor",
  role: "doctor",
  workspace: "/doctor",
  roleLabel: "Doctor",
  title: "Run a consultation",
  goal: "See today's queue, write a consultation, prescribe and finalize it.",
  summary: "You've seen how a doctor works through the queue, writes a draft, prescribes medicine and finalizes the visit into a permanent record.",
  steps: [
    {
      id: "queue-nav", route: "/doctor/dashboard", target: "nav-queue",
      title: "Open today's queue",
      body: "Queue management lists the patients who have checked in to see you.",
      advanceOn: { type: "route", value: "^/doctor/queue" },
    },
    {
      id: "queue", target: "doctor-queue",
      title: "Today's queue",
      body: "Patients are listed in token order with their position.",
      behindTheScenes: "The Appointment service owns the queue. Position changes are made under a row lock, so two doctors calling at once can't take the same patient.",
      advanceOn: { type: "manual" },
    },
    {
      id: "call-next", target: "queue-call-next",
      title: "Call the next patient",
      body: "Call next patient moves the first waiting patient into consultation. It stays disabled while someone is already with you, as it is now.",
      advanceOn: { type: "manual" },
    },
    {
      id: "consultations-nav", target: "nav-consultations",
      title: "Open the consultation",
      body: "The patient with you has a draft consultation ready.",
      advanceOn: { type: "route", value: "^/doctor/consultations" },
    },
    {
      id: "draft", target: "save-draft",
      title: "Write the draft",
      body: "Edit the summary, assessment and plan in these fields, then press Next.",
      advanceOn: { type: "manual" },
    },
    {
      id: "draft-review", target: "save-draft-review",
      title: "Review the draft",
      body: "Review the changes before saving them.",
      advanceOn: { type: "visible", value: "save-draft-confirm" },
    },
    {
      id: "draft-save", target: "save-draft-confirm", mutates: true,
      title: "Save the draft",
      body: "Saving keeps your notes without making them final.",
      behindTheScenes: "The save carries the consultation's version (If-Match). If someone else saved in the meantime, you're asked to reload instead of overwriting their work.",
      advanceOn: { type: "event", value: "Save consultation draft" },
    },
    {
      id: "prescription-open", target: "prescription-items",
      title: "Add a prescription",
      body: "Open Prescribed medicines to prescribe alongside the visit.",
      prepare: (api) => api.openDisclosure("prescription-items"),
      advanceOn: { type: "visible", value: "add-prescribed-medicine" },
    },
    {
      id: "prescription-add", target: "add-prescribed-medicine",
      title: "Add a medicine",
      body: "Add a line for one medicine.",
      advanceOn: { type: "click" },
    },
    {
      id: "prescription-fill", target: "prescription-items",
      title: "Fill in the medicine",
      body: "Type medicine ID 3001 (Paracetamol), quantity 10, a dosage such as \"1 tablet\" and instructions, then press Next.",
      advanceOn: { type: "manual" },
    },
    {
      id: "finalize-review", target: "finalize-review",
      title: "Review finalization",
      body: "Finalizing turns the draft into a permanent medical record and issues the prescription.",
      advanceOn: { type: "visible", value: "finalize-confirm" },
    },
    {
      id: "finalize-confirm", target: "finalize-confirm", mutates: true,
      title: "Finalize the consultation",
      body: "Confirm to finalize. The badge changes to Finalized.",
      behindTheScenes: "The record, the prescription and an outbox event are written in one Records transaction. Pharmacy and Billing hear about it from the event afterwards.",
      advanceOn: { type: "visible", value: "consultation-finalized" },
    },
  ],
};
