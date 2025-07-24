#!/usr/bin/env python3
"""
Script to create a summary CSV with just unique subject IDs and their counts.
"""

import csv
from collections import Counter

def create_unique_subjects_summary():
    """Create a summary CSV with unique subject IDs and their frequency."""
    
    # Read the original CSV
    subject_ids = []
    with open('subject_ids_from_json.csv', 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            subject_id = row['subject_id']
            # Skip errors and empty values
            if subject_id and not subject_id.startswith('ERROR') and subject_id != 'None':
                subject_ids.append(subject_id)
    
    # Count occurrences
    subject_counts = Counter(subject_ids)
    
    # Create summary CSV
    with open('unique_subject_ids.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['subject_id', 'file_count']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for subject_id, count in sorted(subject_counts.items()):
            writer.writerow({
                'subject_id': subject_id,
                'file_count': count
            })
    
    print(f"Created unique_subject_ids.csv with {len(subject_counts)} unique subject IDs")
    print(f"Total files with valid subject IDs: {sum(subject_counts.values())}")
    
    # Print the unique subject IDs
    print("\nUnique Subject IDs found:")
    for subject_id in sorted(subject_counts.keys()):
        print(f"  {subject_id} (appears in {subject_counts[subject_id]} files)")

if __name__ == "__main__":
    create_unique_subjects_summary()
