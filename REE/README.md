# Liquid Handler Transfer File Generator

## Overview

This project contains a Jupyter Notebook (`transfer.ipynb`) designed to generate transfer instructions for automated liquid handlers. It calculates the necessary volumes of stock solutions to transfer to destination wells to achieve specific target concentrations.

## Purpose

The script automates the calculation of liquid handling instructions, specifically:
-   Calculating transfer volumes from stock solutions to destination wells.
-   Selecting between high and low-concentration stocks based on minimum volume requirements.
-   Calculating the necessary amount of water to reach the target total volume.
-   Generating a CSV file compatible with liquid handlers.

## Project Structure

```
.
├── transfer.ipynb          # Main application notebook
├── requirements.txt        # Python dependencies
└── data/                   # Input and output data directory
    ├── stock_concentrations_REE.csv      # Components and stock concentrations
    ├── 24-well_stock_plate_high.csv      # Layout of high-concentration stock plate
    ├── 24-well_stock_plate_low.csv       # Layout of low-concentration stock plate
    ├── target_concentrations.csv         # Desired concentrations for destination wells
    └── transfer_instructions.csv         # (Output) Generated instructions for the liquid handler
```

## Setup and Installation

1.  **Prerequisites**: Ensure you have Python installed.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Prepare Input Data**:
    Ensure your input CSV files are correctly placed in the `data/` directory. The scripts expect:
    -   Stock concentrations
    -   Plate layouts (High/Low)
    -   Target concentrations

2.  **Run the Notebook**:
    -   Launch Jupyter Notebook:
        ```bash
        jupyter notebook
        ```
    -   Open `transfer.ipynb`.
    -   Review **Section 2: User Parameters** to adjust configuration settings (e.g., `well_volume`, `min_transfer_volume`).
    -   Run all cells to generate the output.

3.  **Output**:
    The script will generate `data/transfer_instructions.csv`, which contains the commands for the liquid handler.
    Columns: `Source_Plate`, `Source_Well`, `Dest_Plate`, `Dest_Well`, `Transfer_Vol`.

## Configuration

You can adjust the following parameters within the notebook:
-   **Liquid Handling Constraints**: `well_volume`, `dead_volume`, `min_transfer_volume`, `max_tip_volume`.
-   **Plate Formats**: Supports 24-well and 96-well formats.
-   **Stock Management**: Configuration for depletion thresholds and automatic well switching.

## License

[Insert License Information Here]
