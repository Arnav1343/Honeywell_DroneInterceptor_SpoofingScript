"""
countermeasure_analyzer.py
==========================
Models all 16 GPS spoofing detection vectors and scores evasion.

Updated to reflect selective NW-quadrant satellite spoofing
as the primary AoA countermeasure.
"""

import math
import logging


class CountermeasureAnalyzer:
    """
    Analyzes evasion effectiveness against all known detection systems.

    Each analyze method returns:
        evaded: bool
        risk_score: int 0-100 (0=fully evaded, 100=certain detection)
        status: EVADED / PARTIAL / DETECTED
        reason: str
        countermeasure_used: str
    """

    def __init__(self, attack_params):
        """
        Args:
            attack_params dict keys:
                power_ramp_db_per_sec: float
                num_transmit_antennas: int
                spoofable_satellite_count: int
                jammable_satellite_count: int
                interceptor_azimuth_deg: float
                azimuth_tolerance_deg: float
                real_signal_suppressed: bool
                constellations_jammed: list
                vertical_error_m: float
                drift_per_step_m: float
                max_safe_drift_m: float
                pseudorange_consistency_m: float
                drift_rate_ms: float
                imu_noise_ms: float
                receiver_has_osnma: bool
                num_receive_antennas: int
                num_crpa_elements: int
                selective_spoofing_active: bool
        """
        self.params = attack_params
        self.logger = logging.getLogger('CountermeasureAnalyzer')

    def _result(self, evaded, risk, reason, countermeasure):
        status = ('EVADED' if risk < 25 else
                  'PARTIAL' if risk < 60 else 'DETECTED')
        return {
            'evaded': evaded,
            'risk_score': risk,
            'status': status,
            'reason': reason,
            'countermeasure_used': countermeasure
        }

    def analyze_cn0(self):
        """C/N0 monitoring — carrier to noise ratio anomaly detection."""
        ramp = self.params.get('power_ramp_db_per_sec', 0.6)
        if ramp <= 1.0:
            return self._result(
                True, 8,
                f'Ramp rate {ramp} dB/s below 1.0 threshold',
                'Min-power gradual takeover 0.6 dB/s'
            )
        return self._result(
            False, 65,
            f'Ramp rate {ramp} dB/s exceeds safe threshold',
            'Reduce ramp rate'
        )

    def analyze_agc(self):
        """AGC monitoring — automatic gain control anomaly."""
        ramp = self.params.get('power_ramp_db_per_sec', 0.6)
        if ramp < 1.0:
            return self._result(
                True, 12,
                'AGC change below detection threshold',
                'Gradual 0.6 dB/s ramp within atmospheric variation'
            )
        return self._result(
            False, 70,
            'AGC change too rapid',
            'Reduce ramp rate below 1.0 dB/s'
        )

    def analyze_aoa(self):
        """
        Angle of Arrival detection.

        UPDATED: Selective NW-quadrant spoofing defeats AoA by only
        transmitting signals for satellites whose real positions are
        within 45 degrees of the interceptor azimuth (315 NW).
        Every spoofed signal arrives from a geometrically plausible
        sky direction making AoA indistinguishable from real reception.
        """
        selective = self.params.get('selective_spoofing_active', True)
        spoofable_count = self.params.get('spoofable_satellite_count', 4)
        interceptor_az = self.params.get('interceptor_azimuth_deg', 315.0)
        tolerance = self.params.get('azimuth_tolerance_deg', 45.0)
        crpa_elements = self.params.get('num_crpa_elements', 0)

        if selective and spoofable_count >= 4:
            if crpa_elements == 0:
                return self._result(
                    True, 5,
                    f'Selective spoofing: only NW satellites '
                    f'({interceptor_az}° ±{tolerance}°) spoofed. '
                    f'All signals arrive from geometrically correct '
                    f'sky positions. AoA sees plausible directions.',
                    'Selective NW-quadrant satellite spoofing'
                )
            elif crpa_elements <= 4:
                return self._result(
                    True, 30,
                    f'CRPA {crpa_elements} elements present but NW '
                    f'selective spoofing creates null steering dilemma — '
                    f'nulling interceptor also attenuates real satellites '
                    f'at similar elevation angles.',
                    'Selective spoofing + geometric CRPA dilemma'
                )
            else:
                return self._result(
                    False, 55,
                    f'Full CRPA {crpa_elements} elements — partial defeat. '
                    f'Selective spoofing reduces detectability but '
                    f'military CRPA may still null the source.',
                    'Selective spoofing (partial against military CRPA)'
                )
        else:
            return self._result(
                False, 80,
                'Single source spoofing — all signals from one direction',
                'Enable selective NW-quadrant spoofing'
            )

    def analyze_doppler(self):
        """Doppler consistency — per-satellite Doppler variation."""
        spoofable = self.params.get('spoofable_satellite_count', 4)
        if spoofable >= 4:
            return self._result(
                True, 5,
                'Per-satellite Doppler computed independently from '
                'orbital mechanics. Each spoofed PRN has unique shift.',
                'Independent per-satellite Doppler computation'
            )
        return self._result(False, 75, 'Insufficient satellites', '')

    def analyze_correlator(self):
        """Correlator distortion — signal quality monitoring."""
        suppressed = self.params.get('real_signal_suppressed', True)
        if suppressed:
            return self._result(
                True, 3,
                'Non-NW real signals jammed before takeover. '
                'NW satellites taken over via gradual power ramp. '
                'No simultaneous overlap — clean correlation peaks.',
                'Selective jamming eliminates correlator interference'
            )
        return self._result(
            False, 55,
            'Real signal overlap causes correlation distortion',
            'Apply selective jamming of non-NW satellites'
        )

    def analyze_multi_constellation(self):
        """Multi-constellation cross-check."""
        jammed = self.params.get('constellations_jammed', [])
        if 'GLONASS' in jammed and 'BeiDou' in jammed:
            return self._result(
                True, 8,
                'GLONASS and BeiDou suppressed. Target GPS-only.',
                'Selective constellation jamming'
            )
        elif len(jammed) > 0:
            return self._result(
                True, 35,
                f'Partial suppression: {jammed}',
                'Partial constellation jamming'
            )
        return self._result(
            False, 70,
            'Multi-constellation cross-check active',
            'Jam GLONASS and BeiDou'
        )

    def analyze_barometric(self):
        """Barometric altitude cross-check."""
        vert_err = self.params.get('vertical_error_m', 0.2)
        if vert_err < 0.5:
            return self._result(
                True, 2,
                f'Vertical error {vert_err:.2f}m below 0.5m threshold. '
                'Horizontal-only pseudorange constraint applied.',
                'Constrained least-squares horizontal-only offsets'
            )
        return self._result(
            False, 60,
            f'Vertical error {vert_err:.2f}m exceeds barometric threshold',
            'Apply horizontal-only pseudorange constraint'
        )

    def analyze_ekf_innovation(self):
        """EKF innovation rejection."""
        drift = self.params.get('drift_per_step_m', 0.02)
        max_safe = self.params.get('max_safe_drift_m', 1.25)
        margin = max_safe - drift

        if drift < max_safe * 0.4:
            return self._result(
                True, 15,
                f'Drift {drift:.3f}m/step well within gate '
                f'({max_safe:.2f}m). 60% safety margin maintained.',
                f'Adaptive 0.2-0.5 m/s drift rate, 40% safety margin'
            )
        elif drift < max_safe:
            return self._result(
                True, 35,
                f'Drift {drift:.3f}m/step within gate but low margin',
                'Reduce drift rate'
            )
        return self._result(
            False, 85,
            f'Drift {drift:.3f}m/step exceeds innovation gate',
            'Reduce drift rate below max_safe * 0.4'
        )

    def analyze_raim(self):
        """RAIM pseudorange consistency check."""
        consistency = self.params.get('pseudorange_consistency_m', 0.15)
        if consistency < 0.3:
            return self._result(
                True, 10,
                f'Pseudorange consistency {consistency:.3f}m below threshold. '
                'All offsets computed from single coherent position solution.',
                'Simultaneous consistent pseudorange updates all PRNs'
            )
        return self._result(
            False, 65,
            f'Pseudorange inconsistency {consistency:.3f}m exceeds 0.3m',
            'Enforce geometric consistency across all spoofed PRNs'
        )

    def analyze_ins_aided(self):
        """INS-aided tracking — IMU cross-check."""
        drift = self.params.get('drift_rate_ms', 0.3)
        imu_noise = self.params.get('imu_noise_ms', 0.15)

        if drift < imu_noise * 0.8:
            return self._result(
                True, 15,
                f'Drift {drift} m/s below IMU noise {imu_noise} m/s. '
                'EKF cannot distinguish from sensor noise.',
                'Drift rate kept below IMU noise floor'
            )
        elif drift < imu_noise * 1.5:
            return self._result(
                True, 40,
                f'Drift {drift} m/s slightly above IMU noise',
                'Reduce drift or wait for maneuver phase'
            )
        return self._result(
            False, 75,
            f'Drift {drift} m/s significantly exceeds IMU noise {imu_noise}',
            'Reduce drift rate or use maneuver windows'
        )

    def analyze_clock_reference(self):
        """Clock reference timing attack."""
        return self._result(
            True, 4,
            'Carry-off starts synchronized with real GPS time. '
            'Clock bias evolves within TCXO drift bounds naturally.',
            'Carry-off synchronization — no artificial clock jump'
        )

    def analyze_nmea(self):
        """NMEA sentence integrity monitoring."""
        return self._result(
            True, 2,
            'Gradual smooth drift produces valid NMEA output. '
            'No position jumps, no velocity discontinuities.',
            'Sub-meter per step smooth coordinate walk'
        )

    def analyze_ml_detection(self):
        """ML-based anomaly detection (LSTM, SVM)."""
        return self._result(
            True, 45,
            'Carry-off has different statistical signature than '
            'synthesis-based spoofing that most ML detectors train on. '
            'Partial evasion — adaptive classifiers may learn.',
            'Carry-off statistical signature differs from training data'
        )

    def analyze_osnma(self):
        """OSNMA/Chimera signal authentication."""
        has_osnma = self.params.get('receiver_has_osnma', False)
        if not has_osnma:
            return self._result(
                True, 18,
                'Target receiver does not implement OSNMA. '
                'Vast majority of commercial UAVs unprotected.',
                'Target consumer/prosumer receiver without authentication'
            )
        return self._result(
            False, 95,
            'OSNMA active — cryptographic authentication defeats spoofing. '
            'Zero-delay relay attack only option.',
            'Zero-delay relay (limited — timestamp window)'
        )

    def analyze_multiple_receivers(self):
        """Multiple spatially separated GPS receivers."""
        num_recv = self.params.get('num_receive_antennas', 1)
        if num_recv < 2:
            return self._result(
                True, 5,
                'Single GPS antenna — no spatial comparison possible.',
                'Target single-antenna receiver (standard on consumer UAVs)'
            )
        return self._result(
            False, 60,
            f'{num_recv} spatially separated antennas can compare phases',
            'Cooperative multi-interceptor spoofing'
        )

    def analyze_crpa(self):
        """CRPA spatial filtering."""
        crpa = self.params.get('num_crpa_elements', 0)
        selective = self.params.get('selective_spoofing_active', True)

        if crpa == 0:
            return self._result(
                True, 5,
                'No CRPA present.',
                'N/A'
            )
        elif crpa <= 4 and selective:
            return self._result(
                True, 30,
                f'CRPA {crpa} elements. Selective NW spoofing creates '
                f'geometric null-steering dilemma — nulling interceptor '
                f'attenuates real NW satellites simultaneously.',
                'Selective spoofing exploits CRPA geometric constraints'
            )
        elif crpa <= 6 and selective:
            return self._result(
                True, 50,
                f'CRPA {crpa} elements — partial defeat via geometry.',
                'Selective spoofing partial'
            )
        return self._result(
            False, 80,
            f'Full military CRPA {crpa} elements likely defeats approach',
            'Cooperative multi-interceptor or physical interception'
        )

    def run_full_analysis(self):
        """Run all 16 analyzers and compute overall score."""
        results = {
            'cn0_monitoring': self.analyze_cn0(),
            'agc_monitoring': self.analyze_agc(),
            'aoa_detection': self.analyze_aoa(),
            'doppler_consistency': self.analyze_doppler(),
            'correlator_distortion': self.analyze_correlator(),
            'multi_constellation': self.analyze_multi_constellation(),
            'barometric_crosscheck': self.analyze_barometric(),
            'ekf_innovation': self.analyze_ekf_innovation(),
            'raim': self.analyze_raim(),
            'ins_aided': self.analyze_ins_aided(),
            'clock_reference': self.analyze_clock_reference(),
            'nmea_integrity': self.analyze_nmea(),
            'ml_detection': self.analyze_ml_detection(),
            'osnma': self.analyze_osnma(),
            'multiple_receivers': self.analyze_multiple_receivers(),
            'crpa': self.analyze_crpa()
        }

        scores = [r['risk_score'] for r in results.values()]
        overall = sum(scores) / len(scores)

        failed = [name for name, r in results.items()
                  if r['status'] == 'DETECTED']
        partial = [name for name, r in results.items()
                   if r['status'] == 'PARTIAL']

        results['_summary'] = {
            'overall_score': round(overall, 1),
            'evasion_score': round(100 - overall, 1),
            'failed_countermeasures': failed,
            'partial_countermeasures': partial,
            'go': overall < 35
        }

        return results

    def generate_report(self):
        """Print formatted countermeasure evasion report."""
        results = self.run_full_analysis()
        summary = results.pop('_summary')

        print(f"\n{'='*80}")
        print(f"  COUNTERMEASURE EVASION REPORT")
        print(f"{'='*80}")
        print(f"\n{'Countermeasure':<30} | {'Status':<8} | "
              f"{'Risk':>5} | Method")
        print("-" * 80)

        status_symbols = {
            'EVADED': '✓',
            'PARTIAL': '~',
            'DETECTED': '✗'
        }

        for name, result in results.items():
            sym = status_symbols.get(result['status'], '?')
            display_name = name.replace('_', ' ').title()
            method_short = result['countermeasure_used'][:35]
            print(f"{display_name:<30} | "
                  f"{sym} {result['status']:<6} | "
                  f"{result['risk_score']:>4}/100 | "
                  f"{method_short}")

        print("-" * 80)
        print(f"\nOverall Evasion Score: "
              f"{summary['evasion_score']:.1f}/100")

        if summary['go']:
            print(f"STATUS: GO ✓ — Proceed with attack")
        else:
            print(f"STATUS: NO-GO ✗ — Review flagged countermeasures")

        if summary['failed_countermeasures']:
            print(f"\nFailed: {', '.join(summary['failed_countermeasures'])}")
        if summary['partial_countermeasures']:
            print(f"Partial: {', '.join(summary['partial_countermeasures'])}")

        print(f"\nAoA Note: Selective NW-quadrant spoofing (315° ±45°)")
        print(f"  All spoofed signals arrive from geometrically plausible")
        print(f"  sky positions. AoA detection sees legitimate geometry.")

        return results