#!/usr/bin/env python3
"""
Script to walk through all JSON files in the workspace and extract subject IDs into a CSV file.
"""

import json
import os
import csv
from pathlib import Path


def find_subject_id(data, file_path=""):
    """
    Recursively search for subject_id in various possible locations within JSON data.
    
    Args:
        data: JSON data (dict, list, or other)
        file_path: Path to the file being processed (for debugging)
    
    Returns:
        subject_id if found, None otherwise
    """
    if isinstance(data, dict):
        # Direct subject_id keys
        if 'subject_id' in data:
            return data['subject_id']
        
        # Check nested data.subject_id (common in AIND schema)
        if 'data' in data and isinstance(data['data'], dict) and 'subject_id' in data['data']:
            return data['data']['subject_id']
        
        # Check acquisition.subject_id
        if 'acquisition' in data and isinstance(data['acquisition'], dict) and 'subject_id' in data['acquisition']:
            return data['acquisition']['subject_id']
        
        # Recursively search in all dictionary values
        for key, value in data.items():
            result = find_subject_id(value, file_path)
            if result is not None:
                return result
    
    elif isinstance(data, list):
        # Search in list items
        for item in data:
            result = find_subject_id(item, file_path)
            if result is not None:
                return result
    
    return None


def extract_subject_ids_from_json_files(root_dir):
    """
    Walk through all JSON files in the given directory and extract subject IDs.
    
    Args:
        root_dir: Root directory to search for JSON files
    
    Returns:
        List of dictionaries with file_path and subject_id
    """
    results = []
    root_path = Path(root_dir)
    
    # Find all JSON files
    json_files = list(root_path.rglob("*.json"))
    
    print(f"Found {len(json_files)} JSON files to process...")
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            subject_id = find_subject_id(data, str(json_file))
            
            results.append({
                'file_path': str(json_file.relative_to(root_path)),
                'absolute_path': str(json_file),
                'subject_id': subject_id
            })
            
            if subject_id:
                print(f"Found subject_id '{subject_id}' in: {json_file.name}")
            
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON in {json_file}: {e}")
            results.append({
                'file_path': str(json_file.relative_to(root_path)),
                'absolute_path': str(json_file),
                'subject_id': f"ERROR: {str(e)}"
            })
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            results.append({
                'file_path': str(json_file.relative_to(root_path)),
                'absolute_path': str(json_file),
                'subject_id': f"ERROR: {str(e)}"
            })
    
    return results


def save_to_csv(results, output_file):
    """
    Save the results to a CSV file.
    
    Args:
        results: List of dictionaries with file_path and subject_id
        output_file: Path to the output CSV file
    """
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['file_path', 'subject_id', 'absolute_path']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    print(f"Results saved to: {output_file}")


def main():
    """Main function to orchestrate the subject ID extraction."""
    # Use current directory as root
    root_dir = os.getcwd()
    output_file = "subject_ids_from_json.csv"
    
    print(f"Searching for JSON files in: {root_dir}")
    print("-" * 50)
    
    # Extract subject IDs
    results = extract_subject_ids_from_json_files(root_dir)
    
    # Save to CSV
    save_to_csv(results, output_file)
    
    # Print summary
    total_files = len(results)
    files_with_subject_ids = len([r for r in results if r['subject_id'] and not str(r['subject_id']).startswith('ERROR')])
    unique_subject_ids = len(set([r['subject_id'] for r in results if r['subject_id'] and not str(r['subject_id']).startswith('ERROR')]))
    
    print("-" * 50)
    print(f"Summary:")
    print(f"  Total JSON files processed: {total_files}")
    print(f"  Files with subject IDs: {files_with_subject_ids}")
    print(f"  Unique subject IDs found: {unique_subject_ids}")
    print(f"  Output file: {output_file}")


if __name__ == "__main__":
    main()
