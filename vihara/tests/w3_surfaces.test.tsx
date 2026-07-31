import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * R-4 part W · W3 — the Boardroom, the Brainstorm, the Glasshouse, the Library.
 *
 * `lifecycle.test.tsx` holds the four **empty** cases. This file holds the
 * populated ones, and every payload below is a **real response shape captured
 * from the shipping backend on 2026-07-31** — including the twin run that
 * proved `POST /ai/twin/scenarios/{id}/run` answers end to end, which is what
 * let the Boardroom's "Take to the Glasshouse" stop being drawn-and-disabled.
 *
 * What it is actually guarding is DESIGN_CONTRACT §7, which is correctness and
 * not style, and which no type can express:
 *
 *  - a KPI with `measurable: false` names what is missing and prints no figure;
 *  - a movement is shown and never judged — "Behind" and "Ahead" cannot appear,
 *    because the registry declares no direction for any KPI;
 *  - a `currency` KPI carries **no symbol**, so "₹" may not appear anywhere;
 *  - the Glasshouse never invents a baseline, and its permitted loading state
 *    is words that appear only while a run is in flight;
 *  - the Library's influence panel binds `questions_answered` and nothing else;
 *  - and no surface ever renders `undefined` or `NaN`, which is what a missing
 *    binding looks like when §7.1 has been broken by accident rather than on
 *    purpose.
 */

vi.mock("../src/api/strategy", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchBusinessKpis: () =>
    Promise.resolve([
      {
        key: "open_pipeline_value",
        display_name: "Open pipeline value",
        unit: "currency",
        formula: "Sum of Opportunity.amount…",
        value: null,
        baseline_value: null,
        measurable: false,
        missing: ["Opportunity.amount", "Opportunity.stage"],
        caveat: "Counts stated deal sizes, not probability-weighted value.",
        window_days: 30,
        sample_size: 0,
      },
      {
        key: "dso",
        display_name: "Days sales outstanding",
        unit: "days",
        formula: "…",
        value: 38.5,
        baseline_value: 29.5,
        measurable: true,
        missing: [],
        caveat: null,
        window_days: 30,
        sample_size: 11,
      },
      {
        key: "win",
        display_name: "Quote acceptance rate",
        unit: "percent",
        formula: "…",
        value: 61,
        baseline_value: null,
        measurable: true,
        missing: [],
        caveat: null,
        window_days: 7,
        sample_size: 27,
      },
    ]),
}));

vi.mock("../src/api/tenant", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchRecords: (defName: string) =>
    Promise.resolve(
      defName === "Proposition"
        ? [
            {
              id: "11111111-1111-1111-1111-111111111111",
              entity_def_id: "d",
              data: {
                title: "Raise the chase cadence on overdue invoices to every four days",
                rationale: "Meera is idle two days in seven.",
                expected_effect: "Collected sooner on six of eleven invoices",
                cost_estimate: 240000,
                honesty_grade: "replay",
                twin_run_id: "TWR-2208",
                status: "tabled",
              },
              version: 1,
              def_version: 1,
              deleted_at: null,
              created_at: "2026-07-30T09:14:00",
              sor: null,
              synced: false,
            },
            {
              id: "22222222-2222-2222-2222-222222222222",
              entity_def_id: "d",
              data: { title: "Already adopted", status: "adopted", honesty_grade: "untested" },
              version: 2,
              def_version: 1,
              deleted_at: null,
              created_at: "2026-07-29T09:14:00",
              sor: null,
              synced: false,
            },
          ]
        : [
            {
              id: "33333333-3333-3333-3333-333333333333",
              entity_def_id: "m",
              data: {
                title: "Q3 review",
                held_on: "2026-07-30T09:02:00",
                decisions_summary: "Pricing parked for the Q4 board.",
              },
              version: 1,
              def_version: 1,
              deleted_at: null,
              created_at: "2026-07-30T09:02:00",
              sor: null,
              synced: false,
            },
          ],
    ),
}));

vi.mock("../src/api/twin", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchScenarios: () =>
    Promise.resolve([
      {
        id: "a3bafc67-f5a1-439a-a0f5-c282be2b7119",
        name: "Chase cadence at four days",
        kind: "custom",
        scope: { objects: ["Invoice"], window_days: 7 },
        status: "ready",
        acknowledged_estimate_usd: 0.01,
      },
    ]),
  fetchRuns: () =>
    Promise.resolve([
      {
        id: "dcba1526-d824-4a10-bcf2-d25ea573c6cc",
        grade: "replay",
        grade_means: "Replayed real events that actually happened.",
        method: "replayed 1 signal(s) through the shipped loop",
        metrics: {
          truncated: false,
          by_category: {},
          estimate_usd: 0.01,
          runs_executed: 0,
          simulated_calls: 0,
          external_effects: 0,
          signals_replayed: 1,
        },
        cost_usd: 0,
        is_baseline: false,
        refusal_reason: null,
        started_at: "2026-07-31T04:21:40.664045",
        finished_at: "2026-07-31T04:21:40.854264",
      },
    ]),
}));

