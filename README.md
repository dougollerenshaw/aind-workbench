# AIND Workbench

Personal repository of code examples, notebooks, and utilities developed while working at the Allen Institute for Neural Dynamics. Contains exploratory analyses, database queries, workflow examples, and utility scripts.

## Structure

```
.
├── aind_workbench/    # Importable shared utility functions (installable package)
├── notebooks/         # Jupyter notebooks for analysis and exploration
├── scripts/          # Utility scripts and data processing tools
├── examples/         # Code examples and demonstrations
├── projects/         # Self-contained tools and one-off project work
└── docs/            # Additional documentation
```

## Shared utilities (`aind_workbench`)

General-purpose, reusable functions live in the `aind_workbench` package so they can
be imported anywhere. Install it editable from the repo root:

```bash
uv pip install -e .          # or: pip install -e .
```

Then:

```python
from aind_workbench import get_iacuc_id_for_mouse

get_iacuc_id_for_mouse("762287")   # -> "2414"  (current IACUC protocol number)
```

CLI equivalent (installed as a console script):

```bash
get-iacuc-id 762287            # -> 2414
get-iacuc-id 762287 --details  # JSON with source + per-surgery history
```

Available helpers:

| Function | Purpose |
|---|---|
| `get_iacuc_id_for_mouse(subject_id)` | Current IACUC protocol number for a mouse (DocDB fast path, metadata-service fallback). |
