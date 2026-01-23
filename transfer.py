#!/usr/bin/env python
# coding: utf-8

"""
================================================================================
LIQUID HANDLER TRANSFER FILE GENERATOR
================================================================================

PURPOSE:
--------
This script generates transfer instructions for automated liquid handlers.
It calculates how much volume of each stock solution needs to be transferred
to each destination well to achieve target concentrations.

WHAT IT DOES:
-------------
1. Reads input files:
   - Stock concentrations (what concentrations are available)
   - Stock plate layouts (where stocks are located on plates)
   - Target concentrations (what we want in each destination well)

2. Calculates transfer volumes:
   - For each destination well and each component, calculates how much volume
     to transfer from stock solutions
   - Chooses between high/low concentration stocks based on minimum volume requirements
   - Adds water to fill each well to the target total volume

3. Generates transfer instructions:
   - Creates a CSV file with transfer commands for the liquid handler
   - Each row = one transfer: source plate/well → destination plate/well + volume
   - Splits large transfers that exceed maximum tip volume

4. Validates results:
   - Checks that volumes sum correctly
   - Verifies concentrations match targets
   - Warns about source well depletion

INPUT FILES:
------------
- stock_concentrations.csv: List of all components and their stock concentrations
- 24-well_stock_plate_high.csv: Layout of high-concentration stock plate (plate s1)
- 24-well_stock_plate_low.csv: Layout of low-concentration stock plate (plate s4)
- target_concentrations.csv: Target concentration for each component in each well

OUTPUT FILE:
------------
- transfer_instructions.csv: Transfer commands for liquid handler
  Columns: Source_Plate, Source_Well, Dest_Plate, Dest_Well, Transfer_Vol

================================================================================
"""

# %%
# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Import required libraries for data manipulation and calculations

import pandas as pd      # For reading CSV files and working with DataFrames (tables)
import numpy as np       # For numerical calculations and comparisons
import os                # For file path operations
from collections import defaultdict  # For tracking source well usage


# %%
# =============================================================================
# SECTION 2: USER PARAMETERS
# =============================================================================
# This section defines all the configuration settings you can adjust.
# These parameters control how the script behaves and what files it uses.

import math  # For ceiling function (rounding up) when splitting large transfers

# Dictionary containing all user-configurable parameters
user_params = {
    # ========================================================================
    # INPUT FILES
    # ========================================================================
    # Paths to CSV files containing input data
    'stock_conc_file': 'data/stock_concentrations.csv',           # List of components and their concentrations
    'stock_plate_high_file': 'data/24-well_stock_plate_high.csv', # High-concentration stock plate layout
    'stock_plate_low_file': 'data/24-well_stock_plate_low.csv',   # Low-concentration stock plate layout
    'target_conc_file': 'data/target_concentrations.csv',         # Target concentrations for each well

    # ========================================================================
    # LIQUID HANDLING PARAMETERS
    # ========================================================================
    # These parameters define the physical constraints of the liquid handler
    'well_volume': 1500,            # Total volume (µL) in each destination well after all transfers
    'source_well_volume': 9000,    # Maximum usable volume (µL) in each source well
    'dead_volume': 100,            # Volume (µL) that cannot be aspirated from source wells
                                   #   (liquid at bottom that pipette can't reach)
    'min_transfer_volume': 5.0,    # Minimum accurate transfer volume (µL)
                                   #   Transfers smaller than this may be inaccurate
    'max_tip_volume': 200.0,       # Maximum tip volume (µL)
                                   #   Transfers exceeding this will be split into multiple cycles
    'culture_factor': 100,          # Culture dilution factor
                                   #   100x means: 15µL culture in 1500µL total = 1/100 dilution
    'epsilon': 1e-6,               # Floating point comparison tolerance
                                   #   Used to handle rounding errors when comparing floats

    # ========================================================================
    # PLATE FORMAT
    # ========================================================================
    # Configuration for destination plate format
    'wells_per_plate': 48,         # Number of wells per destination plate (48 or 96)
    'plate_format': '48-well',      # Plate format: '48-well' (A1-F8) or '96-well' (A1-H12)

    # ========================================================================
    # CULTURE HANDLING
    # ========================================================================
    # Controls whether culture is added to all wells or only specific ones
    'add_culture_to_all_wells': True,  # If True: add culture to all wells
                                       # If False: only add where target_conc['Culture'] > 0

    # ========================================================================
    # WATER SOURCE CONFIGURATION
    # ========================================================================
    # Where to get water from (used to fill wells to target volume)
    'water_source': {
        'plate': 's_water',  # Plate name (e.g., 's_water') or 'reservoir_1', 'trough_1', etc.
        'well': 'A1',        # Well name (None for reservoir/trough - unlimited source)
        'type': 'plate'      # Source type: 'plate', 'reservoir', or 'trough'
    },

    # ========================================================================
    # OUTPUT
    # ========================================================================
    # Where to save the final transfer instructions
    'output_file': 'data/transfer_instructions.csv'
}

# Print loaded parameters for verification
print("User parameters loaded:")
for key, value in user_params.items():
    if key not in ['water_source']:  # Skip complex objects (dictionaries)
        print(f"  {key}: {value}")


# %%
# =============================================================================
# SECTION 3: LOAD INPUT DATA
# =============================================================================
# This section reads all the input CSV files and loads them into pandas DataFrames.
# DataFrames are like Excel spreadsheets - tables with rows and columns.

# -----------------------------------------------------------------------------
# Load stock concentrations file
# -----------------------------------------------------------------------------
# This file contains a list of all components and their stock concentrations.
# Format: Component (index), Concentration[mM] (column)
df_stock = pd.read_csv(user_params['stock_conc_file'])
df_stock = df_stock.set_index('Component')  # Use Component column as row index
                                             # Makes it easy to look up by component name

