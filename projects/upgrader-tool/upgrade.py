"""
Standalone script to test metadata upgrade for a specific asset.
Can be used from command line or imported by the Flask app.
"""
import argparse
import json
import traceback
from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade


def get_mongodb_client():
    """Get MongoDB client for metadata index"""
    return MetadataDbClient(
        host="api.allenneuraldynamics.org",
        database="metadata_index",
        collection="data_assets"
    )


def upgrade_asset(asset_identifier: str):
    """
    Upgrade a single asset by ID or name.
    
    Returns:
        dict: Result with success status, asset info, and upgrade details or errors
    """
    result = {
        'asset_identifier': asset_identifier,
        'success': False
    }
    
    try:
        # Connect and fetch asset
        client = get_mongodb_client()
        
        # Try to find asset by ID or name
        if len(asset_identifier) == 36 and '-' in asset_identifier:
            query = {"_id": asset_identifier}
        else:
            query = {"name": asset_identifier}
        
        records = client.retrieve_docdb_records(filter_query=query, limit=1)
        
        if not records:
            result['error'] = f'Asset not found: {asset_identifier}'
            return result
        
        asset_data = records[0]
        result['asset_id'] = asset_data.get('_id', 'Unknown')
        result['asset_name'] = asset_data.get('name', 'Unknown')
        result['created'] = str(asset_data.get('created', 'Unknown'))
        
        # Try to upgrade (Upgrade class does everything in __init__)
        print(f"\nUpgrading asset: {result['asset_id']}")
        print(f"Name: {result['asset_name']}")
        print(f"Created: {result['created']}")
        
        upgrader = Upgrade(asset_data)
        
        # The upgrader automatically processes everything, we just need to get the result
        upgraded_data = upgrader.metadata.model_dump()
        
        # Compare original to upgraded to see what changed
        upgraded_files = []
        unchanged_files = []
        
        for core_file in ['acquisition', 'data_description', 'instrument', 'procedures',
                         'processing', 'rig', 'session', 'subject', 'quality_control']:
            if core_file in upgraded_data:
                if core_file in asset_data:
                    # File existed before
                    if upgraded_data[core_file] != asset_data[core_file]:
                        upgraded_files.append(core_file)
                    else:
                        unchanged_files.append(core_file)
                else:
                    # File is new (e.g., session -> acquisition conversion)
                    upgraded_files.append(f"{core_file} (new)")
        
        # Check for conversions (session -> acquisition)
        if 'session' in asset_data and 'session' not in upgraded_data and 'acquisition' in upgraded_data:
            upgraded_files.append('session (converted to acquisition)')
        
        result['success'] = True
        result['upgraded_files'] = upgraded_files
        result['unchanged_files'] = unchanged_files
        
        print(f"\n[SUCCESS] Upgrade completed")
        print(f"  Changed: {', '.join(upgraded_files) if upgraded_files else 'None'}")
        print(f"  Unchanged: {', '.join(unchanged_files) if unchanged_files else 'None'}")
        
    except Exception as e:
        error_str = str(e)
        tb = traceback.format_exc()
        
        result['error'] = error_str
        result['traceback'] = tb
        
        print(f"\n[FAILED] Upgrade failed")
        print(f"Error: {error_str}")
        print(f"\nTraceback:")
        print(tb)
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Test AIND metadata upgrade for a specific asset')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--id', type=str, help='Asset ID (UUID)')
    group.add_argument('--name', type=str, help='Asset name')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    asset_identifier = args.id or args.name
    result = upgrade_asset(asset_identifier)
    
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    
    return 0 if result['success'] else 1


if __name__ == "__main__":
    exit(main())
