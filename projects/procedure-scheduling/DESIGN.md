# Procedure Scheduling — Prototype Design

**Status:** Draft for build
**Author:** Doug Ollerenshaw (with Claude)
**Date:** 2026-08-03
**Related:** [aind-scientific-computing#624](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/624), [#595](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/595), Bruno's requirements comment ([#624 comment](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/624#issuecomment-4549655380)), Bruno's proposal doc ([Aind.Behavior.VrForaging/docs/dataverse-lims-acquisition-scheduling-proposal.md](https://github.com/AllenNeuralDynamics/Aind.Behavior.VrForaging/blob/main/docs/dataverse-lims-acquisition-scheduling-proposal.md)), the live rig↔Dataverse client in [clabe](https://github.com/AllenNeuralDynamics/clabe/blob/main/src/clabe/pickers/dataverse.py), and the session-naming-convention discussion in [#881](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/881)

## Purpose

Issue #624 asks for a Dataverse table (and PowerPlatform automations) to track acquisition sessions that are scheduled/requested but not yet started. The Dataverse implementation is the long-term home for this, but that team is slow and its priorities are opaque. This document specifies a **lightweight, functional prototype** we can stand up in ~1–2 days so that:

1. Stakeholders can see the feature working instead of debating it hypothetically.
2. The Dataverse/PowerPlatform team has a concrete reference implementation and schema to react to and adopt.
3. Any data we enter into the prototype can be **backfilled into Dataverse later** with a straightforward field-by-field mapping.

This prototype is explicitly a **conversation-starter and stopgap**, not the production system. The schema is designed to mirror Bruno's proposed Dataverse tables so the migration path is a direct mapping.

## Scope

**In scope (this build):**

- Phase 1: `scheduled_procedures`, `instruments`, and a shared `procedure_types` vocabulary, plus minimal lookup tables (`mice`, `projects`, `users`).
- A read-only, filterable REST API over that data, reachable internally at `http://{vm_ip}/session_schedule/api/...`.
- A simple web form to add/edit scheduled procedures (so there's data to demo). The public data API stays read-only; writes go through a separate admin path.
- Phase 2: a calendar-style single-page view of the schedule (FullCalendar), reachable at `http://{vm_ip}/session_schedule/`, filterable by platform, date, and instrument.
- A Parquet export of every table for portability and Dataverse backfill.
- Seed data so the app is populated on first run.

**Out of scope (deferred, matching Bruno's doc):**

- Automatic generation of Acquisition-log records when a scheduled procedure is marked complete.
- Cancellation/reschedule-reason capture and "did it happen as planned" reconciliation.
- Auth / user management (single internal endpoint, no auth).
- **SmartSPIM-specific request / surgery / histology sub-workflows.** Deliberately out of scope, and not just to limit effort. Per the Dataverse team (David Feng, Aug 2026), active Dataverse development is *already* focused on SmartSPIM imaging and histology, plus surgical procedure request forms; behavior/physiology acquisition scheduling is the piece still sitting "in the queue." So this prototype targets the behavior/physiology scheduling gap and stays out of SmartSPIM's lane to avoid duplicating or pre-empting work the Dataverse team is mid-flight on. The schema stays general (the `procedure_types` vocab still includes histology/imaging, and a SmartSPIM instrument appears in the seed data) purely to show the model generalizes — not as an attempt to own SmartSPIM pre-acquisition workflows.
- PowerPlatform notification automations (these are Dataverse-native; the prototype instead exposes a `status` field the real system can hang notifications off).

## Current infrastructure (what exists today)

Understanding this is the difference between a prototype that fits and one that has to be thrown away. Verified by reading the live code (`clabe`) and Bruno's proposal doc.

**"Dataverse" means Microsoft Dataverse**, the Power Platform / Dynamics 365 data backend — *not* the academic (Harvard) Dataverse. That's why this work sits with the central-IT PowerPlatform team. The backend is reached as an OData v4 REST API at `https://{org}.crm.dynamics.com/api/data/v9.2/`, authenticated through Azure AD (MSAL) with a service account (`svc_sipe`) whose credentials come from KeePass. Every table carries standard Dataverse audit columns (`createdon`, `modifiedon`) and GUID primary keys, and the environment is modeled as a star schema (`aibs_` prefix, `dim_`/`fact_` tables).

The tables Bruno's "Currently" paragraph refers to:

- **`aibs_dim_mices`** — the Mouse dimension (lookup). `aibs_mouse_id` is the human mouse id (alternate key); `aibs_dim_miceid` is the GUID primary key.
- **`aibs_fact_mouse_proposed_behavior_sessionses`** — this *is* the "Proposed Behavior Sessions" table. One fact row per proposed/next session, with `aibs_task_name`, a mouse lookup (`aibs_mouse_id@odata.bind` on write, `_aibs_mouse_id_value` on read), `aibs_stage_name`, and `aibs_trainer_state` (a JSON blob holding the full curriculum `TrainerState`).
- **"Behavior Training"** table — tracks the scientific contact responsible for each mouse. Managed by the behavior-training team through a Power Apps UI; **its logical name is not in the rig code**, so we'll need the PowerPlatform team to share its schema (see open questions).

**How the rig uses it today** (all via `clabe`'s `DataversePicker`, per session, on the instrument):

1. Read the next settings — look up the mouse GUID, then query `aibs_fact_mouse_proposed_behavior_sessionses` filtered by task + mouse, `order by createdon desc, top 1`, and deserialize `aibs_trainer_state` into the task. This is the "pull settings for the next planned session" Bruno describes.
2. Run the Bonsai task.
3. Write back — after curriculum evaluation, POST a *new* row with the updated trainer state.

So this table is effectively **append-only**, and "next planned session" means "most recently created row" — there is **no calendar date** on these rows. That missing when-and-where is precisely the gap this scheduling work fills. Two consequences shape the design below:

- **The scheduler layers on top; it does not replace the curriculum table.** Our new record schedules *that a session should occur* (mouse, rig, when, protocols, who). The *what-settings-to-run* keeps coming from the proposed-behavior-sessions / curriculum table. Bruno's proposal states this boundary explicitly: "the scheduler is not the authority for runtime execution parameters." This is the same platform-specific-config-table pattern used throughout this doc — now confirmed by real usage.
- **The rig-facing surface is read-only, and humans own writes.** Rigs never edit the schedule; they query and validate at ingestion. That matches the read-only-API + human-facing-form split already chosen here.

## Guardrails: the prototype never touches production Dataverse

This is a hard boundary, not a preference. The prototype is a **self-contained, local system** backed only by its own DuckDB file and synthetic seed data. It must never read from, write to, or otherwise contact the real Microsoft Dataverse environment or any other production/live system.

Specifically, the prototype and any code built for it must NOT:

- Connect to `*.crm.dynamics.com`, the Dataverse OData API, or any Azure AD / MSAL auth flow.
- Import, call, or depend on `clabe`, `dataverse-client`, or the `DataversePicker`, or use the `svc_sipe` service account or any KeePass credentials.
- Read, write, update (PATCH/POST/PUT), or delete any row in `aibs_dim_mices`, `aibs_fact_mouse_proposed_behavior_sessionses`, the "Behavior Training" table, or any other existing Dataverse/LIMS table.
- Reach out to any external network service for data. All data is local and synthetic.

The Microsoft Dataverse details in this doc are **reference only** — they exist so the prototype's schema and API are *shaped* to map onto Dataverse later, and so a human can do a backfill when the time comes. They are not an instruction to integrate. The direction of data flow is strictly one-way and deferred: *someday, a human exports our Parquet and imports it into Dataverse.* Nothing flows the other way, and nothing happens automatically. Any real integration is out of scope and left entirely to the PowerPlatform team.

If example data resembling real mice/rigs is useful, generate it synthetically in the seed script — do not source it from any production system.

## Design decisions (chosen)

- **Backing store:** DuckDB file as source of truth, with a script to export each table to Parquet for portability/backfill.
- **Data entry:** Read-only public data API (GET only) + a simple admin web form that writes via a separate admin route.
- **Calendar UI:** Static single-page app using FullCalendar (loaded from CDN), calling the read-only API.
- **Deployment:** One `uvicorn` process serving both the API and the SPA, no auth, open on the internal network.

## Terminology note (needs reconciliation with Bruno)

Bruno's doc uses both "Procedure Types" (a vocab) and "Acquisition Platforms" (the thing multiselected on instruments and scheduled records). The eight listed items are effectively the acquisition platforms/modalities. **This prototype treats them as one shared vocabulary, named `procedure_types`.** An instrument declares which types it is *compatible* with; a scheduled procedure declares which types are *active* for that session (multiselect, because e.g. Dynamic Foraging + FIP can run together). If Bruno intended two distinct vocabularies, this is a one-line change; calling it out so we can confirm.

## Data model

DuckDB tables. IDs are string UUIDs (maps cleanly onto Dataverse GUID primary keys). The `scheduled_procedures` token id specifically uses **UUIDv7** (time-sortable — see "Persistent acquisition ID"); other keys can be any UUID version. Datetimes are ISO-8601 UTC.

### `procedure_types` (vocabulary)

| field | type | notes |
|---|---|---|
| id | uuid (PK) | |
| name | string | unique (the AIND-internal task/platform label, e.g. "Dynamic foraging behavior") |
| modality_name | string | the aind-data-schema modality this maps to, e.g. "Behavior" (see "aind-data-schema alignment") |
| modality_abbreviation | string | the modality abbreviation, e.g. "behavior", "fib", "ecephys" |
| sort_order | int | for stable display/color assignment |

Seed values (from Bruno's doc):

- Acute extracellular electrophysiology (modular insertion)
- Whole-brain 3D histology
- Cellular imaging
- Fiber photometry (FIP)
- Fiber photometry (HSFP)
- Patch foraging behavior
- Dynamic foraging behavior
- Whole-brain axonal imaging

### `instruments`

| field | type | notes |
|---|---|---|
| id | uuid (PK) | |
| name | string | unique display name, e.g. "SmartSPIM-1", "VR-Foraging-Rig-A" |
| instrument_id | string | the aind-data-schema `instrument_id` value (e.g. "EPHYS1"), i.e. the identity used in acquisition/instrument metadata. Lets a scheduled procedure reference the same instrument identity that lands in the data. |
| sipe_rig_name | string | the SIPE environment-variable rig/computer name the rig identifies itself by; this is the "rig_id" the rig-facing API filters on (see API). Optional but recommended for exact mapping. |
| location | string | optional (room/rig) |
| active | bool | soft-hide retired instruments |

### `instrument_compatible_types` (join: instrument ↔ procedure_type)

| field | type | notes |
|---|---|---|
| instrument_id | uuid (FK) | |
| procedure_type_id | uuid (FK) | |

Represents "Compatible Acquisition Platforms" per instrument.

### `mice` (lookup)

| field | type | notes |
|---|---|---|
| id | uuid (PK) | |
| subject_id | string | AIND subject id (aind-data-schema aligned), unique |
| genotype | string | optional |

### `projects` (lookup)

| field | type | notes |
|---|---|---|
| id | uuid (PK) | |
| name | string | unique |

### `users` (lookup)

| field | type | notes |
|---|---|---|
| id | uuid (PK) | |
| name | string | plain name; feeds acquisition `experimenters` (a list of name strings in aind-data-schema) |
| email | string | unique |
| orcid | string, nullable | optional ORCID; lets a user map to an aind-data-schema `Person` object (used by data_description `investigators`) |

### `scheduled_procedures` (main table)

| field | type | notes |
|---|---|---|
| id | uuidv7 (PK) | **the persistent acquisition token** (see below): a time-sortable UUIDv7, minted at scheduling, immutable, the through-line identifier carried into acquisition/transfer/processing |
| mouse_id | uuid (FK → mice) | |
| instrument_id | uuid (FK → instruments) | |
| project_id | uuid (FK → projects) | |
| contact_user_id | uuid (FK → users) | scientific contact |
| scheduled_start | datetime | |
| scheduled_end | datetime | must be > start |
| acquisition_type | string (computed) | concatenation of active procedure type names, sorted; recomputed on write |
| acquisition_name | string, nullable | *secondary* human-readable, dated session name (the conventional AIND acquisition name), filled once acquisition begins. A convenience cross-reference for humans, NOT the linking key — the `id` token is. Null for purely-scheduled rows. |
| status | enum | `scheduled` (default), `completed`, `cancelled`, `rescheduled` — light-touch; the real system hangs notifications off status changes |
| ethics_review_id | string, nullable | IACUC / ethics protocol number; maps to aind-data-schema acquisition `ethics_review_id`. Called out in Bruno's requirements. |
| notes | text, nullable | free-form notes / metadata |
| planned_config | JSON, nullable | platform-specific planned settings (the "Proposed Behavior Sessions" association pattern, generalized). Free-form for the prototype. |
| protocols | text, nullable | which protocol(s) should run, human-readable |
| created_at | datetime | |
| updated_at | datetime | |

### `scheduled_procedure_active_types` (join: scheduled_procedure ↔ procedure_type)

| field | type | notes |
|---|---|---|
| scheduled_procedure_id | uuid (FK) | |
| procedure_type_id | uuid (FK) | |

Represents "Active Acquisition Platforms" for the session.

### `scheduled_procedure_experimenters` (join: scheduled_procedure ↔ user)

| field | type | notes |
|---|---|---|
| scheduled_procedure_id | uuid (FK) | |
| user_id | uuid (FK → users) | |

Covers the requirement to assign experimenter(s) in addition to a scientific contact.

### Validation rules

1. `scheduled_end` must be strictly after `scheduled_start`.
2. Every active procedure type on a scheduled procedure **must be in the instrument's compatible set**. Reject writes that violate this (this is Bruno's option (b): validate compatibility). Surface a clear error in the form.
3. `acquisition_type` is always recomputed server-side from active types; never client-supplied.

### Persistent acquisition ID (the through-line token)

This is the capability people keep asking for: schedule an acquisition, get an ID, and use that same ID from then on — so when the session is actually performed, the identifier already exists.

`scheduled_procedures.id` (a **UUIDv7**) **is** that ID. It is minted the instant a procedure is scheduled — so it exists *before* acquisition — and it is the single, immutable identifier intended to tie the plan to the raw acquisition and every downstream transfer and processing step.

- Minted at scheduling, immutable thereafter.
- **UUIDv7**, so it is time-sortable: rows sort by creation time by the ID alone, while remaining a standard 128-bit UUID that maps cleanly onto a Dataverse GUID. (This satisfies the "sortable identifier" desideratum raised in #881 without introducing a second ID or a separate ULID type.)
- Returned on every read, including the rig-facing endpoints, so the acquisition software can fetch the token for the planned session and stamp it into the acquisition's metadata. From that moment the same ID links the raw data and all derived assets back to the plan.
- Deliberately independent of date/time — which is exactly why it can pre-exist. AIND session/acquisition names embed the actual date+time and can only be generated at run time; a UUID minted at scheduling has no such constraint.

`acquisition_name` is *secondary*: the conventional human-readable, dated AIND session name, filled once acquisition begins. It's a convenience handle for humans (useful precisely because the token is a UUID), not the linking key.

**Prototype scope / honesty about the boundary.** The prototype mints the token and exposes it through the API. Actually stamping it into rig-generated acquisition metadata lives in the rig/acquisition software, which the prototype doesn't control — so that final hop is part of the real integration, not something this read-only prototype enforces. Bruno's proposal anticipates exactly this as the "acquisition token" enhancement (rig receives a token from the schedule and presents it at transfer for validation/reconciliation). The prototype makes the token real and available; wiring the rig to adopt it is a follow-up for whoever owns the acquisition path.

### Relationship to issue #881 (session naming convention)

[#881](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/881) reconsiders the `<subject>_<datetime>` session-naming convention. The token here is, in effect, the identifier that issue asks for — Bruno's own "suggested path forward #1" is "a ULID or UUID generated at session registration time." How the token bears on each of #881's concerns:

- **Concern 4 — circular dependency with pre-registration/scheduling: solved.** Pre-registration needs an ID assignable before acquisition; the datetime-derived name can't exist until the session runs. A UUIDv7 minted at scheduling breaks the cycle directly. This is the core link.
- **Concern 2 — uniqueness not guaranteed (two sessions, same subject, same second): solved,** once the UUID is the primary identifier rather than the dated name.
- **Concern 3 — the name encodes metadata; need a metadata-backed index: enabled, not fully solved.** The token gives a stable key to query on instead of parsing folder names, and the scheduling DB is itself a UUID→metadata index for planned sessions. The broader "metadata is the source of truth" index over all assets (DocDB) is larger than this prototype, but the token is a necessary ingredient.
- **Concern 1 — ISO 8601 datetime/filename format: de-risked, not settled.** Once identity lives in the UUID, the dated name becomes a non-load-bearing display label that tools shouldn't parse, which lowers the stakes of the format debate — but the filename-format standard itself is a separate question the token doesn't resolve.

**Linchpin dependency (outside this prototype):** for the token to actually travel with the data and land in DocDB, `aind-data-schema` needs a field to carry it — most naturally on the **Identifiers** component (aind-data-schema already has a place for external/registered IDs), or failing that a dedicated `acquisition_id` on the acquisition model. The full loop is: schedule mints the UUIDv7 → rig stamps it into acquisition metadata (Identifiers) → metadata ingested into DocDB → query by UUID thereafter. That schema field is the one piece this prototype can't provide and should be filed as its own issue linking #624 and #881.

## aind-data-schema alignment

The prototype's fields are chosen so a scheduled procedure maps cleanly onto aind-data-schema (v2) metadata — the same models the acquisition will emit and DocDB will index. This makes the schedule → acquisition-metadata handoff a direct field mapping, and it's what lets the persistent token (and everything attached to it) flow into the standard metadata later. Verified against the live metadata service (schema versions ~2.x).

**Field mapping**

| Prototype | aind-data-schema (v2) |
|---|---|
| `mice.subject_id` | `subject_id` (data_description, acquisition, subject) |
| `projects.name` | data_description `project_name` (controlled vocabulary — validate against the AIND project-name list) |
| `instruments.instrument_id` | instrument `instrument_id` / acquisition `instrument_id` |
| `users.name` | acquisition `experimenters` (list of name strings) |
| `users` + `orcid` | data_description `investigators` (list of `Person` objects with ORCID) |
| `scheduled_start` / `scheduled_end` | planned analogues of acquisition `acquisition_start_time` / `acquisition_end_time` (tz-aware ISO-8601) |
| `acquisition_type` (computed) | acquisition `acquisition_type` (a free descriptive string — our concatenation is compatible) |
| `ethics_review_id` | acquisition `ethics_review_id` (IACUC number) |
| active `procedure_types` → their `modality_*` | data_description `modalities` / data-stream `modalities` (list of `{name, abbreviation}`) |
| `acquisition_name` | data_description `name` (the `<subject>_<datetime>` asset name) |
| `id` (UUIDv7 token) | **no home yet** — needs a new aind-data-schema field, likely on the Identifiers component (the linchpin issue for #624/#881) |

**Procedure type → modality controlled vocabulary.** This is the important mapping: aind-data-schema modalities are a controlled vocab, and several prototype procedure types collapse onto one modality. Each `procedure_types` row carries the mapping so the schedule can emit the correct `modalities` list.

| procedure_type (`name`) | modality `name` | modality `abbreviation` |
|---|---|---|
| Patch foraging behavior | Behavior | behavior |
| Dynamic foraging behavior | Behavior | behavior |
| Fiber photometry (FIP) | Fiber photometry | fib |
| Fiber photometry (HSFP) | Fiber photometry | fib |
| Acute extracellular electrophysiology (modular insertion) | Extracellular electrophysiology | ecephys |
| Whole-brain 3D histology | Selective plane illumination microscopy | SPIM |
| Cellular imaging | Planar optical physiology | pophys |
| Whole-brain axonal imaging | Selective plane illumination microscopy | SPIM |

Notes: a multi-platform session (e.g. Dynamic foraging + FIP) therefore emits **two** modalities (`Behavior`, `Fiber photometry`) — exactly what the multiselect produces. The imaging/histology mappings (SPIM/pophys) are best-effort and belong to the SmartSPIM lane that's out of scope here (see Scope); confirm them with the Dataverse/imaging team rather than treating them as settled. Project names and modalities should both be validated against the live controlled vocabularies (the metadata service exposes them).

## API

FastAPI, mounted so everything lives under `/session_schedule`. All read endpoints are **GET only**. Responses resolve lookups (return names alongside IDs) so the frontend needs no join logic.

### Read (public, read-only)

- `GET /session_schedule/api/scheduled-procedures` — list. **Filters (all optional, combinable):** `mouse_id` / `subject_id`, `instrument_id`, `project_id`, `contact_user_id`, `procedure_type_id` (matches any active type), `status`, `start_after`, `start_before`, `end_after`, `end_before`. Returns resolved records (mouse subject_id, instrument name, project name, contact name, active type names, experimenter names, acquisition_type).
- `GET /session_schedule/api/scheduled-procedures/{id}` — single record, fully resolved.
- `GET /session_schedule/api/instruments` — filters: `active`, `procedure_type_id` (compatible with).
- `GET /session_schedule/api/procedure-types`
- `GET /session_schedule/api/mice` — filter: `subject_id`.
- `GET /session_schedule/api/projects`
- `GET /session_schedule/api/users`

The requirement "expose a read-only API with filters for all fields" is satisfied by the filter set above.

### Rig-facing convenience endpoints (mirror the expected client)

Bruno's proposal specifies the Python client shape the rig-side code expects. Provide these as thin aliases over the read API so the prototype is drop-in shaped — "here's the endpoint the rig would call". In every response here, the `id` field is the persistent acquisition token (see "Persistent acquisition ID") — the value a rig would fetch for the planned session and carry into the acquisition and everything downstream:

- `GET /session_schedule/api/rig/{rig_id}/planned-acquisitions?start=...&end=...` — mirrors `get_planned_acquisitions(rig_id, start_date, end_date)`. `rig_id` matches `instruments.sipe_rig_name` (falling back to `name`).
- `GET /session_schedule/api/acquisitions/{id}` — mirrors `get_acquisition_record(acquisition_id)` (same payload as `scheduled-procedures/{id}`).
- `GET /session_schedule/api/animals/{animal_id}/next-acquisition` — mirrors `get_next_acquisition_for_animal(animal_id)`; returns the soonest future scheduled procedure for that mouse. Note the semantic upgrade over today's behavior: "next" here means *earliest upcoming scheduled_start*, not "most recently created row."

### Write (admin, for the form only)

Kept separate from the public read API so the "read-only API" contract is honored. No auth in the prototype, but namespaced so it's obvious what's write-side.

- `POST /session_schedule/api/admin/scheduled-procedures`
- `PUT /session_schedule/api/admin/scheduled-procedures/{id}`
- `DELETE /session_schedule/api/admin/scheduled-procedures/{id}`
- Minimal admin create endpoints for `instruments`, `mice`, `projects`, `users`, and instrument-compatibility so the demo can be populated through the UI as well as the seed script.

All writes enforce the validation rules above and recompute `acquisition_type` and `updated_at`.

## Seed data and worked examples

The prototype ships **pre-populated** with a small synthetic dataset so the calendar isn't empty and the GET endpoints return real results on first run. This section is the canonical seed dataset and a concrete end-to-end walkthrough. (`acquisition_type` is the active type names sorted alphabetically and joined with `" + "`. IDs are UUIDs in reality; short readable placeholders like `INST-VRA` are used here for legibility.)

### Seed dataset

**`procedure_types`** (all eight; `sort_order` 1–8 in the order listed under Data model).

**`instruments`**

| id | name | instrument_id | sipe_rig_name | compatible procedure types |
|---|---|---|---|---|
| INST-VRA | VR-Foraging-Rig-A | VRForaging1 | BEH-VR-01 | Patch foraging behavior; Dynamic foraging behavior; Fiber photometry (FIP) |
| INST-SPIM1 | SmartSPIM-1 | SmartSPIM1 | IMG-SPIM-01 | Whole-brain 3D histology; Cellular imaging; Whole-brain axonal imaging |
| INST-EPHYS2 | Ephys-Rig-2 | EPHYS2 | EPHYS-02 | Acute extracellular electrophysiology; Patch foraging behavior; Fiber photometry (FIP) |

**`mice`**: `testmouse1`, `testmouse2`, `testmouse3` (genotypes left as placeholder strings, e.g. `test-genotype`). Deliberately non-numeric so they can never be mistaken for or collide with real 6-digit AIND subject IDs — reinforcing the "synthetic data only" guardrail.
**`projects`**: `Cognitive flexibility in patch foraging` (PROJ-PF), `Brain-wide connectivity` (PROJ-BC).
**`users`**: Doug Ollerenshaw (doug.ollerenshaw@alleninstitute.org), Bruno Cruz, Jane Kim.

**`scheduled_procedures`** — four explicit rows below; the seed script fills out to ~15–25 total spread across the next 2–3 weeks (times UTC; "today" for seeding = the date the script runs).

| id | mouse | instrument | project | contact | experimenters | start → end | active types | acquisition_type | status |
|---|---|---|---|---|---|---|---|---|---|
| SP-1 | testmouse1 | VR-Foraging-Rig-A | PROJ-PF | Doug | Bruno | 08-04 09:00 → 11:00 | Dynamic foraging behavior, Fiber photometry (FIP) | Dynamic foraging behavior + Fiber photometry (FIP) | scheduled |
| SP-2 | testmouse2 | VR-Foraging-Rig-A | PROJ-PF | Doug | Jane | 08-05 13:00 → 14:30 | Patch foraging behavior | Patch foraging behavior | scheduled |
| SP-3 | testmouse3 | SmartSPIM-1 | PROJ-BC | Jane | Jane | 08-07 10:00 → 16:00 | Whole-brain 3D histology | Whole-brain 3D histology | scheduled |
| SP-4 | testmouse1 | Ephys-Rig-2 | PROJ-PF | Doug | Bruno | 08-11 09:00 → 12:00 | Acute extracellular electrophysiology, Fiber photometry (FIP) | Acute extracellular electrophysiology + Fiber photometry (FIP) | scheduled |

### Example 1 — creating a procedure via the form

A user wants to schedule a combined ephys + photometry session. In the calendar app they click **Add procedure** and fill in:

- Mouse: `testmouse2`
- Instrument: `Ephys-Rig-2` (the form now offers only that rig's compatible types)
- Project: `Cognitive flexibility in patch foraging`
- Scientific contact: `Doug Ollerenshaw`
- Experimenter(s): `Bruno Cruz`
- Active procedure types: ☑ Acute extracellular electrophysiology, ☑ Fiber photometry (FIP)
- Scheduled start / end: `2026-08-12 09:00` → `2026-08-12 11:00`
- Protocols: `Modular probe insertion, 4 shanks; FIP dual-fiber`
- Notes: `First ephys session for this mouse.`
- Planned config (optional JSON): `{"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]}`

Submitting sends this to the admin write API:

```
POST /session_schedule/api/admin/scheduled-procedures
{
  "mouse_id": "testmouse2",
  "instrument_id": "INST-EPHYS2",
  "project_id": "PROJ-PF",
  "contact_user_id": "USR-DOUG",
  "experimenter_user_ids": ["USR-BRUNO"],
  "scheduled_start": "2026-08-12T09:00:00Z",
  "scheduled_end": "2026-08-12T11:00:00Z",
  "active_procedure_type_ids": ["PT-EPHYS", "PT-FIP"],
  "protocols": "Modular probe insertion, 4 shanks; FIP dual-fiber",
  "notes": "First ephys session for this mouse.",
  "planned_config": {"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]}
}
```

The server validates (end > start ✓; both types are in Ephys-Rig-2's compatible set ✓), computes `acquisition_type`, and writes across three tables:

`scheduled_procedures` (one new row, `SP-5`):

```
id=SP-5, mouse_id=testmouse2, instrument_id=INST-EPHYS2, project_id=PROJ-PF,
contact_user_id=USR-DOUG, scheduled_start=2026-08-12T09:00:00Z,
scheduled_end=2026-08-12T11:00:00Z,
acquisition_type="Acute extracellular electrophysiology + Fiber photometry (FIP)",
acquisition_name=NULL, status="scheduled",
protocols="Modular probe insertion, 4 shanks; FIP dual-fiber",
notes="First ephys session for this mouse.",
planned_config={"probe_count":4,"fibers":["DMS-left","DMS-right"]},
created_at=2026-08-03T18:20:00Z, updated_at=2026-08-03T18:20:00Z
```

`scheduled_procedure_active_types` (two rows): `(SP-5, PT-EPHYS)`, `(SP-5, PT-FIP)`.
`scheduled_procedure_experimenters` (one row): `(SP-5, USR-BRUNO)`.

**Validation failure example.** If the user instead tried to add `Whole-brain 3D histology` (compatible only with SmartSPIM-1) on Ephys-Rig-2, the write is rejected:

```
HTTP 422
{"error": "incompatible_procedure_type",
 "detail": "'Whole-brain 3D histology' is not compatible with instrument 'Ephys-Rig-2'.
            Compatible types: Acute extracellular electrophysiology, Patch foraging behavior, Fiber photometry (FIP)."}
```

### Example 2 — what the GET endpoints return

**List, filtered to one rig from a date.** `GET /session_schedule/api/scheduled-procedures?instrument_id=INST-VRA&start_after=2026-08-01T00:00:00Z`

```
[
  {
    "id": "SP-1",
    "mouse": {"id": "testmouse1", "subject_id": "testmouse1"},
    "instrument": {"id": "INST-VRA", "name": "VR-Foraging-Rig-A", "sipe_rig_name": "BEH-VR-01"},
    "project": {"id": "PROJ-PF", "name": "Cognitive flexibility in patch foraging"},
    "contact": {"id": "USR-DOUG", "name": "Doug Ollerenshaw"},
    "experimenters": [{"id": "USR-BRUNO", "name": "Bruno Cruz"}],
    "active_procedure_types": ["Dynamic foraging behavior", "Fiber photometry (FIP)"],
    "acquisition_type": "Dynamic foraging behavior + Fiber photometry (FIP)",
    "acquisition_name": null,
    "scheduled_start": "2026-08-04T09:00:00Z",
    "scheduled_end": "2026-08-04T11:00:00Z",
    "status": "scheduled"
  },
  {
    "id": "SP-2",
    "mouse": {"id": "testmouse2", "subject_id": "testmouse2"},
    "instrument": {"id": "INST-VRA", "name": "VR-Foraging-Rig-A", "sipe_rig_name": "BEH-VR-01"},
    "project": {"id": "PROJ-PF", "name": "Cognitive flexibility in patch foraging"},
    "contact": {"id": "USR-DOUG", "name": "Doug Ollerenshaw"},
    "experimenters": [{"id": "USR-JANE", "name": "Jane Kim"}],
    "active_procedure_types": ["Patch foraging behavior"],
    "acquisition_type": "Patch foraging behavior",
    "acquisition_name": null,
    "scheduled_start": "2026-08-05T13:00:00Z",
    "scheduled_end": "2026-08-05T14:30:00Z",
    "status": "scheduled"
  }
]
```

**Single record (full detail).** `GET /session_schedule/api/scheduled-procedures/SP-5` returns the row created in Example 1, fully resolved, including `protocols`, `notes`, and `planned_config`.

**Rig-facing: what a rig would call.** `GET /session_schedule/api/rig/BEH-VR-01/planned-acquisitions?start=2026-08-04T00:00:00Z&end=2026-08-06T00:00:00Z`

```
[
  {"id": "SP-1", "subject_id": "testmouse1", "acquisition_type": "Dynamic foraging behavior + Fiber photometry (FIP)",
   "scheduled_start": "2026-08-04T09:00:00Z", "scheduled_end": "2026-08-04T11:00:00Z"},
  {"id": "SP-2", "subject_id": "testmouse2", "acquisition_type": "Patch foraging behavior",
   "scheduled_start": "2026-08-05T13:00:00Z", "scheduled_end": "2026-08-05T14:30:00Z"}
]
```

**Next acquisition for an animal.** `GET /session_schedule/api/animals/testmouse1/next-acquisition` (evaluated on 2026-08-03) returns the soonest upcoming row for mouse `testmouse1` — here `SP-1` on 08-04, ahead of `SP-4` on 08-11:

```
{"id": "SP-1", "subject_id": "testmouse1", "instrument": "VR-Foraging-Rig-A",
 "acquisition_type": "Dynamic foraging behavior + Fiber photometry (FIP)",
 "scheduled_start": "2026-08-04T09:00:00Z"}
```

## Frontend — calendar SPA (Phase 2)

Static `index.html` + JS served at `GET /session_schedule/`. Loads FullCalendar (and its resource-timeline plugin, under the FullCalendar GPLv3 license key since this repo is open source) from CDN. No build toolchain.

- **View:** resource-timeline with instruments as rows and scheduled procedures as events spanning `scheduled_start`→`scheduled_end`. If the resource-timeline plugin proves awkward, fall back to a `timeGrid`/`dayGrid` week view with events grouped/labeled by instrument.
- **Color:** events colored by primary active procedure type (stable mapping from `procedure_types.sort_order`). A legend maps color → platform.
- **Filters (client-side, calling the API):** by procedure type/platform, by instrument, by date range. Also a text filter on subject_id.
- **Event click:** side panel showing mouse subject_id, project, contact, experimenters, active platforms, acquisition_type, status, protocols, notes, and planned_config.
- **Add / edit:** an "Add procedure" button opens a modal form (mouse, instrument, project, contact, experimenters, start, end, active types, status, protocols, notes, planned_config). Active-type checkboxes are constrained/validated against the selected instrument's compatible set. Submits to the admin API.

## Deployment (on the VM)

Single process, no auth, internal network only.

- Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`. App is reachable at `http://{vm_ip}:8000/session_schedule/`.
- To serve on bare port 80 (`http://{vm_ip}/session_schedule`), either run uvicorn with `--port 80` under sufficient privileges (`sudo`, or `setcap 'cap_net_bind_service=+ep'` on the Python binary), or put a minimal nginx/caddy reverse proxy in front. The build should default to 8000 and document the port-80 options in the README; don't require root to run.
- A `run.sh` convenience script and an optional `systemd` unit file so it survives reboots/logout.
- DuckDB file and Parquet exports live under `data/` (gitignored except a small seed).

## Backfill to Microsoft Dataverse

`scripts/export_parquet.py` writes each table to `data/parquet/<table>.parquet`. Field names and the table structure intentionally mirror Bruno's proposed Dataverse tables so the migration is a direct mapping:

| Prototype | Microsoft Dataverse (proposed / existing) |
|---|---|
| `procedure_types` | Procedure Types (vocab) |
| `instruments` + `instrument_compatible_types` | Instruments table w/ Compatible Acquisition Platforms multiselect; `sipe_rig_name` is the rig identity |
| `scheduled_procedures` | Scheduled Procedures / Schedule Acquisitions table (new) |
| `scheduled_procedure_active_types` | Active Acquisition Platforms multiselect |
| `acquisition_type` | Acquisition Type (computed concatenation) |
| `mice` | **existing** `aibs_dim_mices` (don't recreate — reference it) |
| `projects`, `users` | existing Dataverse lookups (Project, Users) |
| `planned_config` (behavior rows) | association to the existing `aibs_fact_mouse_proposed_behavior_sessionses` row(s) |

Practical notes for whoever does the real migration, so our exports drop in cleanly:

- Dataverse is a **star schema** with `aibs_`-prefixed `dim_`/`fact_` tables and **GUID** primary keys; relationships are set with the `field@odata.bind = /table(guid)` syntax, not by writing a foreign-key column directly. Our string-UUID keys map onto those GUIDs.
- `mice` already exists as `aibs_dim_mices` — the real scheduled-procedures table should look up mice there rather than importing ours.
- Standard audit columns (`createdon`, `modifiedon`) are added by Dataverse automatically; our `created_at`/`updated_at` are the analogues.

When Dataverse is ready, the Parquet exports become the import payload; existing prototype rows carry over rather than being re-entered.

## Tech stack

- Python 3.11+, FastAPI, uvicorn.
- DuckDB (store) + pyarrow (Parquet export).
- Pydantic v2 for request/response models and validation.
- Frontend: vanilla JS + FullCalendar from CDN. No bundler.
- Tests: pytest + httpx (FastAPI TestClient).

Keep dependencies minimal. No external services, no database server, no auth libraries.

## Open questions for reviewers

1. Are "Procedure Types" and "Acquisition Platforms" one vocabulary or two? (Prototype assumes one.)
2. ~~Do SmartSPIM pre-acquisition steps (requests, surgeries, histology) need dedicated tables in the prototype?~~ **Resolved: no.** The Dataverse team is actively building SmartSPIM imaging/histology and surgical request forms already (David Feng, Aug 2026), so the prototype stays out of that lane and focuses on behavior/physiology scheduling. Confirm this division of labor is still accurate with the Dataverse team.
3. Is a single scientific contact enough, or do we need multiple contacts as well as multiple experimenters?
4. Should `status` be included now (it's cheap and lets the Dataverse team see where notifications would hook in), or strictly deferred?
5. What is the logical name and schema of the existing **"Behavior Training"** table (scientific-contact-per-mouse)? It isn't referenced in the rig code, so we need the PowerPlatform team to share it. Until then the prototype populates `contact_user_id` manually; the real integration should read it from there.