# -----------------------------------------------------------------------------
# Load stock plate layout files
# -----------------------------------------------------------------------------
# These files tell us WHERE each component is located on the stock plates.
# Format: Component, Well, Concentration[mM]
df_stock_plate_high = pd.read_csv(user_params['stock_plate_high_file'])  # High-concentration plate (s1)
df_stock_plate_low = pd.read_csv(user_params['stock_plate_low_file'])    # Low-concentration plate (s4)

# -----------------------------------------------------------------------------
# Load target concentrations file
# -----------------------------------------------------------------------------
# This file specifies what concentration of each component we want in each destination well.
# Format: Well (index), Component1, Component2, ... (columns)
# Each cell contains the target concentration (mM) for that component in that well
df_target_conc = pd.read_csv(user_params['target_conc_file'], index_col=0)  # First column is well names

# Print summary of loaded data
print("Data loaded successfully:")
print(f"  Stock components: {len(df_stock)}")  # Number of different components
print(f"  High plate wells: {len(df_stock_plate_high)}")  # Number of wells in high plate
print(f"  Low plate wells: {len(df_stock_plate_low)}")    # Number of wells in low plate
print(f"  Target wells: {len(df_target_conc)}")            # Number of destination wells
print(f"  Target components: {len(df_target_conc.columns)}")  # Number of components to add


# %%
# =============================================================================
# SECTION 4: BUILD STOCK LOOKUP DICTIONARY
# =============================================================================
# This section creates a lookup table that maps each component to its source location.
# The lookup tells us: for component X, where is it located on which plate?

# Structure: stock_lookup[component_name] = {
#     'high': {'plate': 's1', 'well': 'A1', 'conc': 100.0} or None,
#     'low': {'plate': 's4', 'well': 'B2', 'conc': 10.0} or None
# }

stock_lookup = {}

# -----------------------------------------------------------------------------
# Step 1: Initialize all components from stock concentrations file
# -----------------------------------------------------------------------------
# Create an entry for each component, initially with no source locations
for comp in df_stock.index:
    stock_lookup[comp] = {'high': None, 'low': None}  # None = no source available

# -----------------------------------------------------------------------------
# Step 2: Populate HIGH stock sources
# -----------------------------------------------------------------------------
# Fill in the 'high' entry for each component that exists on the high plate
for _, row in df_stock_plate_high.iterrows():
    comp = row['Component']  # Component name (e.g., 'Glucose')
    
    # If component not in lookup yet, add it
    if comp not in stock_lookup:
        stock_lookup[comp] = {'high': None, 'low': None}

    # Store the location and concentration of this high stock
    stock_lookup[comp]['high'] = {
        'plate': 's1',                    # High concentration plate is always 's1'
        'well': row['Well'],              # Well location (e.g., 'A1', 'B3')
        'conc': row['Concentration[mM]']  # Stock concentration in mM
    }

# -----------------------------------------------------------------------------
# Step 3: Populate LOW stock sources
# -----------------------------------------------------------------------------
# Fill in the 'low' entry for each component that exists on the low plate
for _, row in df_stock_plate_low.iterrows():
    comp = row['Component']
    
    # If component not in lookup yet, add it
    if comp not in stock_lookup:
        stock_lookup[comp] = {'high': None, 'low': None}

    # Store the location and concentration of this low stock
    stock_lookup[comp]['low'] = {
        'plate': 's4',                    # Low concentration plate is always 's4'
        'well': row['Well'],
        'conc': row['Concentration[mM]']
    }

# Print summary
print(f"\nStock lookup created: {len(stock_lookup)} components")
print(f"  Components with HIGH stock: {sum(1 for c in stock_lookup.values() if c['high'] is not None)}")
print(f"  Components with LOW stock: {sum(1 for c in stock_lookup.values() if c['low'] is not None)}")

# -----------------------------------------------------------------------------
# Step 4: Special handling for Culture
# -----------------------------------------------------------------------------
# Culture is handled differently - it uses volume ratio, not concentration.
# If Culture isn't in the stock plates, add it with a default source.
if 'Culture' not in stock_lookup:
    stock_lookup['Culture'] = {
        'high': {
            'plate': 's1',
            'well': 'A1',  # Default source for culture
            'conc': 1.0    # Dummy concentration (Culture uses volume ratio, not concentration)
        },
        'low': None
    }
    print(f"  Added Culture to stock_lookup with default source s1:A1")


# %%
# =============================================================================
# SECTION 5: VALIDATION CHECKS
# =============================================================================
# Before calculating transfers, we check that the input data is valid.
# This helps catch errors early and provides helpful error messages.

errors = []        # Critical errors that will prevent the script from working
warnings_list = [] # Warnings about potential issues (script can continue)

# -----------------------------------------------------------------------------
# Check 1: All components in target exist in stock plates
# -----------------------------------------------------------------------------
# We can't create a solution if we don't have the stock!
missing_components = []
for comp in df_target_conc.columns:
    # Check if component exists in stock lookup
    if comp not in stock_lookup:
        missing_components.append(comp)
    else:
        # Check if component has at least one stock source (high or low)
        has_source = (stock_lookup[comp]['high'] is not None or 
                     stock_lookup[comp]['low'] is not None)
        if not has_source:
            missing_components.append(comp)

if missing_components:
    errors.append(f"Components in target but not in stock plates: {missing_components}")

