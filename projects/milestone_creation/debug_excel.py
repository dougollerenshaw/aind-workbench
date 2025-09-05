import pandas as pd

df = pd.read_excel("SciComp GoalsResourcing Summary.xlsx")

print("Row 2 (first goal) all fields:")
for i, val in enumerate(df.iloc[2]):
    if pd.notna(val) and str(val).strip():
        print(f"Column {i}: {repr(val)}")

print("\nRow 3 (second goal) all fields:")
for i, val in enumerate(df.iloc[3]):
    if pd.notna(val) and str(val).strip():
        print(f"Column {i}: {repr(val)}")
