import pandas as pd
import os

# Path to your CSV
csv_path = "asset_inventory.csv"
df = pd.read_csv(csv_path)

# Rename 'current_data_location' to 'vast_path'
df = df.rename(columns={"current_data_location": "vast_path"})


# Function to check if the dataset is on vast and log the actual path
def is_on_vast(row):
    subject_id = row["subject_id"]
    session_name = row["session_name"]
    base_path = "/Volumes/scratch/sueSu"

    # Get the actual case of the base path
    if not os.path.exists(base_path):
        return "", False

    # Get the actual case of the subject_id directory
    subject_path = os.path.join(base_path, subject_id)
    if not os.path.exists(subject_path):
        # Try case-insensitive search
        for d in os.listdir(base_path):
            if d.lower() == subject_id.lower():
                subject_path = os.path.join(base_path, d)
                break
        else:
            return "", False

    # Get the actual case of the session_name directory
    session_path = os.path.join(subject_path, session_name)
    if not os.path.exists(session_path):
        # Try case-insensitive search
        for d in os.listdir(subject_path):
            if d.lower() == session_name.lower():
                session_path = os.path.join(subject_path, d)
                break
        else:
            return "", False

    # If we get here, we found the path - log it and return the path from 'scratch' onwards
    print(f"Found: {session_path}")
    return session_path.replace("/Volumes/scratch", "scratch"), True


# Update the 'vast_path' and 'on_vast' columns
df[["vast_path", "on_vast"]] = pd.DataFrame(
    df.apply(is_on_vast, axis=1).tolist(), index=df.index
)

# Reorder columns to put 'on_vast' before 'vast_path'
cols = df.columns.tolist()
vast_path_idx = cols.index("vast_path")
cols.remove("on_vast")
cols.insert(vast_path_idx, "on_vast")
df = df[cols]

# Save the updated CSV
df.to_csv(csv_path, index=False)
print("CSV updated with 'vast_path' and 'on_vast' columns.")