# -----------------------------------------------------------------------------
# Check 2: Well formats are valid
# -----------------------------------------------------------------------------
# Wells should be in format: letter + number (e.g., 'A1', 'B12', 'H8')
def is_valid_well(well):
    """Check if well format is valid (e.g., A1, B12)."""
    if pd.isna(well):  # Check for NaN/None
        return False
    well_str = str(well).strip()  # Convert to string and remove whitespace
    if len(well_str) < 2:  # Must have at least letter + number
        return False
    # First character should be a letter, rest should be digits
    return well_str[0].isalpha() and well_str[1:].isdigit()

# Check well formats in both stock plates
for plate_df, plate_name in [(df_stock_plate_high, 'high'), 
                              (df_stock_plate_low, 'low')]:
    invalid_wells = plate_df[~plate_df['Well'].apply(is_valid_well)]['Well'].tolist()
    if invalid_wells:
        warnings_list.append(f"Invalid well formats in {plate_name} plate: {invalid_wells}")

# -----------------------------------------------------------------------------
# Check 3: Concentrations are positive
# -----------------------------------------------------------------------------
# Negative concentrations don't make physical sense
for comp in df_target_conc.columns:
    negative = df_target_conc[comp][df_target_conc[comp] < 0]
    if len(negative) > 0:
        warnings_list.append(f"Negative concentrations for {comp} in wells: {negative.index.tolist()}")

# -----------------------------------------------------------------------------
# Check 4: Stock concentration > target concentration (dilution possible)
# -----------------------------------------------------------------------------
# To dilute a stock, the stock must be more concentrated than the target.
# If target >= stock, we can't achieve it by dilution.
for comp in df_target_conc.columns:
    if comp in stock_lookup:
        max_target = df_target_conc[comp].max()  # Highest target concentration for this component
        
        # Find the maximum stock concentration available (from high or low)
        max_stock = 0
        for stock_type in ['high', 'low']:
            if stock_lookup[comp][stock_type] is not None:
                conc = stock_lookup[comp][stock_type]['conc']
                if conc is not None and conc > max_stock:
                    max_stock = conc

        # If target is >= stock, we can't dilute to achieve it
        if max_stock > 0 and max_target >= max_stock:
            errors.append(f"Component {comp}: max target ({max_target}) >= max stock ({max_stock}) - cannot dilute")

# -----------------------------------------------------------------------------
# Print validation results
# -----------------------------------------------------------------------------
print("Validation complete:")
if errors:
    print(f"  ERRORS ({len(errors)}):")
    for err in errors:
        print(f"    - {err}")
else:
    print("  No errors found")

if warnings_list:
    print(f"  WARNINGS ({len(warnings_list)}):")
    for warn in warnings_list[:5]:  # Show first 5 warnings
        print(f"    - {warn}")
    if len(warnings_list) > 5:
        print(f"    ... and {len(warnings_list) - 5} more warnings")
else:
    print("  No warnings")


# %%
# =============================================================================
# SECTION 6: CORE ALGORITHM - find_volumes_bulk FUNCTION
# =============================================================================
# This is the heart of the script! This function calculates how much volume
# of each component needs to be transferred to each destination well.

