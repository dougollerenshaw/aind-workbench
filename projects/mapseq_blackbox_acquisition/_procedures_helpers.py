"""Shared helpers for MAPseq/BARseq procedures generation.

The contents of this module are copied verbatim from
aind-data-schema PR #1763 (`examples/procedures_sectioning.py`,
branch `1729-barseqmapseq-procedures`, author: Dan Birman).

Kept here so the workbench can produce procedures.json files for
780345 and 780346 without depending on the example-file location
in the schema repo. See implementation_summary.md for context.
"""

from datetime import date
from typing import Dict, List

from aind_data_schema_models.brain_atlas import CCFv3
from aind_data_schema_models.units import SizeUnit

from aind_data_schema.components.coordinates import Translation
from aind_data_schema.components.specimen_procedures import (
    PlanarSection,
    PlanarSectioning,
    Section,
    Sectioning,
    SectionOrientation,
    SpecimenProcedure,
)

_SLIDE_REGIONS = [
    {"slide_num": 1, "section_start": 1, "section_end": 3, "chunk_name": "MOB", "ccf_acronym": "MOB", "includes_surrounding_tissue": False, "notes": "Main olfactory bulb"},
    {"slide_num": 2, "section_start": 4, "section_end": 6, "chunk_name": "MOB", "ccf_acronym": "MOB", "includes_surrounding_tissue": False, "notes": "Main olfactory bulb"},
    {"slide_num": 3, "section_start": 7, "section_end": 9, "chunk_name": "ORB", "ccf_acronym": "ORB", "includes_surrounding_tissue": False, "notes": "Orbital area (orbitofrontal cortex)"},
    {"slide_num": 3, "section_start": 7, "section_end": 9, "chunk_name": "MO", "ccf_acronym": "MO", "includes_surrounding_tissue": False, "notes": "Somatomotor areas (motor cortex)"},
    {"slide_num": 3, "section_start": 7, "section_end": 9, "chunk_name": "AON", "ccf_acronym": "AON", "includes_surrounding_tissue": False, "notes": "Anterior olfactory nucleus"},
    {"slide_num": 4, "section_start": 10, "section_end": 12, "chunk_name": "ORB", "ccf_acronym": "ORB", "includes_surrounding_tissue": False, "notes": "Orbital area (orbitofrontal cortex)"},
    {"slide_num": 4, "section_start": 10, "section_end": 12, "chunk_name": "MO", "ccf_acronym": "MO", "includes_surrounding_tissue": False, "notes": "Somatomotor areas (motor cortex)"},
    {"slide_num": 4, "section_start": 10, "section_end": 12, "chunk_name": "AON", "ccf_acronym": "AON", "includes_surrounding_tissue": False, "notes": "Anterior olfactory nucleus"},
    {"slide_num": 5, "section_start": 13, "section_end": 15, "chunk_name": "CP", "ccf_acronym": "CP", "includes_surrounding_tissue": False, "notes": "Caudoputamen"},
    {"slide_num": 5, "section_start": 13, "section_end": 15, "chunk_name": "ACB", "ccf_acronym": "ACB", "includes_surrounding_tissue": False, "notes": "Nucleus accumbens"},
    {"slide_num": 5, "section_start": 13, "section_end": 15, "chunk_name": "LSX", "ccf_acronym": "LSX", "includes_surrounding_tissue": False, "notes": "Lateral septal complex"},
    {"slide_num": 5, "section_start": 13, "section_end": 15, "chunk_name": "ctx_1", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Superior/dorsal cortex ribbon (ctx 1 in figure)"},
    {"slide_num": 5, "section_start": 13, "section_end": 15, "chunk_name": "ctx_2", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Lateral cortex ribbon (ctx 2 in figure)"},
    {"slide_num": 5, "section_start": 13, "section_end": 15, "chunk_name": "ctx_3", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Inferior/ventrolateral cortex ribbon (ctx 3 in figure)"},
    {"slide_num": 6, "section_start": 16, "section_end": 18, "chunk_name": "CP", "ccf_acronym": "CP", "includes_surrounding_tissue": False, "notes": "Caudoputamen"},
    {"slide_num": 6, "section_start": 16, "section_end": 18, "chunk_name": "ACB", "ccf_acronym": "ACB", "includes_surrounding_tissue": False, "notes": "Nucleus accumbens"},
    {"slide_num": 6, "section_start": 16, "section_end": 18, "chunk_name": "LSX", "ccf_acronym": "LSX", "includes_surrounding_tissue": False, "notes": "Lateral septal complex"},
    {"slide_num": 6, "section_start": 16, "section_end": 18, "chunk_name": "ctx_1", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Superior/dorsal cortex ribbon (ctx 1 in figure)"},
    {"slide_num": 6, "section_start": 16, "section_end": 18, "chunk_name": "ctx_2", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Lateral cortex ribbon (ctx 2 in figure)"},
    {"slide_num": 6, "section_start": 16, "section_end": 18, "chunk_name": "ctx_3", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Inferior/ventrolateral cortex ribbon (ctx 3 in figure)"},
    {"slide_num": 7, "section_start": 19, "section_end": 21, "chunk_name": "CP", "ccf_acronym": "CP", "includes_surrounding_tissue": False, "notes": "Caudoputamen"},
    {"slide_num": 7, "section_start": 19, "section_end": 21, "chunk_name": "LSX", "ccf_acronym": "LSX", "includes_surrounding_tissue": False, "notes": "Lateral septal complex"},
    {"slide_num": 7, "section_start": 19, "section_end": 21, "chunk_name": "BST", "ccf_acronym": "BST", "includes_surrounding_tissue": False, "notes": "Bed nuclei of the stria terminalis (BNST)"},
    {"slide_num": 7, "section_start": 19, "section_end": 21, "chunk_name": "ctx_1", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Superior/dorsal cortex ribbon (ctx 1 in figure)"},
    {"slide_num": 7, "section_start": 19, "section_end": 21, "chunk_name": "ctx_2", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Lateral cortex ribbon (ctx 2 in figure)"},
    {"slide_num": 7, "section_start": 19, "section_end": 21, "chunk_name": "ctx_3", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Inferior/ventrolateral cortex ribbon (ctx 3 in figure)"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "HPF", "ccf_acronym": "HPF", "includes_surrounding_tissue": False, "notes": "Hippocampal formation"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "TH", "ccf_acronym": "TH", "includes_surrounding_tissue": False, "notes": "Thalamus"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "HY", "ccf_acronym": "HY", "includes_surrounding_tissue": False, "notes": "Hypothalamus"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "amygdala", "ccf_acronym": "BLA", "includes_surrounding_tissue": True, "notes": "Amygdala (targeting whole structure via BLA + surrounding tissue)"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "GPE", "ccf_acronym": "GPe", "includes_surrounding_tissue": False, "notes": "Globus pallidus external segment (GPe)"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "ctx_1", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Superior/dorsal cortex ribbon (ctx 1 in figure)"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "ctx_2", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Lateral cortex ribbon (ctx 2 in figure)"},
    {"slide_num": 8, "section_start": 22, "section_end": 24, "chunk_name": "ctx_3", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Inferior/ventrolateral cortex ribbon (ctx 3 in figure)"},
    {"slide_num": 9, "section_start": 25, "section_end": 27, "chunk_name": "MB", "ccf_acronym": "MB", "includes_surrounding_tissue": False, "notes": "Midbrain"},
    {"slide_num": 9, "section_start": 25, "section_end": 27, "chunk_name": "ctx_1", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Superior/dorsal cortex ribbon (ctx 1 in figure)"},
    {"slide_num": 9, "section_start": 25, "section_end": 27, "chunk_name": "ctx_2", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Lateral cortex ribbon (ctx 2 in figure)"},
    {"slide_num": 9, "section_start": 25, "section_end": 27, "chunk_name": "ctx_3", "ccf_acronym": "CTX", "includes_surrounding_tissue": True, "notes": "Inferior/ventrolateral cortex ribbon (ctx 3 in figure)"},
    {"slide_num": 10, "section_start": 28, "section_end": 30, "chunk_name": "MB", "ccf_acronym": "MB", "includes_surrounding_tissue": False, "notes": "Midbrain (more caudal)"},
    {"slide_num": 10, "section_start": 28, "section_end": 30, "chunk_name": "HB", "ccf_acronym": "HB", "includes_surrounding_tissue": False, "notes": "Hindbrain"},
    {"slide_num": 11, "section_start": 31, "section_end": 33, "chunk_name": "MB", "ccf_acronym": "MB", "includes_surrounding_tissue": False, "notes": "Midbrain (most caudal)"},
    {"slide_num": 11, "section_start": 31, "section_end": 33, "chunk_name": "HB", "ccf_acronym": "HB", "includes_surrounding_tissue": False, "notes": "Hindbrain"},
    {"slide_num": 12, "section_start": 34, "section_end": 36, "chunk_name": "CB", "ccf_acronym": "CB", "includes_surrounding_tissue": False, "notes": "Cerebellum"},
    {"slide_num": 12, "section_start": 34, "section_end": 36, "chunk_name": "MY", "ccf_acronym": "MY", "includes_surrounding_tissue": False, "notes": "Medulla"},
    {"slide_num": 13, "section_start": 37, "section_end": 39, "chunk_name": "MY", "ccf_acronym": "MY", "includes_surrounding_tissue": False, "notes": "Medulla"},
]


def _load_slide_regions() -> Dict[int, dict]:
    """Load slide region data from _SLIDE_REGIONS and organize by slide number."""
    slides: Dict[int, dict] = {}
    for row in _SLIDE_REGIONS:
        slide = row["slide_num"]
        if slide not in slides:
            slides[slide] = {
                "section_start": row["section_start"],
                "section_end": row["section_end"],
                "chunks": [],
            }
        slides[slide]["chunks"].append(
            {
                "chunk_name": row["chunk_name"],
                "ccf_acronym": row["ccf_acronym"],
                "includes_surrounding_tissue": row["includes_surrounding_tissue"],
                "notes": row["notes"],
            }
        )
    return slides


def generate_mapseq_slide_chunks(specimen_id: str) -> List[SpecimenProcedure]:
    """Generate specimen procedures for the MAPseq slide chunking based on _SLIDE_REGIONS."""
    slides = _load_slide_regions()
    procedures = []
    for slide_num, slide_data in slides.items():
        section_start = slide_data["section_start"]
        section_end = slide_data["section_end"]
        chunks = slide_data["chunks"]

        input_ids = [f"{specimen_id}_map{i:03d}" for i in range(section_start, section_end + 1)]

        output_sections = []
        for chunk_idx, chunk in enumerate(chunks, start=1):
            structure = CCFv3.by_acronym(chunk["ccf_acronym"])
            surrounding = True if chunk["includes_surrounding_tissue"] else None
            for sec_id in input_ids:
                output_sections.append(
                    Section(
                        output_specimen_id=f"{sec_id}_{chunk_idx:03d}",
                        targeted_structure=structure,
                        includes_surrounding_tissue=surrounding,
                    )
                )

        chunk_names = ", ".join(c["chunk_name"] for c in chunks)
        ctx_notes = "; ".join(c["notes"] for c in chunks if c["ccf_acronym"] == "CTX")
        note = f"Slide {slide_num}: sections {section_start}-{section_end} chunked into [{chunk_names}]"
        if ctx_notes:
            note += f". CTX chunks: {ctx_notes}"

        procedures.append(
            SpecimenProcedure(
                procedure_type="Sectioning",
                specimen_id=input_ids,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                experimenters=["Polina Kosillo"],
                procedure_details=[Sectioning(sections=output_sections)],
                notes=note,
            )
        )
    return procedures


def create_planar_section(
    specimen_id: str,
    section_id: str,
    coordinate_system_name: str,
    start_um: float,
    thickness: float,
    thickness_unit: SizeUnit,
) -> PlanarSection:
    """Create a PlanarSection with the given parameters."""
    return PlanarSection(
        output_specimen_id=f"{specimen_id}_{section_id}",
        coordinate_system_name=coordinate_system_name,
        start_coordinate=Translation(translation=[round(start_um), 0, 0]),
        thickness=thickness,
        thickness_unit=thickness_unit,
    )


def create_uniform_sections(
    specimen_id: str,
    start_section_num: int,
    num_sections: int,
    start_um: float,
    thickness: float,
    thickness_unit: SizeUnit,
    coordinate_system_name: str = "CCF",
    section_prefix: str = "sec",
) -> List[PlanarSection]:
    """Create a list of PlanarSections with uniform spacing."""
    return [
        create_planar_section(
            specimen_id=specimen_id,
            section_id=f"{section_prefix}{start_section_num + i:03d}",
            coordinate_system_name=coordinate_system_name,
            start_um=start_um + i * thickness,
            thickness=thickness,
            thickness_unit=thickness_unit,
        )
        for i in range(num_sections)
    ]


def create_nonuniform_sections(
    specimen_id: str,
    num_sections: int,
    start_positions_um: List[float],
    thickness: float,
    thickness_unit: SizeUnit,
    coordinate_system_name: str = "CCF",
    section_prefix: str = "sec",
    start_section_num: int = 1,
) -> List[PlanarSection]:
    """Create a list of PlanarSections with non-uniform spacing."""
    if num_sections != len(start_positions_um):
        raise ValueError("num_sections and start_positions_um must have same length")

    return [
        create_planar_section(
            specimen_id=specimen_id,
            section_id=f"{section_prefix}{start_section_num + i:03d}",
            coordinate_system_name=coordinate_system_name,
            start_um=start_um,
            thickness=thickness,
            thickness_unit=thickness_unit,
        )
        for i, start_um in enumerate(start_positions_um)
    ]


def create_planar_sectioning(
    sections: List[PlanarSection],
    section_orientation: SectionOrientation = SectionOrientation.CORONAL,
) -> PlanarSectioning:
    """Create a PlanarSectioning procedure with the given sections and orientation."""
    return PlanarSectioning(
        sections=sections,
        section_orientation=section_orientation,
    )


def collect_unique_specimen_ids(*procedure_results) -> List[str]:
    """Extract unique output_specimen_ids (in order) from PlanarSectioning/Sectioning results.

    Used to keep the acquisition's specimen_id list in sync with the
    procedures-level definitions.
    """
    ids: List[str] = []
    seen: set = set()
    for result in procedure_results:
        for sec in result.sections:
            sid = sec.output_specimen_id
            if sid not in seen:
                seen.add(sid)
                ids.append(sid)
    return ids
