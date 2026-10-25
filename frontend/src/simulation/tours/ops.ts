import type { Tour } from "../types";

export const opsTour: Tour = {
  id: "ops",
  role: "ops",
  workspace: "/ops",
  roleLabel: "Operations",
  title: "Watch the system",
  goal: "Read the headline figures, inspect a degraded service and follow a trace.",
  summary: "You've seen how operations staff read system health, inspect a degraded service, read alerts and follow a request through its trace.",
  steps: [
    {
      id: "headline", route: "/ops/dashboard", target: "ops-headline",
      title: "Headline figures",
      body: "Ready services and firing alerts at a glance.",
      behindTheScenes: "These numbers come from Prometheus, which scrapes every service replica every few seconds.",
      advanceOn: { type: "manual" },
    },
    {
      id: "degraded", target: "ops-degraded-service",
      title: "Inspect a degraded service",
      body: "Open the degraded service to see its replicas.",
      advanceOn: { type: "click" },
    },
    {
      id: "alerts", target: "ops-alerts",
      title: "Read the alerts",
      body: "Alerts name the rule that fired and the service it concerns.",
      advanceOn: { type: "manual" },
    },
    {
      id: "traces-nav", target: "nav-traces",
      title: "Open the Trace Explorer",
      body: "Follow one request between services.",
      advanceOn: { type: "route", value: "^/ops/traces" },
    },
    {
      id: "trace", target: "ops-trace-option",
      title: "Open a trace",
      body: "Open a recent trace to see its timing.",
      advanceOn: { type: "visible", value: "ops-trace-spans" },
    },
    {
      id: "spans", target: "ops-trace-spans",
      title: "Each hop between services",
      body: "Every span is one service's part of the request, with how long it took.",
      behindTheScenes: "OpenTelemetry passes a trace ID in every HTTP call and event, so spans from different services join into one timeline in Tempo.",
      advanceOn: { type: "manual" },
    },
  ],
};
