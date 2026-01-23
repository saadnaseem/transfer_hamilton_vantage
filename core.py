"""
Core functions for calculating transfer volumes for media preparation.

This module replaces the original core.py dependency and provides functions
to calculate transfer volumes from target concentrations and stock concentrations.
"""

import pandas as pd
import numpy as np


def find_volumes(
    target_conc_dict: dict,
    df_stock: pd.DataFrame,
    well_volume: float,
    min_tip_volume: float = 5.0
) -> tuple[dict, dict]:
    """
    Calculate transfer volumes for a single set of target concentrations.
    
    This function determines:
    1. Transfer volumes for each component
    2. Whether to use HIGH or LOW stock concentration
    
    Algorithm:
    - First tries to use HIGH stock concentrations
    - If any resulting volume < min_tip_volume, switches to LOW stock for that component
    - Recalculates volumes with the new stock concentrations
    - Water volume is calculated to bring total to well_volume
    
    Parameters
    ----------
    target_conc_dict : dict
        Dictionary mapping component names to target concentrations (mM)
    df_stock : pd.DataFrame
        DataFrame with stock concentrations. Must have index='Component' and columns:
        - 'High Concentration[mM]' or 'High Concentration'
        - 'Low Concentration[mM]' or 'Low Concentration'
    well_volume : float
        Total volume (µL) in each destination well
    min_tip_volume : float, optional
        Minimum accurate transfer volume (µL). Below this, use LOW stock.
        Default is 5.0 µL.
    
    Returns
    -------
    volumes : dict
        Dictionary mapping component names to transfer volumes (µL)
        Includes 'Water' key for water volume needed
    conc_level : dict
        Dictionary mapping component names to 'high' or 'low' stock level used
    """
    volumes = {}
    conc_level = {}
    
    # Normalize column names (handle both with and without [mM] suffix)
    high_col = 'High Concentration[mM]' if 'High Concentration[mM]' in df_stock.columns else 'High Concentration'
    low_col = 'Low Concentration[mM]' if 'Low Concentration[mM]' in df_stock.columns else 'Low Concentration'
    
    # First pass: try HIGH stock for all components
    for comp, target_conc in target_conc_dict.items():
        if comp not in df_stock.index:
            # Skip components not in stock (e.g., metadata columns)
            continue
            
        stock_high = df_stock.loc[comp, high_col]
        
        # Calculate volume: volume = (target_conc * well_volume) / stock_conc
        # This comes from: target_conc = (stock_conc * volume) / well_volume
        if stock_high > 0:
            vol_high = (target_conc * well_volume) / stock_high
        else:
            vol_high = 0.0
        
        volumes[comp] = vol_high
        conc_level[comp] = 'high'
    
    # Second pass: switch to LOW stock if volume < min_tip_volume
    for comp in volumes.keys():
        if volumes[comp] < min_tip_volume and volumes[comp] > 0:
            stock_low = df_stock.loc[comp, low_col]
            target_conc = target_conc_dict[comp]
            
            if stock_low > 0:
                vol_low = (target_conc * well_volume) / stock_low
                volumes[comp] = vol_low
                conc_level[comp] = 'low'
    
    # Calculate water volume to fill remaining space
    total_component_volume = sum(volumes.values())
    volumes['Water'] = well_volume - total_component_volume
    
    # Ensure water volume is non-negative
    if volumes['Water'] < 0:
        raise ValueError(
            f"Total component volumes ({total_component_volume:.2f} µL) exceed "
            f"well volume ({well_volume:.2f} µL). Cannot achieve target concentrations."
        )
    
    return volumes, conc_level


def find_volumes_bulk(
    df_stock: pd.DataFrame,
    df_target_conc: pd.DataFrame,
    well_volume: float,
    min_tip_volume: float = 5.0,
    culture_ratio: float = 100.0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate transfer volumes for multiple wells, auto-selecting high/low stocks.
    
    This is the main function used in the notebook. It processes all wells at once
    and determines optimal stock concentrations (high/low) for each component/well
    combination.
    
    Parameters
    ----------
    df_stock : pd.DataFrame
        DataFrame with stock concentrations. Must have index='Component' and columns:
        - 'High Concentration[mM]' or 'High Concentration'
        - 'Low Concentration[mM]' or 'Low Concentration'
    df_target_conc : pd.DataFrame
        DataFrame with target concentrations for each well.
        Index should be well names (e.g., 'A1', 'A2', ...).
        Columns should be component names with target concentrations (mM).
        May include metadata columns (e.g., 'OD340_pred', 'Label') which will be ignored.
    well_volume : float
        Total volume (µL) in each destination well
    min_tip_volume : float, optional
        Minimum accurate transfer volume (µL). Below this, use LOW stock.
        Default is 5.0 µL.
    culture_ratio : float, optional
        Culture dilution factor. Not used in volume calculation but kept for API compatibility.
        Default is 100.0.
    
    Returns
    -------
    df_volumes : pd.DataFrame
        DataFrame with transfer volumes (µL) for each component per well.
        Index: well names
        Columns: component names + 'Water'
        Does NOT include 'Culture' - that is added separately in the notebook.
    df_conc_level : pd.DataFrame
        DataFrame indicating whether to use 'high' or 'low' stock for each component/well.
        Index: well names
        Columns: component names
        Values: 'high' or 'low'
    
    Notes
    -----
    - The algorithm first tries HIGH stock for all components
    - If any volume < min_tip_volume, it switches to LOW stock for that component
    - Water volume is calculated to bring total to well_volume
    - Culture volume is NOT included here - it's added separately in the notebook
    """
    # Normalize column names in df_stock
    high_col = 'High Concentration[mM]' if 'High Concentration[mM]' in df_stock.columns else 'High Concentration'
    low_col = 'Low Concentration[mM]' if 'Low Concentration[mM]' in df_stock.columns else 'Low Concentration'
    
    # Get component columns (exclude metadata columns)
    component_cols = [col for col in df_target_conc.columns if col in df_stock.index]
    
    # Initialize output dataframes
    df_volumes = pd.DataFrame(index=df_target_conc.index, columns=component_cols + ['Water'])
    df_conc_level = pd.DataFrame(index=df_target_conc.index, columns=component_cols)
    
    # Process each well
    for well in df_target_conc.index:
        # Get target concentrations for this well
        target_conc_dict = df_target_conc.loc[well, component_cols].to_dict()
        
        # Calculate volumes for this well
        volumes, conc_level = find_volumes(
            target_conc_dict=target_conc_dict,
            df_stock=df_stock,
            well_volume=well_volume,
            min_tip_volume=min_tip_volume
        )
        
        # Store results
        for comp in component_cols:
            if comp in volumes:
                df_volumes.loc[well, comp] = volumes[comp]
                df_conc_level.loc[well, comp] = conc_level[comp]
        
        df_volumes.loc[well, 'Water'] = volumes['Water']
    
    # Convert to numeric (in case any values are strings)
    for col in df_volumes.columns:
        df_volumes[col] = pd.to_numeric(df_volumes[col], errors='coerce')
    
    return df_volumes, df_conc_level
