"""
Quick check if an asset will have the fiber connection upgrade issue
"""

import sys
from aind_data_access_api.document_db import MetadataDbClient


def check_asset(asset_id: str):
    """Check if an asset will have the fiber connection upgrade issue"""
    client = MetadataDbClient(
        host="api.allenneuraldynamics.org",
        database="metadata_index",
        collection="data_assets"
    )
    
    try:
        record = client.retrieve_docdb_records(
            filter_query={"_id": asset_id},
            limit=1
        )
        
        if not record:
            print(f"Asset {asset_id} not found")
            return
        
        record = record[0]
        session = record.get("session", {})
        
        print(f"\nAsset: {asset_id}")
        print(f"Name: {record.get('name', 'N/A')}")
        print(f"Session version: {session.get('schema_version', 'N/A')}")
        
        # Check data streams
        data_streams = session.get("data_streams", [])
        print(f"Data streams: {len(data_streams)}")
        
        has_fiber_connections = False
        has_fiber_photometry = False
        has_missing_channel = False
        total_fiber_connections = 0
        
        for stream in data_streams:
            # Check for fiber photometry modality
            modalities = stream.get("stream_modalities", [])
            for mod in modalities:
                if isinstance(mod, dict) and mod.get("abbreviation") == "fib":
                    has_fiber_photometry = True
                elif isinstance(mod, str) and mod == "fib":
                    has_fiber_photometry = True
            
            # Check fiber connections
            fiber_connections = stream.get("fiber_connections", [])
            if fiber_connections:
                has_fiber_connections = True
                total_fiber_connections += len(fiber_connections)
                
                for fc in fiber_connections:
                    if "channel" not in fc or not fc.get("channel"):
                        has_missing_channel = True
        
        print(f"Has fiber photometry modality: {has_fiber_photometry}")
        print(f"Has fiber connections: {has_fiber_connections}")
        print(f"Total fiber connections: {total_fiber_connections}")
        print(f"Missing channel data: {has_missing_channel}")
        
        # Verdict
        print("\n" + "=" * 60)
        if has_fiber_photometry and has_missing_channel:
            print("VERDICT: This asset WILL FAIL to upgrade")
            print("REASON: Fiber photometry stream with missing channel data")
            print(f"PATTERN: Has exactly {total_fiber_connections} fiber connections (4 = problematic)")
        elif has_fiber_connections and not has_missing_channel:
            print("VERDICT: This asset should upgrade successfully")
            print("REASON: Fiber connections have proper channel data")
        elif not has_fiber_connections:
            print("VERDICT: No fiber connections, upgrade should proceed")
        else:
            print("VERDICT: Unclear - no fiber photometry modality but has connections")
        
        print("=" * 60)
        
    except Exception as e:
        print(f"Error checking asset: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_asset.py <asset_id>")
        print("\nExample:")
        print("  python check_asset.py 733a1052-683c-46d2-96ca-8f89bd270192")
        sys.exit(1)
    
    asset_id = sys.argv[1]
    check_asset(asset_id)
