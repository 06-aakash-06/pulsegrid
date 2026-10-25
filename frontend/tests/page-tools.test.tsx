import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageToolsProvider, PageRefresh, AdvancedLookup, ItemDetails, MoreActions } from "../src/components/PageTools";
import { PageHeader } from "../src/components/PageHeader";

describe("task-focused page tools",()=>{
 it("has one header refresh, runs existing read handlers, and leaves drafts and commands alone",()=>{
  const first=vi.fn(),second=vi.fn(),command=vi.fn();
  render(<PageToolsProvider><PageHeader title="Appointments" subtitle="Plan your visit" department="appointments"/><input aria-label="Draft note" defaultValue=""/><PageRefresh onClick={first}>Refresh list</PageRefresh><PageRefresh onClick={second} disabled>Refresh unavailable detail</PageRefresh><MoreActions><button onClick={command}>Update insurance data</button></MoreActions></PageToolsProvider>);
  fireEvent.change(screen.getByLabelText("Draft note"),{target:{value:"Keep my draft"}});
  expect(screen.getAllByRole("button",{name:"Refresh"})).toHaveLength(1);
  fireEvent.click(screen.getByRole("button",{name:"Refresh"}));
  expect(first).toHaveBeenCalledTimes(1);expect(second).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Draft note")).toHaveValue("Keep my draft");
 });
 it("collects manual lookups under one disclosure and retains entered values across collapse",()=>{
  render(<PageToolsProvider><AdvancedLookup title="Patient"><input aria-label="Patient reference"/></AdvancedLookup><AdvancedLookup title="Invoice"><input aria-label="Invoice reference"/></AdvancedLookup></PageToolsProvider>);
  const summary=screen.getByText("Advanced lookup",{selector:"summary"});
  expect(screen.getAllByText("Advanced lookup",{selector:"summary"})).toHaveLength(1);
  expect(screen.getByLabelText("Patient reference")).not.toBeVisible();fireEvent.click(summary);
  fireEvent.change(screen.getByLabelText("Patient reference"),{target:{value:"2001"}});
  fireEvent.click(summary);fireEvent.click(summary);expect(screen.getByLabelText("Patient reference")).toHaveValue("2001");
 });
 it("uses one Details disclosure when technical sections are nested",()=>{
  render(<ItemDetails>Reference 2001<ItemDetails>Version 3</ItemDetails></ItemDetails>);
  expect(screen.getAllByText("Details",{selector:"summary"})).toHaveLength(1);
  expect(screen.getByText(/Reference/)).not.toBeVisible();fireEvent.click(screen.getByText("Details"));expect(screen.getByText(/Reference/)).toBeVisible();
 });
});
