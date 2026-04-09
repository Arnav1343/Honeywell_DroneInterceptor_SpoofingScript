# Honeywell Drone Interceptor - GPS Spoofing Toolkit

This repository contains the `gps_spoofing_v2` toolkit, an advanced approach to drone interception using GPS spoofing techniques.

## Repository Structure

- `gps_spoofing_v2/`: Contains the refined scenario orchestration and probe detection logic.
- `*.py`: Core logic files including `satellite_geometry.py`, `ekf_model.py`, `drift_planner.py`, and more.
- `config.yaml`: Central configuration for simulation and attack parameters.

## Key Features

- **Selective Spoofing**: Defeats AoA detection by selectively spoofing quadrant-specific satellites.
- **Terrain Masking**: Resolves barometric sensor fusion conflicts via terrain-correlated route planning.
- **Adaptive Drift Control**: Optimizes spoofing rates to stay below target EKF innovation gates.

## Usage

Run the scenario runner from the `gps_spoofing_v2` directory:
```bash
python3 gps_spoofing_v2/scenario_runner.py
```

## Research Context

Developed as part of the Research Project for advanced GPS spoofing and security analysis.
