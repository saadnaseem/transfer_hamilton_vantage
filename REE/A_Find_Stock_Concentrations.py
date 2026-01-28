#!/usr/bin/env python
# coding: utf-8

"""
Calculate low and high stock solution concentrations for media optimization.

This script calculates stock concentrations that allow media preparation without dilutions,
reducing pipetting operations and tip usage. Given a standard media recipe and target
concentration ranges, it generates low and high stock concentrations that satisfy:
- Solubility limits
- Minimum transfer volume constraints
- Well volume constraints

Inputs:
    - standard_recipe_concentrations.csv: Standard media recipe with concentrations [mM] and solubility limits
    - Putida_media_bounds.csv: Target concentration ranges (Min/Max) for each component

Outputs:
    - stock_concentrations_REE.csv: Low and high stock concentrations with dilution factors
"""

from pathlib import Path
import pandas as pd
import numpy as np




# =============================================================================
# CONFIGURATION
# =============================================================================

user_params = {
    'standard_media_file': 'data/standard_recipe_concentrations.csv',  
    'output_file_path': 'data/',
    'bounds_file': 'data/Putida_media_bounds.csv',  # CSV with columns [Variable, Min, Max]
    'well_volume': 1000,            # Total volume of the media content+culture in the well (µL)
    'min_volume_transfer': 10,        # Minimal transfer volume of the liquid handler (µL)
}


# =============================================================================
# DATA LOADING
# =============================================================================

# Load standard media recipe with solubility limits
try:
    df_stand = pd.read_csv(user_params['standard_media_file'])
    df_stand = df_stand.set_index("Component")
    print(f"Loaded standard recipe: {user_params['standard_media_file']}")
except FileNotFoundError:
    raise FileNotFoundError(
        f"Could not find standard media file: {user_params['standard_media_file']}\n"
        f"Please ensure the file exists in the data directory."
    )
except Exception as e:
    raise Exception(f"Error reading standard media file: {e}")

# Load target concentration bounds (Min/Max for each component)
try:
    df_bounds = pd.read_csv(user_params['bounds_file'])
    df_bounds = df_bounds.set_index('Variable')
except FileNotFoundError:
    raise FileNotFoundError(
        f"Could not find bounds file: {user_params['bounds_file']}\n"
        f"Please ensure the file exists in the data directory."
    )
except Exception as e:
    raise Exception(f"Error reading bounds file: {e}")

# Filter standard recipe to only include components in bounds file
df_stand = df_stand.loc[df_bounds.index]
print(f"Loaded {len(df_bounds)} components from bounds file")


# =============================================================================
# CALCULATE LOW STOCK CONCENTRATIONS
# =============================================================================
# Find stock concentrations that can achieve minimum target concentrations.
# Formula: Stock_conc = (Min_target × well_volume) / min_tip_volume

min_tip_volume = user_params['min_volume_transfer']
df_low = pd.DataFrame(
    index=df_stand.index,
    columns=["Stock Concentration", "Target Concentration"]
)

# Initialize with minimum target concentrations
df_low["Target Concentration"] = df_bounds["Min"]
df_low["Stock Concentration"] = (
    df_low["Target Concentration"] * user_params['well_volume'] / min_tip_volume
)


# Check solubility limits
# If stock concentration exceeds solubility, increase transfer volume incrementally
# to reduce required stock concentration: Stock = (target × well_volume) / transfer_volume

def check_solubility(df, solubility):
    """Return components where stock concentration exceeds solubility limit."""
    nonsol = []
    for comp in df.index:
        if comp in solubility.index:
            if df.at[comp, 'Stock Concentration'] > solubility[comp]:
                nonsol.append(comp)
    return nonsol

if 'Solubility' in df_stand.columns:
    nonsol_comp_low = check_solubility(df_low, solubility=df_stand['Solubility'])
    volume_transfer = min_tip_volume
    
    iteration = 0
    while len(nonsol_comp_low) > 0:
        volume_transfer += min_tip_volume
        for comp in nonsol_comp_low:
            df_low.at[comp, "Stock Concentration"] = (
                df_low.at[comp, "Target Concentration"] 
                * user_params['well_volume'] / volume_transfer
            )
        nonsol_comp_low = check_solubility(df_low, solubility=df_stand['Solubility'])
        iteration += 1
        if iteration > 100:  # Safety limit
            print(f"Warning: Could not resolve solubility for {nonsol_comp_low}")
            break
