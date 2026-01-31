"""
Save updated stock plate dataframes to new CSV files
This script saves the updated df_stock_plate_high and df_stock_plate_low 
to new CSV files with '_updated' suffix.
"""

import pandas as pd

# Load the current stock plate files
stock_plate_high_file = 'DBTL_1_V2/plate1/24-well_stock_plate_high.csv'
stock_plate_low_file = 'DBTL_1_V2/plate1/24-well_stock_plate_low.csv'

# Read the dataframes
df_stock_plate_high = pd.read_csv(stock_plate_high_file)
df_stock_plate_low = pd.read_csv(stock_plate_low_file)

# Save high concentration plate to new file
output_high_file = 'DBTL_1_V2/plate1/24-well_stock_plate_high_updated.csv'
df_stock_plate_high.to_csv(output_high_file, index=False)
print(f"Updated high stock plate saved to: {output_high_file}")
print(f"  Number of wells: {len(df_stock_plate_high)}")
print(f"  Columns: {list(df_stock_plate_high.columns)}")

# Save low concentration plate to new file
output_low_file = 'DBTL_1_V2/plate1/24-well_stock_plate_low_updated.csv'
df_stock_plate_low.to_csv(output_low_file, index=False)
print(f"\nUpdated low stock plate saved to: {output_low_file}")
print(f"  Number of wells: {len(df_stock_plate_low)}")
print(f"  Columns: {list(df_stock_plate_low.columns)}")

print("\n" + "="*60)
print("Files saved successfully!")
print("="*60)