def find_volumes_bulk(df_stock, df_target_conc, well_volume, min_tip_volume, culture_ratio, stock_lookup, 
                      epsilon=1e-6, add_culture_to_all=True):
    """
    Calculate transfer volumes for all wells and components.
    
    HOW IT WORKS:
    For each well and each component:
    1. Get target concentration
    2. Find appropriate stock (high or low concentration)
    3. Calculate: transfer_vol = (target_conc × well_volume) / stock_conc
    4. Check if volume meets minimum requirement
    5. Add water to fill well to target volume
    
    Args:
        df_stock: DataFrame with stock concentrations
        df_target_conc: DataFrame with target concentrations (Well × Component)
        well_volume: Total volume (µL) in each destination well
        min_tip_volume: Minimum accurate transfer volume (µL)
        culture_ratio: Culture dilution factor (e.g., 100 for 100x dilution)
        stock_lookup: Dictionary mapping components to their source locations
        epsilon: Floating point comparison tolerance
        add_culture_to_all: If False, only add culture where target_conc['Culture'] > 0
    
    Returns:
        df_volumes: DataFrame (Well × Component) with transfer volumes in µL
        df_conc_level: DataFrame (Well × Component) with stock level used ('high', 'low', 'fresh')
        errors: List of error messages
        warnings_list: List of warning messages
    """
    
    # Initialize output DataFrames
    # These will store the calculated volumes and which stock was used
    df_volumes = pd.DataFrame(index=df_target_conc.index, columns=df_target_conc.columns)
    df_conc_level = pd.DataFrame(index=df_target_conc.index, columns=df_target_conc.columns)

    errors = []
    warnings_list = []

    # -------------------------------------------------------------------------
    # Process each well and each component
    # -------------------------------------------------------------------------
    for well in df_target_conc.index:  # Loop through each destination well
        for comp in df_target_conc.columns:  # Loop through each component
            target_conc = df_target_conc.loc[well, comp]  # Get target concentration

            # Skip if zero, None, or NaN (using epsilon for floating point comparison)
            # We don't need to transfer anything if target is zero
            if pd.isna(target_conc) or abs(target_conc) < epsilon:
                df_volumes.loc[well, comp] = 0.0
                df_conc_level.loc[well, comp] = None
                if pd.isna(target_conc):
                    warnings_list.append(f"Well {well}, {comp}: NaN concentration, skipping")
                continue

            # Check if component exists in stock lookup
            if comp not in stock_lookup:
                errors.append(f"Well {well}, {comp}: Component not in stock lookup")
                df_volumes.loc[well, comp] = 0.0
                df_conc_level.loc[well, comp] = None
                continue

            stocks = stock_lookup[comp]  # Get available stocks for this component
            transfer_vol = None  # Will store calculated transfer volume
            stock_level = None   # Will store which stock we used ('high' or 'low')

            # -----------------------------------------------------------------
            # Try stock types in priority order: high → low
            # -----------------------------------------------------------------
            # We prefer high concentration stocks because they require smaller volumes
            # (more accurate for small volumes, less pipetting)
            for stock_type in ['high', 'low']:
                stock_info = stocks[stock_type]

                # Skip if this stock type doesn't exist
                if stock_info is None:
                    continue

                # -----------------------------------------------------------------
                # Special handling for Culture (uses volume ratio, not concentration)
                # -----------------------------------------------------------------
                # Culture is added as a fixed volume ratio, not based on concentration.
                # Example: 100x dilution = 15µL culture in 1500µL total
                if comp == 'Culture':
                    transfer_vol = well_volume / culture_ratio  # Calculate volume based on ratio
                    stock_level = 'fresh'  # Mark as 'fresh' (special handling)
                    break  # Found what we need, stop looking

                # -----------------------------------------------------------------
                # Regular components: calculate transfer volume from concentration
                # -----------------------------------------------------------------
                # Get stock concentration
                stock_conc = stock_info.get('conc')
                if stock_conc is None:
                    continue

                # Handle "300x" format (shouldn't happen after stock lookup, but just in case)
                # Some files might have concentrations like "300x" instead of a number
                if isinstance(stock_conc, str) and 'x' in str(stock_conc).lower():
                    try:
                        factor = float(str(stock_conc).replace('x', '').replace('X', '').strip())
                        stock_conc = factor
                    except (ValueError, TypeError):
                        continue  # Skip this stock if we can't parse it

                # -----------------------------------------------------------------
                # Calculate transfer volume using dilution formula
                # -----------------------------------------------------------------
                # Formula: C1 × V1 = C2 × V2
                #   C1 = stock concentration, V1 = transfer volume (unknown)
                #   C2 = target concentration, V2 = well volume (known)
                # Solving: V1 = (C2 × V2) / C1
                transfer_vol = (target_conc * well_volume) / stock_conc

                # -----------------------------------------------------------------
                # Check if volume meets minimum requirement
                # -----------------------------------------------------------------
                # If transfer volume is too small, it may be inaccurate.
                # We check if it's >= min_tip_volume (using epsilon for floating point comparison)
                if transfer_vol >= min_tip_volume - epsilon:
                    stock_level = stock_type  # This stock works!
                    break  # Found a valid stock, stop looking

            # -----------------------------------------------------------------
            # Store the result
            # -----------------------------------------------------------------
            if transfer_vol is not None and stock_level is not None:
                # We found a valid stock - store the volume and stock level
                df_volumes.loc[well, comp] = round(transfer_vol, 2)  # Round to 2 decimal places
                df_conc_level.loc[well, comp] = stock_level
            else:
                # No valid stock found - volume would be too small
                # Note this but don't error (allows small concentrations to be skipped)
                warnings_list.append(f"Well {well}, {comp}: Cannot transfer (all stocks require < {min_tip_volume} µL)")
                df_volumes.loc[well, comp] = 0.0
                df_conc_level.loc[well, comp] = None

    # -------------------------------------------------------------------------
    # Add Culture to wells (configurable)
    # -------------------------------------------------------------------------
    # Culture is handled separately because it uses volume ratio, not concentration
    if 'Culture' not in df_volumes.columns:
        if add_culture_to_all:
            # Add culture to all wells
            culture_vol = well_volume / culture_ratio  # Calculate volume based on ratio
            df_volumes['Culture'] = round(culture_vol, 2)
            df_conc_level['Culture'] = 'high'  # Culture from high plate
        else:
            # Only add culture where target_conc has Culture > 0
            if 'Culture' in df_target_conc.columns:
                for well in df_target_conc.index:
                    culture_target = df_target_conc.loc[well, 'Culture']
                    if not pd.isna(culture_target) and culture_target > epsilon:
                        culture_vol = well_volume / culture_ratio
                        df_volumes.loc[well, 'Culture'] = round(culture_vol, 2)
                        df_conc_level.loc[well, 'Culture'] = 'high'
                    else:
                        df_volumes.loc[well, 'Culture'] = 0.0
                        df_conc_level.loc[well, 'Culture'] = None
            else:
                # No Culture column in target, don't add
                pass

    # -------------------------------------------------------------------------
    # Calculate water volume for each well
    # -------------------------------------------------------------------------
    # Water fills the remaining volume to reach the target well_volume
    # Formula: water_vol = well_volume - sum(all_component_volumes)
    df_volumes['Water'] = 0.0
    for well in df_volumes.index:
        # Sum all component volumes (excluding Water itself)
        total_vol = df_volumes.loc[well, df_volumes.columns != 'Water'].sum()
        water_vol = well_volume - total_vol

        # Use epsilon for floating point comparison
        if water_vol < -epsilon:
            # Error: total volume exceeds well capacity (shouldn't happen)
            errors.append(f"Well {well}: Total volume {total_vol:.2f} exceeds {well_volume} µL")
            water_vol = 0.0
        elif abs(water_vol) < epsilon:
            water_vol = 0.0  # Snap to zero if very small (rounding error)
        elif water_vol > 0 and water_vol < min_tip_volume - epsilon:
            # Warning: water volume is very small (may be inaccurate)
            warnings_list.append(f"Well {well}: Water volume {water_vol:.2f} < {min_tip_volume} µL (may be inaccurate)")

        df_volumes.loc[well, 'Water'] = round(water_vol, 2)

    return df_volumes, df_conc_level, errors, warnings_list