else:
    print('Note: Solubility values not provided, assuming limits are not reached.')


# Handle zero Min values and ensure volumes fit in well
# Components with Min=0 need special handling - use Max target for stock calculation
EPS = 0.000001
zero_min_components = df_low[df_low['Target Concentration'] == 0].index.tolist()
if len(zero_min_components) > 0:
    print(f"Note: {len(zero_min_components)} components have Min=0, using Max for stock calculation")
    for comp in zero_min_components:
        max_target = df_bounds.at[comp, 'Max']
        df_low.at[comp, 'Stock Concentration'] = (
            max_target * user_params['well_volume'] / min_tip_volume
        )

# Check volume constraint: sum of (target/stock) ratios must be <= 1.0
# This ensures all component volumes fit within the well volume
stock_vals = df_low['Stock Concentration'].values.astype(float)
target_vals = df_low['Target Concentration'].values.astype(float)
ratios = np.where(stock_vals > 0, target_vals / stock_vals, 0)
current_sum = np.sum(ratios)

# If sum > 1, increase all stock concentrations proportionally to reduce volumes
MAX_SUM = 0.95  # Leave 5% headroom for water
iteration = 0
MAX_ITERATIONS = 20

while current_sum > MAX_SUM and iteration < MAX_ITERATIONS:
    iteration += 1
    factor = current_sum / MAX_SUM
    df_low['Stock Concentration'] = df_low['Stock Concentration'] * factor
    
    # Recalculate ratios
    stock_vals = df_low['Stock Concentration'].values.astype(float)
    ratios = np.where(stock_vals > 0, target_vals / stock_vals, 0)
    current_sum = np.sum(ratios)

if current_sum > MAX_SUM:
    print(f"Warning: Could not reduce volume sum below {MAX_SUM} after {MAX_ITERATIONS} iterations")

def find_volumes(well_volume, components, stock_conc_val, target_conc_val):
    """
    Calculate transfer volumes for each component to achieve target concentrations.
    
    Formula: volume = (target_conc / stock_conc) × well_volume
    
    Parameters:
    -----------
    well_volume : float
        Total volume of the well (µL)
    components : array-like
        Component names
    stock_conc_val : array-like
        Stock concentrations for each component
    target_conc_val : array-like
        Target concentrations for each component
    
    Returns:
    --------
    volumes : dict
        Dictionary mapping component names to volumes (µL)
    df : pandas.DataFrame
        DataFrame with 'Volumes[uL]' column indexed by component names
    """
    volumes_dict = {}
    for i, comp in enumerate(components):
        if stock_conc_val[i] > 0:
            volume = (target_conc_val[i] / stock_conc_val[i]) * well_volume
        else:
            volume = 0.0
        volumes_dict[comp] = volume
    
    df = pd.DataFrame(index=components)
    df['Volumes[uL]'] = [volumes_dict[comp] for comp in components]
    return volumes_dict, df

# Verify volumes meet minimum transfer requirements
volumes, _ = find_volumes(
    user_params['well_volume'], 
    components=df_low.index,
    stock_conc_val=df_low['Stock Concentration'].values, 
    target_conc_val=df_low['Target Concentration'].values
)

non_zero_mask = df_low['Target Concentration'] > 0
non_zero_volumes = [volumes[comp] for comp in df_low.index[non_zero_mask]]

if len(non_zero_volumes) > 0:
    all_valid = all(v >= min_tip_volume - EPS for v in non_zero_volumes)
    assert all_valid, f"Not all volumes are >={min_tip_volume}µL!"
    print(f"All non-zero target volumes >= {min_tip_volume} µL: ✓")

# Round stock concentrations
num_digits = 6
df_low['Stock Concentration'] = df_low['Stock Concentration'].round(num_digits)


