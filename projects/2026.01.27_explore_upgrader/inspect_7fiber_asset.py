"""
Inspect what's actually in the "7 fiber" asset
"""

import json
from aind_data_access_api.document_db import MetadataDbClient


def inspect_asset(asset_id: str):
    """Inspect the fiber connections in detail"""
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
    data_streams = session.get("data_streams", [])
    
    print(f"Asset: {asset_id}")
    print(f"Name: {record.get('name')}")
    print(f"Session version: {session.get('schema_version')}")
    print(f"\nData streams: {len(data_streams)}")
    
    for stream_idx, stream in enumerate(data_streams):
        print(f"\n=== Stream {stream_idx} ===")
        
        fiber_connections = stream.get("fiber_connections", [])
        print(f"Fiber connections: {len(fiber_connections)}")
        
        for idx, fc in enumerate(fiber_connections):
            print(f"\nFiber connection {idx}:")
            print(f"  Keys: {list(fc.keys())}")
            print(f"  Patch cord: {fc.get('patch_cord_name', 'N/A')}")
            print(f"  Fiber: {fc.get('fiber_name', 'N/A')}")
            
            if "channel" in fc:
                channel = fc["channel"]
                print(f"  Channel name: {channel.get('channel_name', 'N/A')}")
                print(f"  Has channel: YES")
            else:
                print(f"  Has channel: NO")
        
        # Save full stream to file
        output_file = f"7fiber_stream_{stream_idx}.json"
        with open(output_file, "w") as f:
            json.dump(stream, f, indent=2, default=str)
        print(f"\nFull stream saved to: {output_file}")


if __name__ == "__main__":
    asset_id = "89d976e2-1765-48e2-b662-817b6170b9aa"
    inspect_asset(asset_id)
