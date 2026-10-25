import type { Tour } from "../types";

export const emergencyTour: Tour = {
  id: "emergency",
  role: "emergency_staff",
  workspace: "/emergency",
  roleLabel: "Emergency staff",
  title: "Triage a request",
  goal: "Pick the most urgent request, set its priority, claim it and start processing.",
  summary: "You've seen how emergency staff triage the queue: set a priority, claim the case so nobody else works it, and start processing.",
  steps: [
    {
      id: "nav", route: "/emergency/dashboard", target: "nav-requests",
      title: "Open Emergency management",
      body: "All open requests arrive here.",
      advanceOn: { type: "route", value: "^/emergency/requests" },
    },
    {
      id: "queue", target: "er-queue",
      title: "The queue is sorted by urgency",
      body: "Higher priority and longer-waiting requests sit at the top; closed ones drop to the bottom.",
      advanceOn: { type: "manual" },
    },
    {
      id: "top", target: "er-case-top",
      title: "Open the top case",
      body: "Open the request at the top of the queue.",
      advanceOn: { type: "click" },
    },
    {
      id: "priority", target: "er-priority",
      title: "Set a priority",
      body: "Choose a priority (1 is the highest) and give a short reason, then press Next.",
      behindTheScenes: "Priority is a staff decision recorded with its reason. The app never guesses urgency for you.",
      advanceOn: { type: "manual" },
    },
    {
      id: "priority-review", target: "er-priority-review",
      title: "Review the priority",
      body: "Check the priority before saving it.",
      advanceOn: { type: "visible", value: "er-priority-confirm" },
    },
    {
      id: "priority-confirm", target: "er-priority-confirm", mutates: true,
      title: "Save the priority",
      body: "Confirm to set the priority.",
      advanceOn: { type: "event", value: "Set priority" },
    },
    {
      id: "claim-review", target: "er-claim-review",
      title: "Claim the request",
      body: "Claiming tells the team you are handling this case.",
      advanceOn: { type: "visible", value: "er-claim-confirm" },
    },
    {
      id: "claim-confirm", target: "er-claim-confirm", mutates: true,
      title: "Confirm the claim",
      body: "Confirm to take the case.",
      behindTheScenes: "A claim is a 15-minute lease stored with the request, so two staff members can't process the same case at once.",
      advanceOn: { type: "event", value: "Claim request" },
    },
    {
      id: "process", target: "er-processing",
      title: "Start processing",
      body: "Give a reason and review starting work on the case, then press Next.",
      advanceOn: { type: "manual" },
    },
    {
      id: "process-review", target: "er-processing-review",
      title: "Review the start",
      body: "Review the change of state.",
      advanceOn: { type: "visible", value: "er-processing-confirm" },
    },
    {
      id: "process-confirm", target: "er-processing-confirm", mutates: true,
      title: "Start processing",
      body: "Confirm to mark the request as being processed.",
      advanceOn: { type: "event", value: "Start processing" },
    },
  ],
};
