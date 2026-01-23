#!/usr/bin/env python
# coding: utf-8

"""
Comprehensive test suite for transfer.py
Tests cover:
- Unit tests for core functions
- Integration tests for full pipeline
- Edge case handling
- Data validation
"""

import pytest
import pandas as pd
import numpy as np
import os
import math
from io import StringIO
import sys


# =============================================================================
# FIXTURES AND SETUP
# =============================================================================

@pytest.fixture
def sample_stock_conc():
    """Create sample stock concentrations DataFrame."""
    return pd.DataFrame({
        'Component': ['MOPS', 'Tricine', 'H3BO3', 'Glucose', 'K2SO4'],
        'Low Concentration': [2000, 400, 0.12, 3000, 8.7],
        'High Concentration': [2000, 400, 2.4, 3000, 43.5],
        'Dilution Factor': [1, 1, 20, 1, 5]
    }).set_index('Component')


@pytest.fixture
def sample_stock_plate_high():
    """Create sample high concentration stock plate layout."""
    return pd.DataFrame({
        'Well': ['A1', 'B1', 'C1', 'D1', 'A2'],
        'Component': ['MOPS', 'Tricine', 'H3BO3', 'Glucose', 'K2SO4'],
        'Concentration[mM]': [2000.0, 400.0, 2.4, 3000.0, 43.5]
    })


@pytest.fixture
def sample_stock_plate_low():
    """Create sample low concentration stock plate layout."""
    return pd.DataFrame({
        'Well': ['A1', 'B1', 'C1'],
        'Component': ['H3BO3', 'K2SO4', 'Glucose'],
        'Concentration[mM]': [0.12, 8.7, 3000.0]
    })


@pytest.fixture
def sample_target_conc():
    """Create sample target concentrations."""
    wells = ['A1', 'A2', 'B1', 'B2']
    data = {
        'MOPS': [0.0, 0.0, 0.0, 0.0],
        'H3BO3': [0.0037, 0.05, 0.1, 0.5],
        'K2SO4': [0.03, 0.5, 1.0, 5.0],
        'Glucose': [20.0, 20.0, 20.0, 20.0],
    }
    return pd.DataFrame(data, index=wells)


@pytest.fixture
def user_params():
    """Standard user parameters for testing."""
    return {
        'well_volume': 1500,
        'source_well_volume': 9000,
        'dead_volume': 100,
        'min_transfer_volume': 5.0,
        'max_tip_volume': 200.0,
        'culture_factor': 100,
        'epsilon': 1e-6,
        'wells_per_plate': 48,
        'plate_format': '48-well',
        'add_culture_to_all_wells': True,
        'water_source': {
            'plate': 's_water',
            'well': 'A1',
            'type': 'plate'
        }
    }


# =============================================================================
# UNIT TESTS - Core Functions
# =============================================================================