print("find_volumes_bulk function defined")


# %%
# =============================================================================
# SECTION 7: RUN VOLUME CALCULATIONS
# =============================================================================
# Execute the find_volumes_bulk function to calculate all transfer volumes.

df_volumes, df_conc_level, calc_errors, calc_warnings = find_volumes_bulk(
    df_stock=df_stock,
    df_target_conc=df_target_conc,
    well_volume=user_params['well_volume'],
    min_tip_volume=user_params['min_transfer_volume'],
    culture_ratio=user_params['culture_factor'],
    stock_lookup=stock_lookup,
    epsilon=user_params['epsilon'],
    add_culture_to_all=user_params['add_culture_to_all_wells']
)

print("Volume calculations complete!")
print(f"\nVolumes dataframe shape: {df_volumes.shape}")  # (number of wells, number of components)
print(f"Conc level dataframe shape: {df_conc_level.shape}")

# Print any errors or warnings from the calculation
if calc_errors:
    print(f"\nCalculation ERRORS ({len(calc_errors)}):")
    for err in calc_errors[:10]:  # Show first 10
        print(f"  - {err}")
    if len(calc_errors) > 10:
        print(f"  ... and {len(calc_errors) - 10} more errors")

if calc_warnings:
    print(f"\nCalculation WARNINGS ({len(calc_warnings)}):")
    for warn in calc_warnings[:10]:  # Show first 10
        print(f"  - {warn}")
    if len(calc_warnings) > 10:
        print(f"  ... and {len(calc_warnings) - 10} more warnings")

# Show sample results
print("\nSample volumes (first well, first 5 components):")
print(df_volumes.iloc[0, :5])
print("\nSample conc levels:")
print(df_conc_level.iloc[0, :5])


# %%
# =============================================================================
# SECTION 8: WELL REMAPPING FOR DIFFERENT PLATE FORMATS
# =============================================================================
# This section handles different plate formats (48-well vs 96-well).
# It remaps well IDs if needed and assigns destination wells to plates.

# -----------------------------------------------------------------------------
# Function: remap_well_for_plate
# -----------------------------------------------------------------------------
def remap_well_for_plate(well, plate_format='48-well'):
    """
    Remap well IDs for different plate formats.
    
    Converts 96-well format (A1-H12) to 48-well format (A1-F8) if needed.
    
    Plate formats:
    - 48-well: 6 rows (A-F) × 8 columns (1-8) = 48 wells
    - 96-well: 8 rows (A-H) × 12 columns (1-12) = 96 wells
    
    Args:
        well: Well ID (e.g., 'A1', 'H12')
        plate_format: '48-well' or '96-well'
    
    Returns:
        Remapped well ID or original if no remapping needed
    """
    if pd.isna(well):
        return None

    well_str = str(well).strip().upper()  # Convert to uppercase string
    if len(well_str) < 2:
        return well_str

    row = well_str[0]      # Extract row letter (A, B, C, ...)
    col = int(well_str[1:])  # Extract column number (1, 2, 3, ...)

    # If 48-well format, validate well exists
    if plate_format == '48-well':
        # 48-well: 6 rows (A-F) × 8 columns (1-8)
        max_row = 'F'
        max_col = 8

        # If well is beyond 48-well format, remap or error
        if row > max_row or col > max_col:
            # Try to remap: G1-H12 -> F1-F8 (last row)
            if row > max_row:
                row = max_row
            if col > max_col:
                col = max_col
            return f"{row}{col}"

    # 96-well format: 8 rows (A-H) × 12 columns (1-12) - no remapping needed
    return well_str


# -----------------------------------------------------------------------------
# Function: assign_dest_plates
# -----------------------------------------------------------------------------
def assign_dest_plates(wells, wells_per_plate=48):
    """
    Assign destination wells to plates.
    
    This function splits wells across multiple destination plates.
    For example, if you have 100 wells and wells_per_plate=48:
    - Wells 1-48 → dest_1
    - Wells 49-96 → dest_2
    - Wells 97-100 → dest_3
    
    Args:
        wells: List of well IDs
        wells_per_plate: Number of wells per plate (48 or 96)
    
    Returns:
        Dictionary mapping well → plate name (e.g., {'A1': 'dest_1', 'A2': 'dest_1', ...})
    """
    plate_num = 1
    well_count = 0
    assignments = {}

    for well in wells:
        # If we've filled a plate, move to the next one
        if well_count >= wells_per_plate:
            plate_num += 1
            well_count = 0

        dest_plate = f"dest_{plate_num}"  # Create plate name (e.g., 'dest_1', 'dest_2')
        assignments[well] = dest_plate
        well_count += 1

    return assignments

# -----------------------------------------------------------------------------
# Assign destination plates
# -----------------------------------------------------------------------------
# Assign each destination well to a plate
dest_plate_assignments = assign_dest_plates(
    df_target_conc.index,  # List of all destination well IDs
    wells_per_plate=user_params['wells_per_plate']
)

# Remap wells if needed (for 48-well format)
plate_format = user_params.get('plate_format', '48-well')
if plate_format == '48-well':
    # Remap destination wells to 48-well format
    remapped_assignments = {}
    for well, plate in dest_plate_assignments.items():
        remapped_well = remap_well_for_plate(well, plate_format)
        remapped_assignments[remapped_well] = plate
    dest_plate_assignments = remapped_assignments

