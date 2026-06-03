"""Procedures metadata for subject 780345.

Generates `procedures_780345.json`. Subject-specific generators are
adapted from aind-data-schema PR #1763
(`examples/procedures_sectioning.py`, branch `1729-barseqmapseq-procedures`).

Also exposes `MAPSEQ_SPECIMEN_IDS`, the canonical list of MAPseq output
specimen IDs for this subject. `mapseq_acquisition.py` imports this constant
so the acquisition's `specimen_id` list stays in sync with the procedures.
"""

import argparse
from datetime import date
from pathlib import Path

from aind_data_schema_models.brain_atlas import CCFv3
from aind_data_schema_models.units import SizeUnit

from aind_data_schema.components.coordinates import AtlasLibrary
from aind_data_schema.components.specimen_procedures import (
    Section,
    Sectioning,
    SpecimenProcedure,
)
from aind_data_schema.core.procedures import Procedures

from _procedures_helpers import (
    collect_acquisition_specimen_ids,
    create_nonuniform_sections,
    create_planar_sectioning,
    create_uniform_sections,
    generate_mapseq_slide_chunks,
)

SUBJECT_ID = "780345"

# TODO: confirm actual sectioning dates with Polina Kosillo. Placeholder
# matches PR #1763. Sectioning happened in-house at the Allen Institute
# before tissue was shipped to CSHL (2025-03-24 for this subject).
_SECTIONING_DATE = date(2024, 1, 1)


def generate_mapseq_first_batch():
    """First batch of MAPseq slides: sections 1-27, plates 0-98 (300um, partial slices)."""
    start_positions = [i * (9800 / 27) for i in range(27)]
    sections = create_nonuniform_sections(
        specimen_id=SUBJECT_ID,
        num_sections=27,
        start_positions_um=start_positions,
        thickness=300,
        thickness_unit=SizeUnit.UM,
        section_prefix="map",
        start_section_num=1,
    )
    return create_planar_sectioning(sections)


def generate_mapseq_second_batch():
    """Second batch of MAPseq slides: sections 28-39, plates 112-132 (300um, partial slices)."""
    start_positions = [11200 + i * (2000 / 12) for i in range(12)]
    sections = create_nonuniform_sections(
        specimen_id=SUBJECT_ID,
        num_sections=12,
        start_positions_um=start_positions,
        thickness=300,
        thickness_unit=SizeUnit.UM,
        section_prefix="map",
        start_section_num=28,
    )
    return create_planar_sectioning(sections)


def generate_barseq_lc():
    """BARseq LC slides: 44 sections, plates 99-112 (20um uniform spacing)."""
    sections = create_uniform_sections(
        specimen_id=SUBJECT_ID,
        start_section_num=1,
        num_sections=44,
        start_um=9900,
        thickness=20,
        thickness_unit=SizeUnit.UM,
        section_prefix="bar",
    )
    return create_planar_sectioning(sections)


def generate_mapseq_spinal():
    """MAPseq spinal cord: one specimen cut into 3 thirds (size approximate)."""
    return Sectioning(
        sections=[
            Section(
                output_specimen_id=f"{SUBJECT_ID}_spinal",
                targeted_structure=CCFv3.CST,
                thickness=1000,
                thickness_unit=SizeUnit.UM,
            ),
            Section(
                output_specimen_id=f"{SUBJECT_ID}_spinal",
                targeted_structure=CCFv3.CST,
                thickness=1000,
                thickness_unit=SizeUnit.UM,
            ),
            Section(
                output_specimen_id=f"{SUBJECT_ID}_spinal",
                targeted_structure=CCFv3.CST,
                thickness=1000,
                thickness_unit=SizeUnit.UM,
            ),
        ]
    )


def generate_procedures() -> Procedures:
    """Build the full Procedures object for subject 780345."""
    return Procedures(
        subject_id=SUBJECT_ID,
        coordinate_system=AtlasLibrary.CCFv3_10um,
        specimen_procedures=[
            SpecimenProcedure(
                procedure_type="Sectioning",
                specimen_id=SUBJECT_ID,
                start_date=_SECTIONING_DATE,
                end_date=_SECTIONING_DATE,
                experimenters=["Polina Kosillo"],
                procedure_details=[generate_mapseq_first_batch()],
                notes="MAPseq sections 1-27 covering plates 0-98 (300um thick, partial slices)",
            ),
            SpecimenProcedure(
                procedure_type="Sectioning",
                specimen_id=SUBJECT_ID,
                start_date=_SECTIONING_DATE,
                end_date=_SECTIONING_DATE,
                experimenters=["Polina Kosillo"],
                procedure_details=[generate_barseq_lc()],
                notes="BARseq LC sections 1-44 covering plates 99-112 (20um thick)",
            ),
            SpecimenProcedure(
                procedure_type="Sectioning",
                specimen_id=SUBJECT_ID,
                start_date=_SECTIONING_DATE,
                end_date=_SECTIONING_DATE,
                experimenters=["Polina Kosillo"],
                procedure_details=[generate_mapseq_second_batch()],
                notes="MAPseq sections 28-39 covering plates 112-132 (300um thick, partial slices)",
            ),
            SpecimenProcedure(
                procedure_type="Sectioning",
                specimen_id=SUBJECT_ID,
                start_date=_SECTIONING_DATE,
                end_date=_SECTIONING_DATE,
                experimenters=["Polina Kosillo"],
                procedure_details=[generate_mapseq_spinal()],
                notes="MAPseq spinal cord sections, size is approximate (1/3rd length each)",
            ),
            *generate_mapseq_slide_chunks(SUBJECT_ID),
        ],
    )


# Canonical MAPseq specimen IDs for this subject — flat list of chunk-level
# outputs (and the spinal cord) drawn from the Sectioning sub-procedures.
# Imported by mapseq_acquisition.py to keep acquisition's specimen_id list
# in sync with procedures.
MAPSEQ_SPECIMEN_IDS = collect_acquisition_specimen_ids(generate_procedures())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate procedures metadata for subject 780345.")
    parser.add_argument("--output-dir", default=".", help="Output directory for the JSON file")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    procs = generate_procedures()
    serialized = procs.model_dump_json()
    deserialized = Procedures.model_validate_json(serialized)
    deserialized.write_standard_file(output_directory=output_dir, filename_suffix=SUBJECT_ID)
    print(f"Written: procedures_{SUBJECT_ID}.json")