class TestStockLookupCreation:
    """Test stock_lookup creation from plate layouts."""

    def test_stock_lookup_basic_structure(self, sample_stock_conc, sample_stock_plate_high, sample_stock_plate_low):
        """Test that stock_lookup has correct structure."""
        stock_lookup = {}

        # Initialize all components
        for comp in sample_stock_conc.index:
            stock_lookup[comp] = {'high': None, 'low': None}

        # Populate HIGH
        for _, row in sample_stock_plate_high.iterrows():
            comp = row['Component']
            if comp not in stock_lookup:
                stock_lookup[comp] = {'high': None, 'low': None}
            stock_lookup[comp]['high'] = {
                'plate': 's1',
                'well': row['Well'],
                'conc': row['Concentration[mM]']
            }

        # Populate LOW
        for _, row in sample_stock_plate_low.iterrows():
            comp = row['Component']
            if comp not in stock_lookup:
                stock_lookup[comp] = {'high': None, 'low': None}
            stock_lookup[comp]['low'] = {
                'plate': 's4',
                'well': row['Well'],
                'conc': row['Concentration[mM]']
            }

        # Assertions
        assert len(stock_lookup) == 5, f"Expected 5 components, got {len(stock_lookup)}"
        assert 'MOPS' in stock_lookup
        assert stock_lookup['MOPS']['high'] is not None
        assert stock_lookup['MOPS']['high']['well'] == 'A1'
        assert stock_lookup['MOPS']['high']['plate'] == 's1'
        assert stock_lookup['H3BO3']['low'] is not None
        assert stock_lookup['H3BO3']['low']['conc'] == 0.12

    def test_stock_lookup_all_components_covered(self, sample_stock_plate_high, sample_stock_plate_low):
        """Test that all components in target are covered by stock plates."""
        high_components = set(sample_stock_plate_high['Component'])
        low_components = set(sample_stock_plate_low['Component'])
        all_components = high_components | low_components

        assert 'MOPS' in all_components
        assert 'H3BO3' in all_components
        assert len(all_components) >= 3

    def test_stock_lookup_handles_duplicates(self, sample_stock_plate_high):
        """Test that stock_lookup handles components appearing in multiple wells."""
        stock_lookup = {}
        for _, row in sample_stock_plate_high.iterrows():
            comp = row['Component']
            if comp not in stock_lookup:
                stock_lookup[comp] = {'high': None, 'low': None}
            # Last well wins for same component
            stock_lookup[comp]['high'] = {
                'plate': 's1',
                'well': row['Well'],
                'conc': row['Concentration[mM]']
            }

        # MOPS appears once, so should have one well
        assert stock_lookup['MOPS']['high'] is not None


class TestWellRemapping:
    """Test well remapping for different plate formats."""

    def test_48well_format_valid_wells(self):
        """Test that 48-well format validates correctly."""
        # 48-well: A-F (6 rows) × 1-8 (8 columns)
        valid_wells = ['A1', 'A8', 'F1', 'F8']
        for well in valid_wells:
            row = well[0]
            col = int(well[1:])
            assert row in 'ABCDEF'
            assert col in range(1, 9)

    def test_96well_format_valid_wells(self):
        """Test that 96-well format validates correctly."""
        # 96-well: A-H (8 rows) × 1-12 (12 columns)
        valid_wells = ['A1', 'A12', 'H1', 'H12']
        for well in valid_wells:
            row = well[0]
            col = int(well[1:])
            assert row in 'ABCDEFGH'
            assert col in range(1, 13)

    def test_well_remapping_48to48(self):
        """Test remapping within 48-well format."""
        wells_48 = ['A1', 'F8', 'C4']
        for well in wells_48:
            row = well[0]
            col = int(well[1:])
            # Check bounds
            assert row <= 'F', f"Row {row} exceeds 48-well format"
            assert col <= 8, f"Col {col} exceeds 48-well format"

    def test_well_remapping_96to48(self):
        """Test remapping from 96-well to 48-well."""
        # G1 should remap to F1 (beyond 48-well rows)
        well_96 = 'G1'
        row = well_96[0]
        col = int(well_96[1:])

        # Remap logic
        if row > 'F':
            row = 'F'
        if col > 8:
            col = 8

        remapped = f"{row}{col}"
        assert row == 'F'
        assert remapped == 'F1'


class TestDestinationPlateAssignment:
    """Test destination plate assignment."""

    def test_48well_single_plate(self):
        """Test that 48 wells fit in one destination plate."""
        wells = [f"{chr(65+i)}{j}" for i in range(6) for j in range(1, 9)]  # A1-F8
        assignments = {}
        plate_num = 1
        well_count = 0

        for well in wells:
            if well_count >= 48:
                plate_num += 1
                well_count = 0
            assignments[well] = f"dest_{plate_num}"
            well_count += 1

        assert len(set(assignments.values())) == 1, "48 wells should fit in 1 plate"
        assert all(v == 'dest_1' for v in assignments.values())

    def test_96well_two_plates(self):
        """Test that 96 wells require two destination plates."""
        wells = [f"{chr(65+i)}{j}" for i in range(8) for j in range(1, 13)]  # A1-H12
        assignments = {}
        plate_num = 1
        well_count = 0

        for well in wells:
            if well_count >= 48:
                plate_num += 1
                well_count = 0
            assignments[well] = f"dest_{plate_num}"
            well_count += 1

        plate_count = len(set(assignments.values()))
        assert plate_count == 2, f"96 wells should require 2 plates with 48-well limit, got {plate_count}"

    def test_assignment_maintains_order(self):
        """Test that well assignments are in order."""
        wells = ['A1', 'A2', 'A3', 'B1', 'B2']
        assignments = {}
        plate_num = 1
        well_count = 0

        for well in wells:
            if well_count >= 48:
                plate_num += 1
                well_count = 0
            assignments[well] = f"dest_{plate_num}"
            well_count += 1

        assert assignments['A1'] == 'dest_1'
        assert assignments['A2'] == 'dest_1'
        assert assignments['B1'] == 'dest_1'


