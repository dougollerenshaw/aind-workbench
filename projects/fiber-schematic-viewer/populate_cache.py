"""
Temporary script to pre-populate cache for all fiber photometry subjects.

Queries metadata for all subjects with 'fib' in modality, then fetches procedures
for each one to populate the cache. This avoids the ~30-40s delay for existing subjects.
"""

import argparse
import sys
import time
from pathlib import Path

from tqdm import tqdm

# Add parent to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app import get_procedures_for_subject, get_cache_path


def get_fiber_subjects():
    """Get all unique subject IDs with fiber photometry modality."""
    try:
        from aind_data_access_api.document_db import MetadataDbClient
        
        print("Querying metadata for fiber photometry subjects...")
        
        client = MetadataDbClient(
            host='api.allenneuraldynamics.org',
            database='metadata_index',
            collection='data_assets',
        )
        
        # Query for records with 'fib' in modality
        pipeline = [
            {
                "$match": {
                    "data_description.modality.abbreviation": {"$regex": "fib", "$options": "i"}
                }
            },
            {
                "$group": {
                    "_id": "$subject.subject_id",
                }
            },
            {
                "$sort": {"_id": -1}
            }
        ]
        
        results = client.aggregate_docdb_records(pipeline)
        subject_ids = [r['_id'] for r in results if r.get('_id')]
        
        print(f"Found {len(subject_ids)} unique subjects with fiber photometry data")
        return subject_ids
        
    except Exception as e:
        print(f"Error querying metadata: {e}")
        return []


def check_cache_status(subject_ids, cache_dir=".cache/procedures"):
    """Check cache status for all subject IDs without fetching."""
    total = len(subject_ids)
    cached = 0
    
    print(f"\nChecking cache status for {total} subjects...")
    print(f"Cache directory: {cache_dir}\n")
    
    for subject_id in tqdm(subject_ids, desc="Checking cache", unit="subject"):
        cache_path = get_cache_path(subject_id, cache_dir)
        if cache_path.exists():
            cached += 1
    
    print(f"\n{'='*60}")
    print(f"Cache Status Report")
    print(f"{'='*60}")
    print(f"Total subjects:     {total}")
    print(f"Already cached:     {cached} ({100*cached/total:.1f}%)")
    print(f"Not cached:         {total-cached} ({100*(total-cached)/total:.1f}%)")
    print(f"{'='*60}")


def populate_cache(subject_ids, cache_dir=".cache/procedures"):
    """Populate cache for all subject IDs."""
    total = len(subject_ids)
    cached = 0
    fetched = 0
    errors = 0
    
    print(f"\nPopulating cache for {total} subjects...")
    print(f"Cache directory: {cache_dir}\n")
    
    start_time = time.time()
    
    for subject_id in tqdm(subject_ids, desc="Populating cache", unit="subject"):
        try:
            result = get_procedures_for_subject(subject_id, cache_dir=cache_dir)
            
            if result:
                data, cache_info = result
                if cache_info['from_cache']:
                    cached += 1
                else:
                    fetched += 1
                    # Sleep briefly to avoid overwhelming metadata service
                    time.sleep(1)
            else:
                tqdm.write(f"Subject {subject_id}: no procedures found")
                errors += 1
                
        except Exception as e:
            tqdm.write(f"Subject {subject_id}: ERROR: {e}")
            errors += 1
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"Cache population complete!")
    print(f"{'='*60}")
    print(f"Total subjects:     {total}")
    print(f"Already cached:     {cached}")
    print(f"Newly fetched:      {fetched}")
    print(f"Errors/no data:     {errors}")
    print(f"Time elapsed:       {elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pre-populate cache for fiber photometry subjects"
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=".cache/procedures",
        help="Cache directory (default: .cache/procedures)"
    )
    parser.add_argument(
        "--query-only",
        action="store_true",
        help="Only query and report statistics without fetching data"
    )
    
    args = parser.parse_args()
    
    # Get all fiber photometry subjects
    subject_ids = get_fiber_subjects()
    
    if not subject_ids:
        print("No subjects found or error querying metadata")
        sys.exit(1)
    
    # Either check cache status or populate cache
    if args.query_only:
        check_cache_status(subject_ids, cache_dir=args.cache_dir)
    else:
        populate_cache(subject_ids, cache_dir=args.cache_dir)
