"""
Utility functions for getting subject lists.
"""

# Subject IDs extracted from the SmartSPIM filenames in Polina's analysis capsule
PATCHSEQ_SUBJECT_IDS = [
    "716946",
    "716947",
    "716948",
    "716949",
    "716950",
    "716951",
    "725231",
    "725328",
    "725329",
    "728854",
    "731907",
    "737038",
    "737042",
    "744117",
    "744119",
    "746041",
    "746043",
    "746045",
    "746046",
    "751017",
    "751019",
    "751023",
    "751024",
    "751035",
    "755069",
    "755071",
    "755072",
    "755073",
    "755790",
    "762196",
    "762199",
]


def get_subjects_list():
    """
    Get the list of patchseq subject IDs.
    
    Returns:
        list: List of subject IDs
    """
    print(f"Found {len(PATCHSEQ_SUBJECT_IDS)} patchseq subjects")
    return PATCHSEQ_SUBJECT_IDS
