# Mapping subject ID → IACUC protocol via the AIND metadata service

**Goal:** Given a subject/mouse ID, return the IACUC protocol name by querying Dataverse
through the `aind-metadata-service`.

**TL;DR:** The mapping is built into the schema (`aibs_dim_mice` has an `aibs_iacuc_protocol`
lookup to the protocol table), so it's a single-table query with no join. **However, as of
2026-06 the field is null for all 1156 mice** — structurally present, not yet populated. A
query today returns nothing for every subject.

---

## The API

OpenAPI spec: `https://aind-metadata-service/openapi.json`
(Swagger UI: `https://aind-metadata-service/docs`)

Two relevant endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/v2/dataverse/tables` | Lists all 147 tables (`entitysetname`, `logicalname`, `name`) |
| `GET /api/v2/dataverse/tables/{entitysetname}?columns=<csv>&filter=<OData>` | Returns rows; optional column selection + OData filter |

Note the URL takes the **entity set name** (pluralized), e.g. table `aibs_dim_mice` →
`aibs_dim_mices`.

## The relevant tables

- **`aibs_dim_mices`** (1156 rows) — the mouse dimension.
  - `aibs_mouse_id` — the subject ID (e.g. `835272`)
  - `aibs_genotype`, `aibs_sex`, `aibs_date_of_birth`, `aibs_deceased`, `aibs_reverse_light_cycle`
  - `aibs_dim_miceid` — primary key (GUID)
  - **`aibs_iacuc_protocol`** — lookup → `aibs_dim_iacuc_protocols`  ← *the link we want*
- **`aibs_dim_iacuc_protocolses`** (32 rows) — the protocol registry.
  - `aibs_protocol_id` — the protocol name/number (e.g. `2301-Westlake`)
  - principal investigator (lookup), committee, currently_active, initial_approval_date,
    expiration_date

## The query (when data is populated)

```
GET /api/v2/dataverse/tables/aibs_dim_mices
      ?columns=aibs_mouse_id,aibs_iacuc_protocol
      &filter=aibs_mouse_id eq '835272'
```

Then read the protocol name from the lookup's formatted annotation:
`_aibs_iacuc_protocol_value@OData.Community.Display.V1.FormattedValue` → e.g. `2301-Westlake`.

## Current data status

Selecting the lookup across the whole table returns **0 / 1156 mice populated**:

```
GET /api/v2/dataverse/tables/aibs_dim_mices?columns=aibs_mouse_id,aibs_iacuc_protocol
→ 1156 rows, none have _aibs_iacuc_protocol_value set
```

So the column exists but hasn't been filled in for any current subject (these records were
created ~Feb 2026). Worth checking with whoever owns the colony-management data whether/when
this gets populated.

## Gotchas (these cost real time to discover)

1. **Null fields are omitted from the JSON.** An all-null column is invisible in the returned
   data — the only way we found `aibs_iacuc_protocol` existed was the schema diagram. Confirm a
   column exists by `columns=`-selecting it, not by inspecting the keys of row 0.
2. **Use the lookup, not the display-name field.** `aibs_iacuc_protocol` /
   `_aibs_iacuc_protocol_value` are queryable. The denormalized display strings shown in the
   schema diagram — `aibs_iacuc_protocolname`, `aibs_projectname` — throw a **500** if you try
   to select them. (The lookup's `FormattedValue` gives you the protocol id anyway.)
3. **Raw lookup GUIDs are stripped.** The service returns only the
   `_<lookup>_value@OData.Community.Display.V1.FormattedValue` (human-readable) form.
4. **`filter=... ne null` returns a 404.** To find populated rows, select the column and check
   presence client-side rather than server-filtering on null.
5. **Large tables cap at 5000 rows** returned (e.g. water/weight record tables). `aibs_dim_mices`
   at 1156 rows is fully returned.

## Verdict

- **Structurally: yes** — a clean, single-table subject → IACUC protocol lookup exists.
- **Practically: not yet** — the field is empty for all current subjects, so the function would
  return `None` today.
