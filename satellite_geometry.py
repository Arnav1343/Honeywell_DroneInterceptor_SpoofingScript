"""
satellite_geometry.py
=====================
GPS satellite position computation, Doppler calculation,
pseudorange modeling, and satellite classification by
interceptor azimuth for AoA-defeating selective spoofing.
"""

import math
import time
import numpy as np
from scipy import linalg


GPS_L1_FREQ = 1575.42e6
GPS_L2_FREQ = 1227.60e6
CA_CHIP_RATE = 1.023e6
SPEED_OF_LIGHT = 299792458.0
EARTH_RADIUS = 6371000.0
GPS_ORBITAL_RADIUS = 26560000.0
GPS_ORBITAL_VELOCITY = 3874.0
EARTH_ROTATION_RATE = 7.2921150e-5
MU_EARTH = 3.986004418e14


class SatelliteGeometry:
    """
    Computes GPS satellite positions, Doppler shifts, pseudoranges,
    and classifies satellites for AoA-defeating selective spoofing.
    """

    def __init__(self, config):
        self.lat = math.radians(config['mission']['start_lat'])
        self.lon = math.radians(config['mission']['start_lon'])
        self.alt = config['mission']['start_alt']
        self._init_orbital_params()

    def _init_orbital_params(self):
        """Initialize simplified orbital parameters for PRN 1-32."""
        self.orbital_params = {}
        planes = 6
        sats_per_plane = 4
        raan_spacing = 2 * math.pi / planes
        anomaly_spacing = 2 * math.pi / sats_per_plane

        prn = 1
        for plane in range(planes):
            for slot in range(sats_per_plane):
                if prn > 32:
                    break
                self.orbital_params[prn] = {
                    'semi_major_axis': GPS_ORBITAL_RADIUS,
                    'inclination': math.radians(55.0),
                    'raan': plane * raan_spacing,
                    'mean_anomaly': slot * anomaly_spacing + plane * 0.52,
                    'eccentricity': 0.0
                }
                prn += 1

    def prn_to_ecef(self, prn, gps_time=None):
        """
        Compute satellite ECEF position for given PRN.

        Args:
            prn: satellite PRN number 1-32
            gps_time: GPS time in seconds, uses time.time() if None

        Returns:
            numpy array [x, y, z] in meters
        """
        if gps_time is None:
            gps_time = time.time()

        params = self.orbital_params.get(prn, self.orbital_params[1])
        a = params['semi_major_axis']
        inc = params['inclination']
        raan = params['raan']
        m0 = params['mean_anomaly']

        n = math.sqrt(MU_EARTH / (a ** 3))
        M = m0 + n * gps_time
        E = M

        for _ in range(10):
            E = M + params['eccentricity'] * math.sin(E)

        x_orb = a * math.cos(E)
        y_orb = a * math.sin(E)

        cos_raan = math.cos(raan + EARTH_ROTATION_RATE * gps_time)
        sin_raan = math.sin(raan + EARTH_ROTATION_RATE * gps_time)
        cos_inc = math.cos(inc)
        sin_inc = math.sin(inc)

        x = cos_raan * x_orb - sin_raan * cos_inc * y_orb
        y = sin_raan * x_orb + cos_raan * cos_inc * y_orb
        z = sin_inc * y_orb

        return np.array([x, y, z])

    def observer_ecef(self, lat=None, lon=None, alt=None):
        """
        Convert observer lat/lon/alt to ECEF coordinates.

        Returns:
            numpy array [x, y, z] in meters
        """
        lat = lat if lat is not None else self.lat
        lon = lon if lon is not None else self.lon
        alt = alt if alt is not None else self.alt

        a = 6378137.0
        f = 1 / 298.257223563
        e2 = 2 * f - f ** 2
        N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)

        x = (N + alt) * math.cos(lat) * math.cos(lon)
        y = (N + alt) * math.cos(lat) * math.sin(lon)
        z = (N * (1 - e2) + alt) * math.sin(lat)

        return np.array([x, y, z])

    def ecef_to_azel(self, sat_ecef, observer_ecef=None):
        """
        Convert satellite ECEF position to azimuth/elevation/range
        from observer position.

        Returns:
            tuple (azimuth_deg, elevation_deg, range_m)
        """
        if observer_ecef is None:
            observer_ecef = self.observer_ecef()

        diff = sat_ecef - observer_ecef
        range_m = np.linalg.norm(diff)

        lat = self.lat
        lon = self.lon

        R = np.array([
            [-math.sin(lat) * math.cos(lon),
             -math.sin(lat) * math.sin(lon),
             math.cos(lat)],
            [-math.sin(lon), math.cos(lon), 0],
            [math.cos(lat) * math.cos(lon),
             math.cos(lat) * math.sin(lon),
             math.sin(lat)]
        ])

        enu = R @ diff
        e, n, u = enu

        elevation = math.degrees(math.asin(u / range_m))
        azimuth = math.degrees(math.atan2(e, n)) % 360

        return azimuth, elevation, range_m

    def get_doppler_shift(self, prn, receiver_velocity_ned):
        """
        Compute Doppler shift in Hz for given PRN.

        Args:
            prn: satellite PRN number
            receiver_velocity_ned: [vn, ve, vd] in m/s

        Returns:
            Doppler shift in Hz, range approximately -4500 to +4500
        """
        obs_ecef = self.observer_ecef()
        sat_ecef = self.prn_to_ecef(prn)
        sat_ecef_dt = self.prn_to_ecef(prn, time.time() + 1.0)

        sat_velocity = sat_ecef_dt - sat_ecef
        los_vector = (sat_ecef - obs_ecef)
        los_unit = los_vector / np.linalg.norm(los_vector)

        lat, lon = self.lat, self.lon
        R = np.array([
            [-math.sin(lat) * math.cos(lon),
             -math.sin(lon),
             math.cos(lat) * math.cos(lon)],
            [-math.sin(lat) * math.sin(lon),
             math.cos(lon),
             math.cos(lat) * math.sin(lon)],
            [math.cos(lat), 0, math.sin(lat)]
        ])

        vn, ve, vd = receiver_velocity_ned
        recv_ecef = R @ np.array([vn, ve, vd])

        relative_velocity = np.dot(sat_velocity - recv_ecef, los_unit)
        doppler = -relative_velocity / SPEED_OF_LIGHT * GPS_L1_FREQ

        return doppler

    def compute_pseudorange(self, prn, receiver_ecef=None):
        """
        Compute pseudorange including atmospheric delays.

        Returns:
            pseudorange in meters
        """
        if receiver_ecef is None:
            receiver_ecef = self.observer_ecef()

        sat_ecef = self.prn_to_ecef(prn)
        geometric_range = np.linalg.norm(sat_ecef - receiver_ecef)

        _, elevation, _ = self.ecef_to_azel(sat_ecef, receiver_ecef)
        elev_rad = math.radians(max(elevation, 5.0))

        iono_delay = 5.0 + 10.0 * math.cos(
            2 * math.pi * (elevation - 90) / 180)
        tropo_delay = 2.3 / (math.sin(elev_rad) + 0.05)

        return geometric_range + iono_delay + tropo_delay

    def get_visible_satellites(self, min_elevation=10.0):
        """
        Get all satellites above minimum elevation angle.

        Returns:
            list of dicts sorted by elevation descending, each containing:
            {prn, elevation_deg, azimuth_deg, range_m, doppler_hz, pseudorange_m}
        """
        obs_ecef = self.observer_ecef()
        visible = []

        for prn in range(1, 33):
            sat_ecef = self.prn_to_ecef(prn)
            az, el, rng = self.ecef_to_azel(sat_ecef, obs_ecef)

            if el >= min_elevation:
                doppler = self.get_doppler_shift(prn, [0.0, 0.0, 0.0])
                pseudorange = self.compute_pseudorange(prn, obs_ecef)

                visible.append({
                    'prn': prn,
                    'elevation_deg': round(el, 2),
                    'azimuth_deg': round(az, 2),
                    'range_m': round(rng, 1),
                    'doppler_hz': round(doppler, 2),
                    'pseudorange_m': round(pseudorange, 2),
                    'snr_db': round(35.0 - max(0, 20 - el) * 0.5, 1)
                })

        return sorted(visible, key=lambda s: s['elevation_deg'], reverse=True)

    def classify_satellites_by_interceptor_position(
            self,
            visible_sats,
            interceptor_azimuth_deg=315.0,
            azimuth_tolerance_deg=45.0,
            min_spoofable=4):
        """
        Classify satellites as SPOOF or JAM based on azimuth proximity
        to interceptor position. Core of AoA defeat strategy.

        Satellites within azimuth_tolerance of interceptor_azimuth are
        spoofable because their signals naturally arrive from the same
        direction as the interceptor making AoA detection impossible to
        distinguish from legitimate reception.

        Args:
            visible_sats: output of get_visible_satellites()
            interceptor_azimuth_deg: interceptor azimuth from target (315=NW)
            azimuth_tolerance_deg: half-window for spoofable satellites
            min_spoofable: minimum satellites needed for valid position fix

        Returns:
            (spoofable_list, jammable_list) each with 'role' key added
        """
        def azimuth_diff(az1, az2):
            diff = abs(az1 - az2) % 360
            return min(diff, 360 - diff)

        spoofable = []
        jammable = []

        for sat in visible_sats:
            diff = azimuth_diff(
                sat['azimuth_deg'], interceptor_azimuth_deg)
            sat_copy = dict(sat)
            sat_copy['azimuth_diff_deg'] = round(diff, 2)

            if diff <= azimuth_tolerance_deg:
                sat_copy['role'] = 'SPOOF'
                spoofable.append(sat_copy)
            else:
                sat_copy['role'] = 'JAM'
                jammable.append(sat_copy)

        if len(spoofable) < min_spoofable:
            jammable_sorted = sorted(
                jammable, key=lambda s: s['azimuth_diff_deg'])
            needed = min_spoofable - len(spoofable)

            for sat in jammable_sorted[:needed]:
                sat['role'] = 'SPOOF'
                sat['role_reason'] = 'promoted_for_minimum_fix'
                spoofable.append(sat)
                jammable.remove(sat)

        return spoofable, jammable

    def compute_horizontal_only_offsets(
            self, target_lat, target_lon,
            current_lat, current_lon):
        """
        Compute per-PRN pseudorange offsets producing purely horizontal
        displacement with under 0.3m vertical error.

        Uses constrained least squares with satellite geometry matrix.

        Returns:
            dict {prn: offset_meters}
        """
        obs_ecef = self.observer_ecef(
            math.radians(current_lat),
            math.radians(current_lon),
            self.alt
        )
        target_ecef = self.observer_ecef(
            math.radians(target_lat),
            math.radians(target_lon),
            self.alt
        )

        delta_ecef = target_ecef - obs_ecef
        delta_ecef[2] = 0.0

        visible = self.get_visible_satellites()
        offsets = {}

        for sat in visible:
            prn = sat['prn']
            sat_ecef = self.prn_to_ecef(prn)
            los = sat_ecef - obs_ecef
            los_unit = los / np.linalg.norm(los)
            offsets[prn] = float(np.dot(delta_ecef, los_unit))

        return offsets

    def get_geometry_matrix(self, visible_sats):
        """
        Build geometry matrix H for RAIM consistency checking.

        Returns:
            numpy array shape (N, 4) where N is number of satellites
        """
        obs_ecef = self.observer_ecef()
        rows = []

        for sat in visible_sats:
            sat_ecef = self.prn_to_ecef(sat['prn'])
            los = sat_ecef - obs_ecef
            los_unit = los / np.linalg.norm(los)
            rows.append([-los_unit[0], -los_unit[1], -los_unit[2], 1.0])

        return np.array(rows)