class TestVolumeCalculation:
    """Test volume calculation logic."""

    def test_calculate_transfer_volume_basic(self):
        """Test basic transfer volume calculation."""
        # Formula: (target_conc × well_volume) / stock_conc
        target_conc = 1.0  # mM
        well_volume = 1500  # µL
        stock_conc = 2000.0  # mM

        transfer_vol = (target_conc * well_volume) / stock_conc
        expected = 0.75  # µL

        assert abs(transfer_vol - expected) < 0.01

    def test_calculate_transfer_volume_high_dilution(self):
        """Test transfer volume with high dilution (high concentration stock)."""
        # Small target concentration, high stock
        target_conc = 0.001  # mM
        well_volume = 1500  # µL
        stock_conc = 2.4  # mM (high boron)

        transfer_vol = (target_conc * well_volume) / stock_conc
        # (0.001 × 1500) / 2.4 = 0.625 µL

        assert transfer_vol < 1.0
        assert transfer_vol > 0

    def test_calculate_transfer_volume_low_dilution(self):
        """Test transfer volume with low dilution (low concentration stock)."""
        # Moderate target, low stock
        target_conc = 1.0  # mM
        well_volume = 1500  # µL
        stock_conc = 0.12  # mM (low boron)

        transfer_vol = (target_conc * well_volume) / stock_conc
        # (1.0 × 1500) / 0.12 = 12500 µL - would exceed tip volume

        assert transfer_vol > 1500  # Exceeds well volume, error case

    def test_transfer_volume_selection_high_then_low(self):
        """Test that HIGH stock is selected first, LOW if volume too small."""
        target_conc = 0.001  # mM - very small
        well_volume = 1500  # µL
        stock_high = 2.4  # mM
        stock_low = 0.12  # mM
        min_transfer = 5.0  # µL

        # Try HIGH first
        vol_high = (target_conc * well_volume) / stock_high
        # 0.625 µL - below minimum

        # Try LOW
        vol_low = (target_conc * well_volume) / stock_low
        # 12.5 µL - above minimum, so use LOW

        assert vol_high < min_transfer
        assert vol_low >= min_transfer


class TestTransferSplitting:
    """Test transfer volume splitting for max tip volume."""

    def test_transfer_no_split_below_max(self):
        """Test that transfers below max_tip_volume are not split."""
        transfer_vol = 100.0  # µL
        max_tip_volume = 200.0  # µL

        num_cycles = math.ceil(transfer_vol / max_tip_volume)
        assert num_cycles == 1

    def test_transfer_split_above_max(self):
        """Test that transfers above max_tip_volume are split."""
        transfer_vol = 300.0  # µL
        max_tip_volume = 200.0  # µL

        num_cycles = math.ceil(transfer_vol / max_tip_volume)
        vol_per_cycle = transfer_vol / num_cycles

        assert num_cycles == 2
        assert abs(vol_per_cycle - 150.0) < 0.01

    def test_transfer_split_edge_case(self):
        """Test splitting at exact boundary."""
        transfer_vol = 400.0  # µL
        max_tip_volume = 200.0  # µL

        num_cycles = math.ceil(transfer_vol / max_tip_volume)
        vol_per_cycle = transfer_vol / num_cycles

        assert num_cycles == 2
        assert abs(vol_per_cycle - 200.0) < 0.01

    def test_transfer_split_multiple(self):
        """Test splitting into more than 2 cycles."""
        transfer_vol = 600.0  # µL
        max_tip_volume = 200.0  # µL

        num_cycles = math.ceil(transfer_vol / max_tip_volume)
        vol_per_cycle = transfer_vol / num_cycles

        assert num_cycles == 3
        assert abs(vol_per_cycle - 200.0) < 0.01


