import math
from dataclasses import dataclass

@dataclass(frozen=True)
class GearSpec:
    teeth: int
    module_mm: float | None
    pd_inv_in: float | None
    pressure_angle_deg: float
    addendum_factor: float = 1.0
    dedendum_factor: float = 1.25

    def is_metric(self) -> bool:
        return self.module_mm is not None and self.module_mm > 0

    def is_pd(self) -> bool:
        return self.pd_inv_in is not None and self.pd_inv_in > 0

    def validate(self):
        if self.teeth < 6:
            raise ValueError("Teeth must be >= 6")
        if not (self.is_metric() ^ self.is_pd()):
            raise ValueError("Choose either module (mm) OR Pd (1/in)")
        if self.pressure_angle_deg <= 0 or self.pressure_angle_deg >= 45:
            raise ValueError("Pressure angle must be between 0 and 45 deg")

@dataclass(frozen=True)
class GearGeom:
    teeth: int
    phi_rad: float
    pitch_diam: float
    pitch_rad: float
    base_rad: float
    addendum: float
    dedendum: float
    addendum_rad: float
    root_rad: float
    circular_pitch: float
    base_pitch: float
    outside_diam: float
    root_diam: float
    base_diam: float

def module_from_pd(pd_inv_in: float) -> float:
    return 25.4 / pd_inv_in

def pd_from_module(module_mm: float) -> float:
    return 25.4 / module_mm

def gear_geom(spec: GearSpec) -> GearGeom:
    spec.validate()
    phi = math.radians(spec.pressure_angle_deg)

    if spec.is_metric():
        m = float(spec.module_mm)
        pitch_d = m * spec.teeth
        circular_pitch = math.pi * m
        addendum = spec.addendum_factor * m
        dedendum = spec.dedendum_factor * m
    else:
        Pd = float(spec.pd_inv_in)
        pitch_d = spec.teeth / Pd
        circular_pitch = math.pi / Pd
        addendum = spec.addendum_factor / Pd
        dedendum = spec.dedendum_factor / Pd

    r = pitch_d / 2.0
    rb = r * math.cos(phi)
    ra = r + addendum
    rr = max(0.05 * r, r - dedendum)
    base_pitch = circular_pitch * math.cos(phi)

    outside_d = 2.0 * ra
    root_d = 2.0 * rr
    base_d = 2.0 * rb

    return GearGeom(
        teeth=spec.teeth,
        phi_rad=phi,
        pitch_diam=pitch_d,
        pitch_rad=r,
        base_rad=rb,
        addendum=addendum,
        dedendum=dedendum,
        addendum_rad=ra,
        root_rad=rr,
        circular_pitch=circular_pitch,
        base_pitch=base_pitch,
        outside_diam=outside_d,
        root_diam=root_d,
        base_diam=base_d
    )

def center_distance(g1: GearGeom, g2: GearGeom) -> float:
    return g1.pitch_rad + g2.pitch_rad

def contact_ratio(g1: GearGeom, g2: GearGeom) -> float:
    r1, r2 = g1.pitch_rad, g2.pitch_rad
    rb1, rb2 = g1.base_rad, g2.base_rad
    ra1, ra2 = g1.addendum_rad, g2.addendum_rad
    phi = g1.phi_rad

    term1 = math.sqrt(max(0.0, ra1 * ra1 - rb1 * rb1))
    term2 = math.sqrt(max(0.0, ra2 * ra2 - rb2 * rb2))
    L = term1 + term2 - (r1 + r2) * math.sin(phi)
    if g1.base_pitch <= 1e-12:
        return 0.0
    return L / g1.base_pitch

def rpm_chain(teeth_list: list[int], rpm_in: float) -> list[float]:
    rpms = [rpm_in]
    for i in range(1, len(teeth_list)):
        z_prev = teeth_list[i - 1]
        z_cur = teeth_list[i]
        rpms.append(-rpms[-1] * (z_prev / z_cur))
    return rpms

def ang_vel_from_rpm(rpm: float) -> float:
    return rpm * 2.0 * math.pi / 60.0

def pitch_line_velocity(pitch_diam: float, rpm: float) -> float:
    return math.pi * pitch_diam * rpm / 60.0

def ratio_simplified(a: int, b: int) -> tuple[int, int]:
    a = abs(int(a))
    b = abs(int(b))
    if a == 0 or b == 0:
        return (a, b)
    x, y = a, b
    while y:
        x, y = y, x % y
    g = max(1, x)
    return (a // g, b // g)

def pair_ratio_text(z_from: int, z_to: int) -> str:
    p, q = ratio_simplified(z_from, z_to)
    return f"{z_from}:{z_to} ({p}:{q})"

def overall_ratio_text(z_in: int, z_out: int) -> str:
    p, q = ratio_simplified(z_in, z_out)
    return f"{z_in}:{z_out} ({p}:{q})"

def chain_speed_factor(teeth_list: list[int]) -> float:
    if not teeth_list:
        return 0.0
    z1 = float(teeth_list[0])
    zn = float(teeth_list[-1])
    sgn = -1.0 if ((len(teeth_list) - 1) % 2 == 1) else 1.0
    return sgn * (z1 / zn)

def solve_motor_rpm_for_target_output(teeth_list: list[int], rpm_out_target: float) -> float:
    k = chain_speed_factor(teeth_list)
    if abs(k) < 1e-12:
        return 0.0
    return rpm_out_target / k