vi.mock("../src/api/library", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchDocuments: () =>
    Promise.resolve([
      {
        id: "44444444-4444-4444-4444-444444444444",
        filename: "Pricing 2026.pdf",
        file_type: "pdf",
        upload_status: "completed",
        created_at: "2026-03-12T10:00:00",
        source_kind: "upload",
        source_uri: null,
        effective_from: "2026-04-01",
        staleness_state: "superseded",
        staleness_reason: "a newer document supersedes this one",
        superseded_by_id: "55555555-5555-5555-5555-555555555555",
        memory_domain: null,
      },
      {
        id: "55555555-5555-5555-5555-555555555555",
        filename: "Pricing 2026-Q3.pdf",
        file_type: "pdf",
        upload_status: "processing",
        created_at: "2026-07-02T10:00:00",
        source_kind: "upload",
        source_uri: null,
        effective_from: null,
        staleness_state: "fresh",
        staleness_reason: null,
        superseded_by_id: null,
        memory_domain: null,
      },
    ]),
  fetchInfluence: () =>
    Promise.resolve({
      document_id: "44444444-4444-4444-4444-444444444444",
      window_days: 30,
      retrievals: 214,
      questions_answered: 40,
      peak_distinct_colleagues: 3,
      active_days: 12,
    }),
  fetchPassage: () =>
    Promise.resolve({
      document: { id: "44444444-4444-4444-4444-444444444444" },
      requested_chunk_index: 0,
      context: 1,
      passages: [
        {
          chunk_id: "c0",
          chunk_index: "0",
          heading_path: "Front matter",
          content: "This price list is effective from 1 April 2026.",
          is_cited: true,
        },
        {
          chunk_id: "c1",
          chunk_index: "1",
          heading_path: "Price list › Cotton — grey",
          content: "Grey cotton is quoted per kilogram, ex-works.",
          is_cited: false,
        },
      ],
    }),
}));

vi.mock("../src/api/pragya", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  sendTurn: () =>
    Promise.resolve({
      reply: "A marketing plan — here is what I already hold.",
      stage: 4,
      stage_name: "planning",
      auth_level: "owner",
      tier: null,
      raised_approval: true,
      needs_step_up: false,
      needs_oob: false,
      command_ref: null,
      command_summary: "draft a campaign brief",
      cost_usd: 0.0123,
      awaiting_confirmation: false,
      advanced_to: null,
      artifacts_written: ["campaign-brief.md"],
      reported_delegations: [],
    }),
}));

import { BoardroomSurface } from "../src/surfaces/BoardroomSurface";
import { GlasshouseSurface } from "../src/surfaces/GlasshouseSurface";
import { LibrarySurface } from "../src/surfaces/LibrarySurface";

afterEach(cleanup);

describe("W3 — the four surfaces on real wire shapes", () => {
  it("the Boardroom binds the agenda, propositions and minutes", async () => {
    const { container } = render(<BoardroomSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.textContent).toContain("Raise the chase cadence"),
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Days sales outstanding");
    expect(text).toContain("38.5d");
    expect(text).toContain("was 29.5d");
    expect(text).toContain("+9d");
    expect(text).toContain("Not measurable");
    expect(text).toContain("Opportunity.amount");
    expect(text).toContain("No comparison yet");
    expect(text).toContain("Q3 review");
    expect(text).toContain("Take to the Glasshouse");
    /* Never a judgement, never an invented direction. */
    expect(text).not.toContain("Behind");
    expect(text).not.toContain("Ahead");
    /* A currency figure carries no symbol. */
    expect(text).not.toContain("₹");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("NaN");
  });

  it("the Brainstorm takes a real turn and reports what it did", async () => {
    const { container } = render(<BoardroomSurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.querySelector(".bs-input")).not.toBeNull());
    const input = container.querySelector(".bs-input")!;
    fireEvent.change(input, { target: { value: "A marketing plan" } });
    fireEvent.submit(container.querySelector(".bs-form")!);

    await waitFor(() =>
      expect(container.textContent).toContain("here is what I already hold"),
    );
    const text = container.textContent ?? "";
    expect(text).toContain("4 · planning");
    expect(text).toContain("USD 0.0123");
    expect(text).toContain("draft a campaign brief");
    expect(text).toContain("campaign-brief.md");
    expect(text).toContain("That turn raised a card");
    expect(text).toContain("File it as a proposition");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("NaN");
  });

  it("the Glasshouse shows the run, the grade sentence, and no invented baseline", async () => {
    const { container } = render(<GlasshouseSurface onEcho={vi.fn()} />);
    await waitFor(() =>
      expect(container.textContent).toContain("replayed 1 signal(s)"),
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Chase cadence at four days");
    expect(text).toContain("Replayed real events that actually happened.");
    expect(text).toContain("no baseline replay");
    expect(text).toContain("no reading to compare");
    expect(text).toContain("priced at USD 0.01");
    expect(text).toContain("real signals replayed");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("NaN");
    /* The exemption is spent on words, and only when a run is in flight. */
    expect(text).not.toContain("running the twin");
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
  });

  it("the Library binds the shelf, a passage and a measured influence", async () => {
    const { container } = render(<LibrarySurface onEcho={vi.fn()} />);
    await waitFor(() => expect(container.textContent).toContain("Answered 40"));
    await waitFor(() => expect(container.textContent).toContain("Grey cotton"));
    const text = container.textContent ?? "";
    expect(text).toContain("Pricing 2026.pdf");
    expect(text).toContain("superseded");
    expect(text).toContain("a newer document supersedes this one");
    expect(text).toContain("Pricing 2026-Q3.pdf");
    expect(text).toContain("Answered 40 questions");
    expect(text).toContain("used on 12 of the last 30 days");
    expect(text).toContain("this needs you");
    expect(text).toContain("1 still being read");
    expect(text).toContain("Grey cotton is quoted per kilogram");
    expect(text).toContain("Cotton — grey");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("NaN");
  });
});