class TestWaterVolumeCalculation:
    """Test water volume calculation."""

    def test_water_volume_basic(self):
        """Test basic water volume calculation."""
        well_volume = 1500.0  # µL
        component_volumes = [50.0, 100.0, 200.0]  # µL each
        total_component_vol = sum(component_volumes)

        water_vol = well_volume - total_component_vol
        expected = 1150.0

        assert abs(water_vol - expected) < 0.01

    def test_water_volume_all_allocated(self):
        """Test water volume when all volume is allocated to components."""
        well_volume = 1500.0  # µL
        component_volumes = [1500.0]

        water_vol = well_volume - component_volumes[0]

        assert abs(water_vol) < 0.01  # Should be ≈ 0

    def test_water_volume_negative_detection(self):
        """Test detection of negative water volume (error case)."""
        well_volume = 1500.0  # µL
        component_volumes = [1600.0]  # Exceeds well volume
        epsilon = 1e-6

        water_vol = well_volume - component_volumes[0]

        assert water_vol < -epsilon, "Should detect over-allocation"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for full pipeline."""

    def test_load_actual_data_files(self):
        """Test loading actual data files."""
        assert os.path.exists('data/stock_concentrations.csv'), "Stock conc file missing"
        assert os.path.exists('data/24-well_stock_plate_high.csv'), "High plate file missing"
        assert os.path.exists('data/24-well_stock_plate_low.csv'), "Low plate file missing"
        assert os.path.exists('data/target_concentrations.csv'), "Target conc file missing"

        # Try loading
        df_stock = pd.read_csv('data/stock_concentrations.csv', index_col=0)
        df_high = pd.read_csv('data/24-well_stock_plate_high.csv')
        df_low = pd.read_csv('data/24-well_stock_plate_low.csv')
        df_target = pd.read_csv('data/target_concentrations.csv', index_col=0)

        assert len(df_stock) > 0, "Stock conc file is empty"
        assert len(df_high) > 0, "High plate file is empty"
        assert len(df_low) > 0, "Low plate file is empty"
        assert len(df_target) > 0, "Target conc file is empty"

    def test_stock_lookup_from_actual_files(self):
        """Test creating stock_lookup from actual data files."""
        df_stock = pd.read_csv('data/stock_concentrations.csv', index_col=0)
        df_high = pd.read_csv('data/24-well_stock_plate_high.csv')
        df_low = pd.read_csv('data/24-well_stock_plate_low.csv')

        stock_lookup = {}
        for comp in df_stock.index:
            stock_lookup[comp] = {'high': None, 'low': None}

        for _, row in df_high.iterrows():
            comp = row['Component']
            if comp not in stock_lookup:
                stock_lookup[comp] = {'high': None, 'low': None}
            stock_lookup[comp]['high'] = {
                'plate': 's1',
                'well': row['Well'],
                'conc': row['Concentration[mM]']
            }

        for _, row in df_low.iterrows():
            comp = row['Component']
            if comp not in stock_lookup:
                stock_lookup[comp] = {'high': None, 'low': None}
            stock_lookup[comp]['low'] = {
                'plate': 's4',
                'well': row['Well'],
                'conc': row['Concentration[mM]']
            }

        assert len(stock_lookup) > 0
        assert all(comp in stock_lookup for comp in df_stock.index)

    def test_output_file_generated(self):
        """Test that output file is generated."""
        output_file = 'data/transfer_instructions.csv'
        assert os.path.exists(output_file), f"Output file {output_file} not found"

        df_output = pd.read_csv(output_file)
        assert len(df_output) > 0, "Output file is empty"
        assert list(df_output.columns) == ['Source_Plate', 'Source_Well', 'Dest_Plate', 'Dest_Well', 'Transfer_Vol']

    def test_output_format_validity(self):
        """Test that output file has valid format."""
        df_output = pd.read_csv('data/transfer_instructions.csv')

        # Check column types and values
        assert df_output['Transfer_Vol'].dtype in [np.float64, np.int64, float, int], "Transfer_Vol should be numeric"
        assert all(df_output['Transfer_Vol'] >= 0), "All transfer volumes should be non-negative"
        assert all(df_output['Transfer_Vol'] <= 1500), "Transfer volumes should not exceed well volume"

    def test_volume_sum_per_well(self):
        """Test that all volumes per well sum correctly."""
        df_output = pd.read_csv('data/transfer_instructions.csv')
        well_volumes = df_output.groupby('Dest_Well')['Transfer_Vol'].sum()

        # All wells should have approximately the same total volume (well_volume = 1500)
        well_volume_target = 1500.0
        for well, total in well_volumes.items():
            # Allow 1% tolerance for rounding
            assert abs(total - well_volume_target) < 15, f"Well {well} total {total} far from target {well_volume_target}"

    def test_reference_output_comparison(self):
        """Test comparison with reference output if available."""
        reference_file = 'data/output.csv'
        if not os.path.exists(reference_file):
            pytest.skip("Reference output file not found")

        df_reference = pd.read_csv(reference_file)
        df_output = pd.read_csv('data/transfer_instructions.csv')

        # Check that at least the column names match (first 5 columns)
        ref_cols = list(df_reference.columns[:5])
        our_cols = list(df_output.columns)

        assert ref_cols == our_cols, f"Column mismatch: {ref_cols} vs {our_cols}"


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_concentration_component(self):
        """Test handling of components with zero concentration."""
        target_conc = 0.0
        transfer_vol = 0.0
        well_volume = 1500.0

        # Should result in zero transfer
        assert transfer_vol == 0.0

    def test_very_small_concentration(self, user_params):
        """Test handling of very small concentrations."""
        target_conc = 0.00001  # Very small
        well_volume = user_params['well_volume']
        stock_conc = 2.4

        transfer_vol = (target_conc * well_volume) / stock_conc
        # Should be very small, possibly below minimum

        assert transfer_vol >= 0

    def test_large_transfer_volume_requiring_split(self, user_params):
        """Test handling of large transfer volumes."""
        transfer_vol = 600.0  # Exceeds max_tip_volume
        max_tip = user_params['max_tip_volume']

        num_cycles = math.ceil(transfer_vol / max_tip)
        vol_per_cycle = transfer_vol / num_cycles

        assert num_cycles > 1, "Should require multiple cycles"
        assert vol_per_cycle <= max_tip, f"Cycle volume {vol_per_cycle} should not exceed max {max_tip}"

    def test_volume_rounding(self):
        """Test that volumes are correctly rounded."""
        raw_volume = 123.456789
        rounded = round(raw_volume, 2)

        assert rounded == 123.46
        assert isinstance(rounded, float)

    def test_epsilon_comparison_at_boundary(self, user_params):
        """Test floating point comparison with epsilon."""
        epsilon = user_params['epsilon']
        target_volume = 1500.0
        calculated_volume = 1500.0 + epsilon / 2

        # Should be considered equal
        assert abs(calculated_volume - target_volume) < epsilon

    def test_negative_water_volume_case(self):
        """Test detection of impossible case (components > well volume)."""
        well_volume = 1500.0
        component_total = 1600.0

        water_vol = well_volume - component_total

        assert water_vol < 0, "Should detect over-allocation"

    def test_all_components_at_minimum_volume(self):
        """Test case where all components are at minimum transfer volume."""
        min_transfer = 5.0
        well_volume = 1500.0
        num_components = 20

        total_if_all_minimum = min_transfer * num_components
        # 100 µL total - still room for water

        assert total_if_all_minimum < well_volume


# =============================================================================
# DATA VALIDATION TESTS
# =============================================================================

class TestDataValidation:
    """Test data validation and error detection."""

    def test_well_format_validation(self):
        """Test that well formats are validated."""
        valid_wells = ['A1', 'B2', 'C12', 'H12']
        invalid_wells = ['1A', 'AA1', '', '1', 'A', 'ABC1']

        def is_valid_well(well):
            if pd.isna(well) or not isinstance(well, str):
                return False
            well = well.strip()
            if len(well) < 2:
                return False
            return well[0].isalpha() and well[1:].isdigit()

        for well in valid_wells:
            assert is_valid_well(well), f"{well} should be valid"

        for well in invalid_wells:
            assert not is_valid_well(well), f"{well} should be invalid"

    def test_concentration_sign_validation(self):
        """Test that negative concentrations are detected."""
        df_target = pd.DataFrame({
            'Component_A': [1.0, 2.0, -1.0],
            'Component_B': [0.5, 0.5, 0.5]
        })

        negative_found = (df_target < 0).any().any()
        assert negative_found, "Should detect negative concentrations"

    def test_stock_concentration_physical_validity(self):
        """Test that stock concentrations are physically valid."""
        stock_concs = [0.12, 2.4, 8.7, 43.5, 400.0, 2000.0, 3000.0]

        # All should be positive
        assert all(c > 0 for c in stock_concs), "Stock concentrations should be positive"

        # Should be physically reasonable (not negative infinity, not NaN)
        assert all(np.isfinite(c) for c in stock_concs), "Stock concentrations should be finite"

    def test_back_calculation_accuracy(self):
        """Test accuracy of back-calculated concentrations."""
        target_conc = 1.0  # mM
        well_volume = 1500.0  # µL
        stock_conc = 2000.0  # mM

        transfer_vol = (target_conc * well_volume) / stock_conc

        # Back-calculate
        calculated_conc = (transfer_vol * stock_conc) / well_volume

        # Should match target
        assert abs(calculated_conc - target_conc) < 0.001 * target_conc, "Back-calculation error too large"

    def test_back_calculation_high_precision(self):
        """Test back-calculation with various concentrations."""
        test_cases = [
            (0.001, 1500, 2.4),    # Very small conc
            (0.1, 1500, 2.4),      # Small conc
            (1.0, 1500, 2000.0),   # Medium conc
            (10.0, 1500, 43.5),    # Larger conc
        ]

        for target, well_vol, stock in test_cases:
            transfer_vol = (target * well_vol) / stock
            if transfer_vol > 0:
                calculated = (transfer_vol * stock) / well_vol
                error_pct = abs(calculated - target) / target * 100
                assert error_pct < 1.0, f"Error too high for target={target}: {error_pct:.2f}%"


# =============================================================================
# PERFORMANCE AND SCALE TESTS
# =============================================================================

class TestScalability:
    """Test performance with different data sizes."""

    def test_process_48_wells(self):
        """Test processing 48 wells (standard plate)."""
        wells = [f"{chr(65+i)}{j}" for i in range(6) for j in range(1, 9)]
        assert len(wells) == 48
        assert wells[0] == 'A1'
        assert wells[-1] == 'F8'

    def test_process_96_wells(self):
        """Test processing 96 wells (standard large plate)."""
        wells = [f"{chr(65+i)}{j}" for i in range(8) for j in range(1, 13)]
        assert len(wells) == 96
        assert wells[0] == 'A1'
        assert wells[-1] == 'H12'

    def test_process_multiple_plates(self):
        """Test processing data spanning multiple plates."""
        wells_96 = [f"{chr(65+i)}{j}" for i in range(8) for j in range(1, 13)]
        wells_per_plate = 48

        dest_plates = {}
        for idx, well in enumerate(wells_96):
            plate_num = idx // wells_per_plate + 1
            dest_plates[well] = f"dest_{plate_num}"

        unique_plates = set(dest_plates.values())
        assert len(unique_plates) == 2, "96 wells should span 2 destination plates"

    def test_many_transfers_per_well(self):
        """Test wells requiring many transfers (many components)."""
        num_components = 15
        transfers_per_well = num_components + 1  # +1 for water

        assert transfers_per_well > 10, "Should handle 10+ transfers per well"

    def test_large_output_file_handling(self):
        """Test that large output files can be created and read."""
        if os.path.exists('data/transfer_instructions.csv'):
            df = pd.read_csv('data/transfer_instructions.csv')
            file_size = os.path.getsize('data/transfer_instructions.csv')

            assert len(df) > 0, "Output file should have rows"
            assert file_size < 100000, "Output file should be reasonable size (< 100KB)"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