# =============================================================================
# CALCULATE HIGH STOCK CONCENTRATIONS
# =============================================================================
# Check if low stock concentrations can achieve maximum target concentrations.
# If not, increase stock concentrations (starting with components furthest from solubility limit).

df_high = df_low.copy()
df_high["Target Concentration"] = df_bounds["Max"]
df_high["Solubility"] = df_stand['Solubility']

# Check if low stock concentrations can achieve maximum targets
try:
    volumes, df_volumes_check = find_volumes(
        user_params['well_volume'],
        components=df_high.index,
        stock_conc_val=df_high['Stock Concentration'].values, 
        target_conc_val=df_high['Target Concentration'].values
    )
    feasible_volumes = True
    assert (df_volumes_check['Volumes[uL]'].values >= min_tip_volume - EPS).all(), \
        f"Not all volumes are >={min_tip_volume}µL!"
    df_high['Volumes[uL]'] = df_volumes_check['Volumes[uL]']
except AssertionError:
    feasible_volumes = False
    print("Low stocks cannot achieve max targets - adjusting stock concentrations...")


# If low stocks can't achieve max targets, increase stock concentrations
# Start with components furthest from solubility limit (safest to increase)
if not feasible_volumes:
    MULTIPL_FACTOR = 5
    success = False
    iteration = 0
    max_iterations = 50
    
    while not success and iteration < max_iterations:
        iteration += 1
        
        # Find component furthest from solubility limit
        ratios = df_high['Solubility'].values / df_high['Stock Concentration'].values
        df_high['Ratio'] = ratios
        candidates = df_high[df_high['Ratio'] > MULTIPL_FACTOR]
        
        if len(candidates) == 0:
            print("Warning: No components can be increased further")
            break
            
        comp = candidates['Ratio'].idxmax()
        df_high.at[comp, 'Stock Concentration'] *= MULTIPL_FACTOR
        
        # Check if volumes are now feasible
        try:
            volumes, df_volumes = find_volumes(
                user_params['well_volume'], 
                components=df_high.index,
                stock_conc_val=df_high['Stock Concentration'].values, 
                target_conc_val=df_high['Target Concentration'].values
            )
            if (df_volumes['Volumes[uL]'].values >= min_tip_volume - EPS).all():
                df_high['Volumes[uL]'] = df_volumes['Volumes[uL]']
                success = True
                print(f"Adjusted stocks after {iteration} iteration(s)")
        except Exception:
            pass

# Correct for minimal transfer volumes
# If any volume < min_tip_volume, decrease stock concentration to increase transfer volume
comp_small_vol = df_high[df_high['Volumes[uL]'] < min_tip_volume - EPS].index
if len(comp_small_vol) > 0:
    NEW_VOLUME_TRANSFER = 5.0 * min_tip_volume
    for comp in comp_small_vol:
        factor_diff = NEW_VOLUME_TRANSFER / df_high.at[comp, 'Volumes[uL]']
        df_high.at[comp, 'Stock Concentration'] /= factor_diff
    
    # Recalculate volumes
    volumes, df_volumes_new = find_volumes(
        user_params['well_volume'], 
        components=df_high.index,
        stock_conc_val=df_high['Stock Concentration'].values, 
        target_conc_val=df_high['Target Concentration'].values
    )
    df_high['Volumes[uL]'] = df_volumes_new['Volumes[uL]']

# Round stock concentrations
df_high['Stock Concentration'] = df_high['Stock Concentration'].round(5)


# =============================================================================
# GENERATE OUTPUT
# =============================================================================

# Create final dataframe with low and high concentrations
df_stock = df_low.copy()
df_stock.rename(columns={'Stock Concentration': 'Low Concentration'}, inplace=True)
df_stock = df_stock.drop(['Target Concentration'], axis='columns')
df_stock['High Concentration'] = df_high['Stock Concentration']
df_stock['Dilution Factor'] = df_stock['High Concentration'] / df_stock['Low Concentration']

# Save to CSV file
output_file = Path(user_params['output_file_path']) / 'stock_concentrations_REE.csv'
df_stock.to_csv(output_file)
print(f"\nStock concentrations saved to: {output_file}")
print("\nFinal stock concentrations:")
print(df_stock)