print(f"Assigned {len(dest_plate_assignments)} wells to destination plates")
print(f"Number of destination plates: {max([int(p.split('_')[1]) for p in dest_plate_assignments.values()])}")


# %%
# =============================================================================
# SECTION 9: BUILD TRANSFER RECORDS
# =============================================================================
# This section converts the calculated volumes into transfer instructions.
# Each transfer record tells the liquid handler: move X µL from source to destination.

transfers = []  # List to store all transfer records
source_usage = defaultdict(float)  # Track cumulative volume usage: {(plate, well): volume}
                                     # Used to check if source wells will be depleted
transfer_errors = []
transfer_warnings = []

# -----------------------------------------------------------------------------
# Helper function: get_source_well
# -----------------------------------------------------------------------------
def get_source_well(comp, stock_level, stock_lookup, df_stock_plate_high, df_stock_plate_low):
    """
    Get source plate and well for a component based on stock level.
    
    Args:
        comp: Component name
        stock_level: 'high', 'low', or 'fresh' (for Culture)
        stock_lookup: Dictionary mapping components to source locations
    
    Returns:
        (source_plate, source_well) tuple, or (None, None) if not found
    """
    if comp not in stock_lookup:
        return None, None

    stocks = stock_lookup[comp]

    # Special handling for Culture (from high plate)
    if comp == 'Culture':
        if stocks.get('high') is not None:
            return stocks['high']['plate'], stocks['high']['well']
        return 's1', 'A1'  # Default (high plate)

    # Regular components: use stock_level to determine plate
    stock_info = stocks.get(stock_level)
    if stock_info is not None:
        return stock_info['plate'], stock_info['well']

    return None, None

# -----------------------------------------------------------------------------
# Process all wells and components to create transfer records
# -----------------------------------------------------------------------------
for dest_well in df_volumes.index:  # Loop through each destination well
    dest_plate = dest_plate_assignments[dest_well]  # Get which plate this well is on

    # Process each component (excluding Water initially - handled separately)
    for comp in df_volumes.columns:
        if comp == 'Water':
            continue  # Handle water separately below

        transfer_vol = df_volumes.loc[dest_well, comp]  # Get calculated transfer volume
        stock_level = df_conc_level.loc[dest_well, comp]  # Get which stock was used

        # Skip if no transfer needed
        if transfer_vol == 0 or pd.isna(transfer_vol) or stock_level is None:
            continue

        # Get source plate and well for this component
        source_plate, source_well = get_source_well(
            comp, stock_level, stock_lookup,
            df_stock_plate_high, df_stock_plate_low
        )

        if source_plate is None or source_well is None:
            transfer_errors.append(f"Well {dest_well}, {comp}: Could not find source well")
            continue

        # Track source well usage (for depletion checking)
        key = (source_plate, source_well)
        source_usage[key] += transfer_vol

        # ---------------------------------------------------------------------
        # Create transfer record(s)
        # ---------------------------------------------------------------------
        # If transfer exceeds max tip volume, split into multiple cycles
        # Example: 250 µL transfer with max_tip_volume=200 → 2 cycles of 125 µL each
        max_tip_vol = user_params['max_tip_volume']
        if transfer_vol > max_tip_vol:
            # Split into multiple cycles
            num_cycles = math.ceil(transfer_vol / max_tip_vol)  # Round up
            vol_per_cycle = transfer_vol / num_cycles  # Divide volume evenly
            
            # Create one transfer record for each cycle
            for cycle in range(num_cycles):
                transfers.append({
                    'Source_Plate': source_plate,
                    'Source_Well': source_well,
                    'Dest_Plate': dest_plate,
                    'Dest_Well': dest_well,
                    'Transfer_Vol': round(vol_per_cycle, 2),
                    'Component': comp  # Keep for reference, will be removed in final output
                })
                source_usage[(source_plate, source_well)] += vol_per_cycle
        else:
            # Single transfer (within max tip volume)
            transfers.append({
                'Source_Plate': source_plate,
                'Source_Well': source_well,
                'Dest_Plate': dest_plate,
                'Dest_Well': dest_well,
                'Transfer_Vol': transfer_vol,
                'Component': comp  # Keep for reference, will be removed in final output
            })

    # -------------------------------------------------------------------------
    # Add Water transfer (from configured water source)
    # -------------------------------------------------------------------------
    water_vol = df_volumes.loc[dest_well, 'Water']
    if water_vol > user_params['epsilon']:  # Only if water volume is significant
        water_source = user_params['water_source']
        water_plate = water_source['plate']
        water_well = water_source.get('well', 'A1')  # Default if None

        # Check if water source is unlimited (reservoir/trough)
        if water_source.get('type') in ['reservoir', 'trough']:
            # No depletion tracking for unlimited sources
            pass

        # Split if exceeds max tip volume (same as other components)
        max_tip_vol = user_params['max_tip_volume']
        if water_vol > max_tip_vol:
            num_cycles = math.ceil(water_vol / max_tip_vol)
            vol_per_cycle = water_vol / num_cycles
            for cycle in range(num_cycles):
                transfers.append({
                    'Source_Plate': water_plate,
                    'Source_Well': water_well,
                    'Dest_Plate': dest_plate,
                    'Dest_Well': dest_well,
                    'Transfer_Vol': round(vol_per_cycle, 2),
                    'Component': 'Water'
                })
        else:
            transfers.append({
                'Source_Plate': water_plate,
                'Source_Well': water_well,
                'Dest_Plate': dest_plate,
                'Dest_Well': dest_well,
                'Transfer_Vol': round(water_vol, 2),
                'Component': 'Water'
            })

