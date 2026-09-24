"""Shared test setup for the tool launcher.

`launcher.py` reads SCHEDULER_DB **at import time**, and several test modules
import it. Setting the variable here — before any test module runs — guarantees
two things:

1. Every test points the scheduler at a throwaway database, so the suite can
   never open (or lock) the real `data/procedure_scheduling.duckdb` that the
   live service is using.
2. All test modules agree on the value, whichever one imports `launcher` first.
   (They previously each set it themselves, so import order decided the winner
   and an assertion comparing the two disagreed.)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

SCRATCH_DB = Path(tempfile.mkdtemp(prefix="tool-launcher-tests-")) / "scheduler.duckdb"
os.environ["SCHEDULER_DB"] = str(SCRATCH_DB)
