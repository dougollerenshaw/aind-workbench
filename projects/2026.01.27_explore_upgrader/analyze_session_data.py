"""
Analyze the session data to understand the fiber photometry stream structure
"""

import json
from aind_data_access_api.document_db import MetadataDbClient


def analyze_session(asset_id: str):
    """Analyze the session data for fiber photometry streams"""
    client = MetadataDbClient(
        host="api.allenneuraldynamics.org",
        database="metadata_index",
        collection="data_assets"
    )
    
    record = client.retrieve_docdb_records(
        filter_query={"_id": asset_id},
        limit=1
    )[0]
    
    session = record.get("session", {})
    
    print(f"Session schema version: {session.get('schema_version', 'N/A')}")
    print(f"\nSession has {len(session.get('data_streams', []))} data streams")
    
    # Examine each data stream
    for idx, stream in enumerate(session.get("data_streams", [])):
        print(f"\n--- Data Stream {idx} ---")
        print(f"  Modality abbreviation: {stream.get('stream_modalities', [{}])[0].get('abbreviation', 'N/A')}")
        print(f"  Stream start time: {stream.get('stream_start_time', 'N/A')}")
        print(f"  Number of daq names: {len(stream.get('daq_names', []))}")
        
        # Check light sources
        light_sources = stream.get("light_sources", [])
        print(f"  Light sources: {len(light_sources)}")
        for ls_idx, ls in enumerate(light_sources):
            print(f"    {ls_idx}: {ls.get('device_type', 'N/A')} - {ls.get('name', 'N/A')}")
        
        # Check detectors
        detectors = stream.get("detectors", [])
        print(f"  Detectors: {len(detectors)}")
        for det_idx, det in enumerate(detectors):
            print(f"    {det_idx}: {det.get('device_type', 'N/A')} - {det.get('name', 'N/A')}")
        
        # Check for fiber connections (these might be missing)
        fiber_connections = stream.get("fiber_connections", [])
        print(f"  Fiber connections: {len(fiber_connections)}")
        for fc_idx, fc in enumerate(fiber_connections):
            print(f"    {fc_idx}: {fc}")
        
        # Check camera assemblies
        camera_assemblies = stream.get("camera_assemblies", [])
        print(f"  Camera assemblies: {len(camera_assemblies)}")
        
        # Save full stream to file for detailed inspection
        stream_file = f"stream_{idx}.json"
        with open(stream_file, 'w') as f:
            json.dump(stream, f, indent=2, default=str)
        print(f"  Full stream saved to: {stream_file}")
    
    # Save the full session for inspection
    session_file = "session_full.json"
    with open(session_file, 'w') as f:
        json.dump(session, f, indent=2, default=str)
    print(f"\nFull session saved to: {session_file}")


if __name__ == "__main__":
    asset_id = "733a1052-683c-46d2-96ca-8f89bd270192"
    analyze_session(asset_id)
