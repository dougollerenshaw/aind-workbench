talking through specimen_ids with Dan now.

The actual list of specimen_ids comes from procedures. All of the map###__### sections. Eg: 780345_map009_003
Every group of sections that share a final 3-digit nomenclature are repeats of the same brain area across slices.
For exeample, 
* 780345_map007_001
* 780345_map007_002
* 780345_map007_003
all map to "name": "Anterior olfactory nucleus", "acronym": "AON" and get combined in a tube for processing. 

The actual acquisition specimen_id list needs to be flat (as scheme calls for)

But Dan is proposing that maybe we should modify specimen_ids so that it's a nested dictionary like this:
specimen_ids: {
    ...
    "AON": ['780345_map007_001', '780345_map007_002', '780345_map007_003'],
    ...
}

But for now, just make it a flat list. The list is everything in procedures under "object_type": "Sectioning", (not "Planar sectioning")