print(f"Built {len(transfers)} transfer records")
if transfer_errors:
    print(f"Transfer errors: {len(transfer_errors)}")
    for err in transfer_errors[:5]:
        print(f"  - {err}")


# %%
# =============================================================================
# SECTION 10: CHECK SOURCE WELL DEPLETION
# =============================================================================
# This section checks if any source wells will run out of liquid.
# If a source well is used too much, it may be depleted before all transfers complete.

# Calculate usable volume (total volume minus dead volume)
usable_vol = user_params['source_well_volume'] - user_params['dead_volume']

depletion_warnings = []
# Check each source well
for (plate, well), total_vol in source_usage.items():
    if total_vol > usable_vol:
        # This source well will be depleted!
        depletion_warnings.append(
            f"Source {plate}:{well} depleted: {total_vol:.1f} µL needed, "
            f"usable: {usable_vol:.1f} µL"
        )

if depletion_warnings:
    print(f"Source depletion WARNINGS ({len(depletion_warnings)}):")
    for warn in depletion_warnings[:10]:  # Show first 10
        print(f"  - {warn}")
    if len(depletion_warnings) > 10:
        print(f"  ... and {len(depletion_warnings) - 10} more warnings")
else:
    print("No source well depletion issues detected")


# %%
# =============================================================================
# SECTION 11: CREATE OUTPUT DATAFRAME
# =============================================================================
# Convert the list of transfer records into a pandas DataFrame and format it
# for the final output CSV file.

# Convert transfers list to DataFrame
df_transfers = pd.DataFrame(transfers)

# Select only the 5 columns matching output.csv format
# The 'Component' column was kept for reference but is removed in final output
output_columns = ['Source_Plate', 'Source_Well', 'Dest_Plate', 'Dest_Well', 'Transfer_Vol']
df_output = df_transfers[output_columns].copy()

# Sort by destination plate and well for better organization
# This makes it easier to read and follow the transfer sequence
df_output = df_output.sort_values(['Dest_Plate', 'Dest_Well', 'Source_Plate', 'Source_Well'])

print(f"Output dataframe shape: {df_output.shape}")
print(f"\nFirst 10 rows:")
print(df_output.head(10))
print(f"\nLast 10 rows:")
print(df_output.tail(10))


# %%
# =============================================================================
# SECTION 12: SAVE OUTPUT CSV
# =============================================================================
# Save the transfer instructions to a CSV file that can be loaded into the
# liquid handler software.

output_file = user_params['output_file']
df_output.to_csv(output_file, index=False)  # index=False means don't save row numbers

print(f"Output saved to: {output_file}")
print(f"Total transfers: {len(df_output)}")
print(f"Unique destination wells: {df_output['Dest_Well'].nunique()}")
print(f"Unique source plates: {df_output['Source_Plate'].nunique()}")
print(f"Unique destination plates: {df_output['Dest_Plate'].nunique()}")


# %%
# =============================================================================
# SECTION 13: VALIDATION TESTS
# =============================================================================
# Run validation tests to ensure the calculations are correct.
# These tests verify that:
# 1. Volumes sum correctly
# 2. Transfer volumes meet minimum requirements
# 3. Water volumes are non-negative
# 4. Back-calculated concentrations match targets

validation_errors = []
validation_warnings = []

# -----------------------------------------------------------------------------
# Test 1: Volume sums equal well_volume for each well
# -----------------------------------------------------------------------------
# For each well, the sum of all component volumes should equal well_volume
print("Test 1: Volume sums validation")
for well in df_volumes.index:
    total_vol = df_volumes.loc[well].sum()  # Sum all component volumes
    # Check if total equals well_volume (using epsilon for floating point comparison)
    if not np.isclose(total_vol, user_params['well_volume'], atol=user_params['epsilon']):
        validation_errors.append(
            f"Well {well}: Total volume {total_vol:.2f} != {user_params['well_volume']} µL"
        )

if validation_errors:
    print(f"  FAILED: {len(validation_errors)} wells with incorrect volume sums")
    for err in validation_errors[:5]:
        print(f"    - {err}")
else:
    print("  PASSED: All wells have correct volume sums")

# -----------------------------------------------------------------------------
# Test 2: All transfer volumes >= min_transfer_volume
# -----------------------------------------------------------------------------
# Check if any transfers are smaller than the minimum accurate volume
print("\nTest 2: Minimum transfer volume validation")
small_volumes = []
for well in df_volumes.index:
    for comp in df_volumes.columns:
        vol = df_volumes.loc[well, comp]
        if vol > 0 and vol < user_params['min_transfer_volume']:
            stock_level = df_conc_level.loc[well, comp]
            small_volumes.append(f"Well {well}, {comp}: {vol:.2f} µL (stock: {stock_level})")

if small_volumes:
    print(f"  WARNING: {len(small_volumes)} transfers < {user_params['min_transfer_volume']} µL")
    for warn in small_volumes[:5]:
        print(f"    - {warn}")
else:
    print("  PASSED: All transfer volumes >= minimum")

# -----------------------------------------------------------------------------
# Test 3: Water volume >= 0
# -----------------------------------------------------------------------------
# Water volume should never be negative (that would mean we're overfilling)
print("\nTest 3: Water volume validation")
negative_water = df_volumes[df_volumes['Water'] < 0]
if len(negative_water) > 0:
    validation_errors.append(f"Found {len(negative_water)} wells with negative water volume")
    print(f"  FAILED: {len(negative_water)} wells with negative water")
else:
    print("  PASSED: All water volumes >= 0")

