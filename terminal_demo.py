#!/usr/bin/env python3
"""
terminal_demo.py
================
Replays the DP5 GPS spoofing simulation with rich colored terminal output.
Pure simulation — no MAVLink connection needed.

Designed for screen recording or standalone demonstration.
Uses colorama for cross-platform colored output.
"""

import sys
import os
import time
import math
import random

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
except ImportError:
    print("Installing colorama...")
    os.system("pip install colorama")
    from colorama import init, Fore, Back, Style
    init(autoreset=True)


# ================================================================
# CONSTANTS
# ================================================================
ORIGIN_LAT = 12.9716
ORIGIN_LON = 77.5946
SAFE_LAT = 12.975000
SAFE_LON = 77.598000
METERS_PER_LAT = 1.0 / 111320.0
METERS_PER_LON = 1.0 / (111320.0 * math.cos(math.radians(ORIGIN_LAT)))


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def typewriter(text, cps=50):
    """Print text character by character at cps (chars per second)."""
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(1.0 / cps)
    print()


def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


# ================================================================
# MAIN DEMO
# ================================================================

def main():
    clear_screen()

    # ─── BANNER ───
    banner = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║      DP5: DRONE INTERCEPTOR WITH GRADUAL GPS SPOOFING       ║",
        "║              Honeywell Design-A-Thon 2026                    ║",
        "╚══════════════════════════════════════════════════════════════╝",
    ]
    print()
    for line in banner:
        typewriter(Fore.CYAN + Style.BRIGHT + line, cps=80)
        time.sleep(0.1)

    print()
    time.sleep(1.0)

    # ─── PHASE 1: RECONNAISSANCE ───
    print(Fore.CYAN + Style.BRIGHT + "=== PHASE 1: RECONNAISSANCE ===")
    time.sleep(0.5)
    print(Fore.WHITE + "[SAT] Scanning GPS constellation...")
    time.sleep(0.5)

    header = "PRN  | Elevation | Azimuth | Doppler (Hz) | Pseudorange (m) | Status"
    sep =    "-----|-----------|---------|--------------|-----------------|--------"
    print(Fore.WHITE + header)
    print(Fore.WHITE + sep)

    sats = [
        ("PRN1", "42.3°", "127.4°", "+1842 Hz", "20,245,312 m"),
        ("PRN2", "67.8°", " 45.2°", "-2103 Hz", "20,112,847 m"),
        ("PRN3", "23.1°", "234.7°", "+3421 Hz", "20,378,901 m"),
        ("PRN4", "55.4°", "312.8°", "-1205 Hz", "20,198,234 m"),
        ("PRN5", "38.9°", " 89.3°", "+2876 Hz", "20,301,456 m"),
        ("PRN6", "71.2°", "178.5°", "-3102 Hz", "20,089,123 m"),
        ("PRN7", "29.7°", "267.1°", "+1543 Hz", "20,412,789 m"),
        ("PRN8", "48.6°", " 23.9°", "-2234 Hz", "20,156,678 m"),
    ]
    for prn, elev, azim, dopp, pr in sats:
        print(Fore.WHITE + f"{prn} |   {elev}   |  {azim} |    {dopp}  |   {pr}  | " +
              Fore.GREEN + "LOCKED")
        time.sleep(0.1)

    print(Fore.GREEN + "[SAT] 8 satellites acquired. Signal quality: EXCELLENT")
    print()
    time.sleep(1.0)

    # ─── PHASE 2: CONSTELLATION SUPPRESSION ───
    print(Fore.CYAN + Style.BRIGHT + "=== PHASE 2: CONSTELLATION SUPPRESSION ===")
    time.sleep(0.3)

    jam_lines = [
        ("[JAM] Targeting GLONASS L1 band (1598-1606 MHz)...    ", "[ACTIVE]"),
        ("[JAM] Targeting BeiDou B1 band (1561.098 MHz)...      ", "[ACTIVE]"),
        ("[JAM] Galileo E1 (1575.42 MHz) — shared with GPS L1   ", "[SUPPRESSED]"),
    ]
    for prefix, status in jam_lines:
        color = Fore.GREEN if "ACTIVE" in status else Fore.YELLOW
        print(Fore.WHITE + prefix + color + status)
        time.sleep(0.3)

    print(Fore.WHITE + "[SYS] Target receiver forced to GPS-only mode")
    time.sleep(0.2)
    print(Fore.WHITE + "[SYS] Multi-constellation cross-check: " + Fore.RED + "DISABLED")
    print()
    time.sleep(1.0)

    # ─── PHASE 3: CARRY-OFF SYNCHRONIZATION ───
    print(Fore.CYAN + Style.BRIGHT + "=== PHASE 3: CARRY-OFF SYNCHRONIZATION ===")
    time.sleep(0.3)
    print(Fore.WHITE + "[SYNC] Locking to real GPS signal...")
    time.sleep(0.3)

    sync_data = [
        ("PRN1", "847.3", "+1842 Hz", "+1"),
        ("PRN2", "234.7", "-2103 Hz", "-1"),
        ("PRN3", "612.1", "+3421 Hz", "+1"),
        ("PRN4", "423.9", "-1205 Hz", "-1"),
        ("PRN5", "156.4", "+2876 Hz", "+1"),
        ("PRN6", "789.2", "-3102 Hz", "-1"),
        ("PRN7", "534.8", "+1543 Hz", "+1"),
        ("PRN8", "901.3", "-2234 Hz", "-1"),
    ]
    for prn, cp, dopp, nav in sync_data:
        print(Fore.WHITE + f"{prn} | Code phase: {cp} chips | Doppler: {dopp} | Nav bit: {nav} | " +
              Fore.GREEN + "SYNCHRONIZED")
        time.sleep(0.15)

    print(Fore.GREEN + "[SYNC] All 8 satellites synchronized — signals bit-perfect with real GPS")
    time.sleep(0.2)
    print(Fore.GREEN + "[SYNC] Carrier phase lock achieved — ready for power takeover")
    print()
    time.sleep(1.0)

    # ─── PHASE 4: POWER TAKEOVER ───
    print(Fore.CYAN + Style.BRIGHT + "=== PHASE 4: POWER TAKEOVER ===")
    time.sleep(0.3)
    print(Fore.WHITE + "[PWR] Ramping transmit power...")
    time.sleep(0.3)

    pwr_steps = [
        (-6, 0.0, "REAL SATELLITES", Fore.WHITE),
        (-5, 0.1, "REAL SATELLITES", Fore.WHITE),
        (-4, 0.2, "TRANSITIONING", Fore.YELLOW),
        (-3, 0.4, "TRANSITIONING", Fore.YELLOW),
        (-2, 0.6, "TRANSITIONING", Fore.YELLOW),
        (-1, 0.8, "SPOOFED SIGNALS", Fore.RED),
        (0,  0.9, "SPOOFED SIGNALS ✓", Fore.RED),
    ]
    for db, agc, status, color in pwr_steps:
        print(Fore.WHITE + f"  {db:3d} dB | AGC delta: {agc:.1f} dB/s | Receiver lock: " +
              color + status)
        time.sleep(0.3)

    print(Fore.GREEN + Style.BRIGHT + "[PWR] Takeover complete — controlling target GPS receiver")
    print()
    time.sleep(1.0)

    # ─── PHASE 5: COORDINATE WALK ───
    print(Fore.CYAN + Style.BRIGHT + "=== PHASE 5: COORDINATE WALK — GPS SPOOFING ACTIVE ===")
    time.sleep(0.3)
    print(Fore.WHITE + "[SPOOF] Carry-off spoofing initiated")
    print(Fore.WHITE + f"[SPOOF] Target: Safe Area Alpha ({SAFE_LAT:.6f}, {SAFE_LON:.6f})")
    print(Fore.WHITE + "[SPOOF] Drift rate: 0.20 → 0.50 m/s (adaptive)")
    print(Fore.WHITE + "[SPOOF] EKF innovation gate: 2.5m")
    print()

    header = " Time  |    Real Position     |   Spoofed Position   | Error  | Drift  | To Safe  | EKF"
    sep =    "-------|----------------------|----------------------|--------|--------|----------|------"
    print(Fore.WHITE + header)
    print(Fore.WHITE + sep)

    # Simulate spoofing data
    real_lat = 12.971600
    real_lon = 77.594700
    spoof_lat = real_lat
    spoof_lon = real_lon
    drift = 0.200
    rows_printed = 0

    for t_idx in range(121):
        t = float(t_idx)

        # Update drift rate
        if t > 10:
            drift = min(drift + 0.003, 0.500)

        # Move spoofed position toward safe area
        brg = math.atan2(SAFE_LON - spoof_lon, SAFE_LAT - spoof_lat)
        step = drift * 1.0  # 1 second step
        dlat = step * math.cos(brg) * METERS_PER_LAT
        dlon = step * math.sin(brg) * METERS_PER_LON
        spoof_lat += dlat
        spoof_lon += dlon

        # Real position barely moves
        real_lat += random.uniform(-0.0000005, 0.0000008)
        real_lon += random.uniform(-0.0000003, 0.0000005)

        # Calculate error
        error = math.sqrt(
            ((spoof_lat - real_lat) / METERS_PER_LAT) ** 2 +
            ((spoof_lon - real_lon) / METERS_PER_LON) ** 2
        )

        dist_safe = haversine_m(spoof_lat, spoof_lon, SAFE_LAT, SAFE_LON)

        # EKF status
        if error < 1.0:
            ekf = Fore.GREEN + "ACCEPT"
        elif random.random() < 0.15:
            ekf = Fore.YELLOW + " WARN "
        else:
            ekf = Fore.GREEN + "ACCEPT"

        row = (Fore.WHITE +
               f" {t:5.1f}s | ({real_lat:.6f},{real_lon:.6f}) | "
               f"({spoof_lat:.6f},{spoof_lon:.6f}) | "
               f"{error:5.1f}m | {drift:.3f} | {dist_safe:7.1f}m | " + ekf)
        print(row)
        rows_printed += 1

        # Reprint headers every 20 rows
        if rows_printed % 20 == 0 and t_idx < 119:
            time.sleep(0.3)
            print(Fore.WHITE + sep)

        time.sleep(0.5)

    print()
    time.sleep(1.0)

    # ─── PHASE 6: EKF FALLBACK ───
    print(Fore.CYAN + Style.BRIGHT + "=== PHASE 6: EKF FALLBACK — MAGNETOMETER SPOOFING ===")
    time.sleep(0.3)

    mag_lines = [
        "[MAG] GPS loss detected — switching to magnetometer spoofing",
        "[MAG] Earth field strength: 50.0 μT (South India, inclination 27°)",
        "[MAG] Computing redirect heading to safe area...",
        "[MAG] Required heading: 44.7° (NE toward safe area)",
        "[MAG] Rotating apparent north: 0° → 44.7° at 5.0°/s",
        "[MAG] Estimated redirect time: 8.9 seconds",
    ]
    for line in mag_lines:
        print(Fore.WHITE + line)
        time.sleep(0.3)
    print(Fore.GREEN + Style.BRIGHT + "[MAG] Redirect complete — drone heading toward safe area")
    print()
    time.sleep(1.0)

    # ─── COUNTERMEASURE EVASION REPORT ───
    print(Fore.CYAN + Style.BRIGHT + "=== COUNTERMEASURE EVASION REPORT ===")
    time.sleep(0.3)

    cm_header = "Countermeasure          | Status   | Risk Score | Method"
    cm_sep =    "------------------------|----------|------------|---------------------------"
    print(Fore.WHITE + cm_header)
    print(Fore.WHITE + cm_sep)

    countermeasures = [
        ("C/N₀ Monitoring        ", "EVADED ", "  8/100", "Min-power takeover"),
        ("AGC Monitoring         ", "EVADED ", " 12/100", "0.6 dB/s ramp rate"),
        ("AoA Detection          ", "PARTIAL", " 35/100", "4-antenna array"),
        ("Doppler Consistency    ", "EVADED ", "  5/100", "Per-satellite Doppler"),
        ("Correlator Distortion  ", "EVADED ", "  3/100", "Real signal suppressed"),
        ("Multi-Constellation    ", "EVADED ", "  8/100", "GLONASS+BeiDou jammed"),
        ("Barometric Cross-check ", "EVADED ", "  2/100", "Horizontal-only drift"),
        ("EKF Innovation         ", "EVADED ", " 15/100", "Adaptive 0.2-0.5 m/s"),
        ("RAIM                   ", "EVADED ", " 10/100", "Pseudorange consistency"),
        ("INS-Aided Tracking     ", "PARTIAL", " 40/100", "Consumer IMU exploited"),
        ("Clock Reference        ", "EVADED ", "  4/100", "Carry-off synchronized"),
        ("NMEA Integrity         ", "EVADED ", "  2/100", "Gradual smooth drift"),
        ("ML Detection           ", "PARTIAL", " 45/100", "Carry-off signature"),
        ("OSNMA/Chimera          ", "EVADED ", " 18/100", "Receiver unprotected"),
        ("Multiple Receivers     ", "EVADED ", "  5/100", "Single-antenna target"),
        ("CRPA Systems           ", "PARTIAL", " 38/100", "No CRPA on target"),
    ]

    for name, status, risk, method in countermeasures:
        if "EVADED" in status:
            sc = Fore.GREEN
        elif "PARTIAL" in status:
            sc = Fore.YELLOW
        else:
            sc = Fore.RED
        print(Fore.WHITE + f"{name} | " + sc + f"{status}" +
              Fore.WHITE + f" |    {risk}  | {method}")
        time.sleep(0.15)

    print()
    print(Fore.GREEN + Style.BRIGHT + "Overall Evasion Score: 86.2 / 100 — GO ✓")
    print()
    time.sleep(1.0)

    # ─── MISSION COMPLETE ───
    print(Fore.CYAN + Style.BRIGHT + "=== MISSION COMPLETE ===")
    time.sleep(0.3)
    final = [
        f"Total drift achieved: {error:.1f}m toward safe area",
        f"Final distance to safe area: {dist_safe:.1f}m",
        "GPS injections delivered: 1,200",
        "Mission duration: 127.4 seconds",
    ]
    for line in final:
        print(Fore.WHITE + line)
        time.sleep(0.2)

    print(Fore.GREEN + Style.BRIGHT + "STATUS: MISSION SUCCESS ✓")
    print()


if __name__ == "__main__":
    main()
