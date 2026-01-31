import pandas as pd
import re

# Read the CSV file
csv_path = 'DBTL_1_V2/plate1/transfer_instructions_plate1.csv'
df = pd.read_csv(csv_path)

print(f"Loaded {len(df)} rows from {csv_path}")
print(f"Columns: {list(df.columns)}")

# Get unique Source_Well values
unique_source_wells = df['Source_Well'].unique()
print(f"\nUnique Source_Well values: {unique_source_wells}")

# Sort Source_Well values: "none" first, then alphabetical
sorted_source_wells = sorted([sw for sw in unique_source_wells if sw != 'none'])
if 'none' in unique_source_wells:
    sorted_source_wells = ['none'] + sorted_source_wells

print(f"\nSorted Source_Well order: {sorted_source_wells}")

# Create custom sorting function for Dest_Well (column-first order)
def dest_well_sort_key(well_name):
    """
    Sort Dest_Well in column-first order: A1, B1, C1, D1, E1, F1, G1, H1, A2, B2, ...
    Returns a tuple (column_number, row_letter_index) for sorting
    """
    if pd.isna(well_name) or well_name == 'none':
        return (999, 999)  # Put None/none values at the end
    
    # Extract row letter and column number
    match = re.match(r'([A-H])(\d+)', str(well_name))
    if match:
        row_letter = match.group(1)
        column_num = int(match.group(2))
        # Convert row letter to index (A=0, B=1, ..., H=7)
        row_index = ord(row_letter) - ord('A')
        return (column_num, row_index)
    else:
        # If pattern doesn't match, put at end
        return (999, 999)

# Process each Source_Well
sorted_dataframes = []

for source_well in sorted_source_wells:
    # Filter dataframe for this Source_Well
    filtered_df = df[df['Source_Well'] == source_well].copy()
    
    # Sort by Dest_Well using custom sorting function
    filtered_df['_sort_key'] = filtered_df['Dest_Well'].apply(dest_well_sort_key)
    filtered_df = filtered_df.sort_values('_sort_key')
    filtered_df = filtered_df.drop('_sort_key', axis=1)
    
    print(f"\nSource_Well '{source_well}': {len(filtered_df)} rows")
    print(f"  First few Dest_Wells: {list(filtered_df['Dest_Well'].head(10))}")
    
    sorted_dataframes.append(filtered_df)

# Concatenate all sorted dataframes
final_df = pd.concat(sorted_dataframes, ignore_index=True)

# Save to new CSV file
output_path = 'DBTL_1_V2/plate1/transfer_instructions_plate1_rearranged.csv'
final_df.to_csv(output_path, index=False)

print(f"\n{'='*60}")
print(f"Final dataframe: {len(final_df)} rows")
print(f"Saved to: {output_path}")
print(f"{'='*60}")