# -----------------------------------------------------------------------------
# Test 4: Back-calculation validation
# -----------------------------------------------------------------------------
# Verify that if we calculate the concentration from the transfer volume,
# we get back the target concentration (within tolerance)
print("\nTest 4: Back-calculation validation (ALL wells)")
sample_wells = df_target_conc.index  # All wells
backcalc_errors = []

for well in sample_wells:
    for comp in df_target_conc.columns:
        if comp in ['Water', 'Culture']:
            continue  # Skip water and culture (they don't use concentration-based calculation)

        target_conc = df_target_conc.loc[well, comp]  # Target concentration
        transfer_vol = df_volumes.loc[well, comp]      # Calculated transfer volume
        stock_level = df_conc_level.loc[well, comp]    # Which stock was used

        if transfer_vol == 0 or stock_level is None:
            continue

        # Get stock concentration
        if comp in stock_lookup:
            stocks = stock_lookup[comp]
            stock_info = stocks.get(stock_level)
            if stock_info:
                stock_conc = stock_info.get('conc')
                if stock_conc is not None:
                    # Back-calculate: (transfer_vol × stock_conc) / well_vol should ≈ target_conc
                    # This reverses the calculation: C2 = (V1 × C1) / V2
                    calculated_conc = (transfer_vol * stock_conc) / user_params['well_volume']
                    # Use epsilon for comparison (allow 1% relative tolerance)
                    if not np.isclose(calculated_conc, target_conc, rtol=0.01, atol=user_params['epsilon']):
                        backcalc_errors.append(
                            f"Well {well}, {comp}: calculated {calculated_conc:.6f} != target {target_conc:.6f}"
                        )

# Calculate statistics if there are errors
if backcalc_errors:
    # Extract errors for statistics
    error_values = []
    for err in backcalc_errors:
        # Parse error message to extract values
        if 'calculated' in err and 'target' in err:
                try:
                    parts = err.split('calculated')[1].split('!=')
                    calc_val = float(parts[0].strip())
                    target_val = float(parts[1].split('target')[1].strip())
                    error_values.append(abs(calc_val - target_val))
                except (ValueError, IndexError):
                    pass

    if error_values:
        mean_error = np.mean(error_values)
        max_error = np.max(error_values)
        print(f"  Statistics:")
        print(f"    Mean absolute error: {mean_error:.6f} mM")
        print(f"    Max absolute error: {max_error:.6f} mM")
        print(f"    Wells with error > 1%: {sum(1 for e in error_values if e > 0.01)}")

if backcalc_errors:
    print(f"  WARNING: {len(backcalc_errors)} back-calculation mismatches")
    for err in backcalc_errors[:5]:
        print(f"    - {err}")
else:
    print("  PASSED: Back-calculations match target concentrations")

print(f"\nValidation Summary:")
print(f"  Errors: {len(validation_errors)}")
print(f"  Warnings: {len(validation_warnings) + len(small_volumes) + len(backcalc_errors)}")


# %%
# =============================================================================
# SECTION 14: COMPARE WITH REFERENCE OUTPUT (if available)
# =============================================================================
# If a reference output file exists, compare our results with it.
# This is useful for debugging and verifying the script works correctly.

reference_file = 'data/output.csv'
if os.path.exists(reference_file):
    try:
        df_reference = pd.read_csv(reference_file)
        print(f"Reference file found: {reference_file}")
        print(f"  Reference shape: {df_reference.shape}")
        print(f"  Our output shape: {df_output.shape}")

        # Check column names match
        ref_cols = list(df_reference.columns[:5])  # First 5 columns
        our_cols = list(df_output.columns)
        if ref_cols == our_cols:
            print("  Column names match")
        else:
            print(f"  Column mismatch:")
            print(f"    Reference: {ref_cols}")
            print(f"    Our output: {our_cols}")

        # Compare row counts
        if len(df_reference) == len(df_output):
            print(f"  Row counts match: {len(df_output)}")
        else:
            print(f"  Row count mismatch: reference={len(df_reference)}, ours={len(df_output)}")

        # Sample comparison (first few rows)
        print("\n  Sample comparison (first 5 rows):")
        print("  Reference:")
        print(df_reference.head())
        print("\n  Our output:")
        print(df_output.head())

    except Exception as e:
        print(f"Could not read reference file: {e}")
else:
    print(f"Reference file not found: {reference_file}")
    print("Skipping comparison with reference output")


# %%
# =============================================================================
# SECTION 15: FINAL SUMMARY
# =============================================================================
# Print a comprehensive summary of what was generated.

print("="*70)
print("TRANSFER FILE GENERATION COMPLETE")
print("="*70)
print(f"\nInput Data:")
print(f"  Target wells: {len(df_target_conc)}")
print(f"  Components: {len(df_target_conc.columns)}")
print(f"  Stock components: {len(stock_lookup)}")

print(f"\nCalculations:")
print(f"  Total transfer records: {len(df_output)}")
print(f"  Destination plates: {df_output['Dest_Plate'].nunique()}")
print(f"  Source plates: {df_output['Source_Plate'].nunique()}")

print(f"\nOutput:")
print(f"  File: {user_params['output_file']}")
print(f"  Format: 5 columns (Source_Plate, Source_Well, Dest_Plate, Dest_Well, Transfer_Vol)")

print(f"\nValidation:")
print(f"  Volume sum errors: {len(validation_errors)}")
print(f"  Total warnings: {len(calc_warnings) + len(transfer_warnings) + len(depletion_warnings)}")
print(f"  Source depletion warnings: {len(depletion_warnings)}")

if len(validation_errors) == 0:
    print("\n✅ All critical validations passed!")
else:
    print(f"\n⚠️  {len(validation_errors)} validation errors found - please review")

print("="*70)
