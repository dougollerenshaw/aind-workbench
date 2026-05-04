"""MAPseq acquisition metadata for subjects 780345 and 780346.

MAPseq (Multiplexed Analysis of Projections by Sequencing) is a barcode-based
projection mapping method in which brain sections are processed and sequenced
to map the long-range projections of individually labeled neurons. The
processed output is a barcode x section matrix that maps individual neurons
to their projection targets across the brain.

This script produces one acquisition.json per subject. Because the full
acquisition spans multiple slides over multiple days and the detailed
per-slide parameters are not fully documented, the acquisition is described at
a high level: inputs (brain sections), timeframe, and experimenters.

Specimen IDs follow the convention {subject_id}_map{n:03d}, matching the
section IDs defined in the companion procedures metadata.
"""

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aind_data_schema_models.modalities import Modality

from aind_data_schema.core.acquisition import Acquisition, ExternalDataStream

from procedures_780345 import MAPSEQ_SPECIMEN_IDS as IDS_780345
from procedures_780346 import MAPSEQ_SPECIMEN_IDS as IDS_780346

# No published MAPseq protocol URL available at the time of writing.
MAPSEQ_PROTOCOL_ID: list[str] = []

# Acquisition note template applied to all subjects.
ACQUISITION_NOTE = (
    "MAPseq was performed off-site at Cold Spring Harbor Laboratory. "
    "The acquisition_start_time represents the date the tissue was mailed to "
    "CSHL; the acquisition_end_time represents the date the final processed "
    "results were received."
)

SUBJECTS = {
    "780345": {
        "experimenters": ["Cold Spring Harbor Laboratory (CSHL) MAPseq team"],
        # Start: date sample was shipped to CSHL for MAPseq processing.
        # End: last reprocessing date from the pipeline (CSHL re-delivered data
        # multiple times over ~8 months due to processing issues).
        # Source: Polina Kosillo Teams chat, 2026-05-01.
        # Time-of-day not provided; using noon to avoid timezone-edge day shifts.
        "acquisition_start": datetime(2025, 3, 24, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        "acquisition_end": datetime(2025, 10, 30, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        # Imported from procedures_780345.py to keep acquisition and procedures in sync.
        "specimen_id": IDS_780345,
    },
    "780346": {
        "experimenters": ["Cold Spring Harbor Laboratory (CSHL) MAPseq team"],
        # Start: date sample was shipped to CSHL for MAPseq processing.
        # End: last reprocessing date from the pipeline.
        # Source: Polina Kosillo Teams chat, 2026-05-01.
        # Time-of-day not provided; using noon to avoid timezone-edge day shifts.
        "acquisition_start": datetime(2025, 7, 23, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        "acquisition_end": datetime(2025, 10, 30, 12, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")),
        # Imported from procedures_780346.py to keep acquisition and procedures in sync.
        "specimen_id": IDS_780346,
    },
}


def build_acquisition(subject_id: str) -> Acquisition:
    """Build a black-box MAPseq acquisition for a given subject."""
    params = SUBJECTS[subject_id]

    return Acquisition(
        subject_id=subject_id,
        specimen_id=params["specimen_id"],
        acquisition_start_time=params["acquisition_start"],
        acquisition_end_time=params["acquisition_end"],
        experimenters=params["experimenters"],
        protocol_id=MAPSEQ_PROTOCOL_ID,
        acquisition_type="BarcodeSequencing",
        notes=ACQUISITION_NOTE,
        data_streams=[
            ExternalDataStream(
                stream_start_time=params["acquisition_start"],
                stream_end_time=params["acquisition_end"],
                modalities=[Modality.MAPSEQ],
                notes="Acquired off-site at Cold Spring Harbor Laboratory.",
            )
        ],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate MAPseq acquisition metadata JSON files.")
    parser.add_argument("--output-dir", default=".", help="Output directory for JSON files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for subject_id in SUBJECTS:
        acq = build_acquisition(subject_id)
        serialized = acq.model_dump_json()
        deserialized = Acquisition.model_validate_json(serialized)
        deserialized.write_standard_file(prefix=f"mapseq_{subject_id}", output_directory=output_dir)
        print(f"Written: mapseq_{subject_id}_acquisition.json")
