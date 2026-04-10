# Honeywell Drone Interceptor — GPS Spoofing Toolkit


> Advanced GPS spoofing and drone interception research toolkit with full SITL simulation.

---

## Overview

This project implements a two-drone GPS spoofing scenario:

- **Rogue drone** — flies an autonomous waypoint loop, gets progressively GPS-spoofed, and is guided to a designated safe area
- **Interceptor drone** — takes off, pursues the rogue, and maintains proximity during the spoofing sequence

The spoofing approach uses **carry-off (meaconing)** — synchronizing to the real GPS signal first, then gradually taking over the receiver by ramping transmit power — making the attack undetectable by AGC, C/N₀, and EKF innovation monitors.

---

## Repository Structure

```
.
├── carry_off.py              # Core carry-off GPS spoofing engine
├── satellite_geometry.py     # GPS satellite visibility & AoA geometry
├── countermeasure_analyzer.py # Scores evasion against 16 detection vectors
├── probe_detector.py         # Detects receiver probe/authentication attempts
├── main_diff.py              # Differential signal analysis
├── scenario_runner.py        # Orchestrates Scenario A & B demonstrations
├── config.yaml               # Central mission & attack parameters
└── terminal_demo.py          # Standalone terminal simulation (no MAVLink needed)
```

---

## Key Features

### Selective Satellite Spoofing (AoA Defeat)
Only satellites within ±45° of the interceptor's azimuth (NW, 315°) are spoofed. Their signals naturally arrive from the interceptor's physical direction, making angle-of-arrival detection indistinguishable from real GPS reception. Non-NW satellites are selectively jammed at low power.

### Carry-Off Synchronization
The spoofer locks onto real GPS signals (code phase, Doppler, nav bits) before transmitting. Power ramps at 0.6 dB/s — staying below AGC monitoring thresholds — until the receiver's lock transfers entirely to spoofed signals.

### Adaptive Drift Control
GPS coordinates are walked toward the safe area at 0.2–0.5 m/s, ramping gradually over ~100 seconds. The drift rate is capped below the target drone's EKF innovation gate (2.5 m) to avoid navigation alerts.

### Multi-Constellation Suppression
GLONASS L1 and BeiDou B1 are jammed, forcing the target receiver into GPS-only mode and disabling cross-constellation consistency checks.

### EKF Fallback — Magnetometer Spoofing
If the target drone loses GPS lock and switches to magnetometer-based navigation, a companion coil spoofs the apparent Earth magnetic field, rotating the drone's heading toward the safe area at 5°/s.

### Countermeasure Evasion
Scores **86.2/100** across 16 detection vectors including C/N₀ monitoring, AGC analysis, Doppler consistency, RAIM, OSNMA/Chimera, and ML-based detection.

---

## Quick Start

### Terminal Demo (no hardware required)

Runs a full animated simulation of the 6-phase attack directly in the terminal — no MAVLink, no Gazebo, no PX4 needed:

```bash
pip install colorama
python3 terminal_demo.py
```

The demo walks through:
1. **Reconnaissance** — satellite acquisition table (8 SVs)
2. **Constellation Suppression** — GLONASS/BeiDou jamming
3. **Carry-Off Synchronization** — bit-perfect signal lock
4. **Power Takeover** — AGC-safe ramp to receiver capture
5. **Coordinate Walk** — 121-step GPS drift to safe area
6. **Countermeasure Evasion Report** — per-vector risk scores

### Full SITL Simulation (PX4 + Gazebo Classic)

**Prerequisites:**
- PX4-Autopilot built at `~/PX4-Autopilot`
- Gazebo Classic with `sitl_gazebo-classic`
- `pymavlink`: `pip install pymavlink`

**Launch:**
```bash
# 1. Start Gazebo + both PX4 SITL instances
bash launch_sitl.sh

# 2. In a new terminal, run the mission
python3 dp5_mission.py
```

MAVLink ports:
| Instance | Role | Port |
|----------|------|------|
| 1 | Rogue drone | UDP 14541 |
| 2 | Interceptor drone | UDP 14542 |

### Scenario Runner (logic-only, no SITL)

```bash
pip install pyyaml numpy
python3 scenario_runner.py
```

Runs Scenario A (selective spoofing success) and Scenario B (terrain masking for barometric sensor fusion conflict) using the parameters in `config.yaml`.

---

## Configuration

All parameters are in `config.yaml`:

```yaml
spoofing:
  min_drift_rate_ms: 0.2       # m/s — start of coordinate walk
  max_drift_rate_ms: 0.5       # m/s — maximum drift speed
  power_ramp_db_per_sec: 0.6   # AGC-safe power increase rate
  ekf_safety_margin: 0.4       # fraction of EKF gate to stay under

mission:
  safe_area_lat: 12.9750       # destination latitude
  safe_area_lon: 77.5980       # destination longitude
  safe_area_radius_m: 10.0     # landing zone radius
```

---

## Attack Phases

```
Phase 1 — Reconnaissance             Acquire 8 GPS satellites, log signal parameters
Phase 2 — Constellation Suppression  Jam GLONASS + BeiDou, force GPS-only mode
Phase 3 — Carry-Off Sync             Lock code phase / Doppler / nav bits per-satellite
Phase 4 — Power Takeover             Ramp TX power at 0.6 dB/s → receiver capture
Phase 5 — Coordinate Walk            Drift spoofed position 0.2→0.5 m/s to safe area
Phase 6 — EKF Fallback               Magnetometer coil spoofing if GPS lock is lost
```

---

## Countermeasure Analysis

| Countermeasure | Status | Risk | Method |
|---|---|---|---|
| C/N₀ Monitoring | EVADED | 8/100 | Min-power takeover |
| AGC Monitoring | EVADED | 12/100 | 0.6 dB/s ramp rate |
| AoA Detection | PARTIAL | 35/100 | NW-quadrant satellite selection |
| Doppler Consistency | EVADED | 5/100 | Per-satellite Doppler match |
| Multi-Constellation | EVADED | 8/100 | GLONASS + BeiDou jammed |
| Barometric Cross-check | EVADED | 2/100 | Horizontal-only drift |
| EKF Innovation | EVADED | 15/100 | Adaptive 0.2–0.5 m/s |
| RAIM | EVADED | 10/100 | Pseudorange consistency |
| OSNMA/Chimera | EVADED | 18/100 | Unprotected receiver |
| ML Detection | PARTIAL | 45/100 | Carry-off signature |
| INS-Aided Tracking | PARTIAL | 40/100 | Consumer IMU exploited |

**Overall Evasion Score: 86.2 / 100**

---

## Research Context

Developed for the **Honeywell Design-A-Thon 2026** as part of a research initiative on GPS spoofing attack vectors and defensive countermeasures for UAV systems.
