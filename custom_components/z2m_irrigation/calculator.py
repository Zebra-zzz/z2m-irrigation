"""VPD-driven irrigation calculator.

v4.0-alpha-1 — pure-Python port of the existing template-helper formula
that has been running in the user's HA configuration for the last several
months. Lifted verbatim so that v4.0 produces identical numbers to the
legacy stack while it runs in parallel.

Formula:
    dryness  = clamp(0.85 + vpd_kpa / 3.0, 0.8, 1.5)
    need_mm  = max(0, base_mm * dryness - rain_today_mm - 0.7 * fc24_mm)
    liters   = need_mm * factor * l_per_mm

Inputs that are missing or unavailable are treated as neutral:
    vpd_kpa missing       → 1.0 kPa  (≈ dryness 1.18, slightly thirsty)
    rain_today_mm missing → 0.0 mm
    fc24_mm missing       → 0.0 mm

The calculator does no I/O. The integration's `weather.py` helper is
responsible for reading sensor states and producing a `WeatherInputs`
struct, which is then handed in here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .zone_store import ZoneConfig


# ─────────────────────────────────────────────────────────────────────────────
# Defaults applied when inputs are missing
# ─────────────────────────────────────────────────────────────────────────────

NEUTRAL_VPD_KPA = 1.0
NEUTRAL_RAIN_MM = 0.0
NEUTRAL_FC24_MM = 0.0

DRYNESS_FLOOR = 0.8
DRYNESS_CEIL = 1.5
DRYNESS_BASELINE = 0.85
DRYNESS_VPD_DIVISOR = 3.0
FORECAST_DAMPENING = 0.7  # 70% of forecasted rain is subtracted from need


@dataclass
class WeatherInputs:
    """Resolved weather inputs for a single calculator run."""
    vpd_kpa: Optional[float]
    rain_today_mm: Optional[float]
    fc24_mm: Optional[float]
    temp_c: Optional[float] = None  # display only

    @property
    def effective_vpd(self) -> float:
        return self.vpd_kpa if self.vpd_kpa is not None else NEUTRAL_VPD_KPA

    @property
    def effective_rain_today(self) -> float:
        return self.rain_today_mm if self.rain_today_mm is not None else NEUTRAL_RAIN_MM

    @property
    def effective_fc24(self) -> float:
        return self.fc24_mm if self.fc24_mm is not None else NEUTRAL_FC24_MM


@dataclass
class ZoneCalc:
    """Per-zone calculator output."""
    zone: str
    base_mm: float
    factor: float
    l_per_mm: float
    dryness: float
    need_mm: float
    liters: float
    skipped: bool
    skip_reason: Optional[str]  # "below_min_run" | "not_in_smart_cycle" | None


@dataclass
class CalculatorResult:
    """Aggregate result of a calculator run, ready to render and to act on."""
    weather: WeatherInputs
    dryness: float                   # global dryness factor (same for all zones)
    zones: List[ZoneCalc]
    total_liters: float
    runnable_zones: int              # count of zones with liters > 0 and not skipped


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_dryness(vpd_kpa: float) -> float:
    """Pure formula — exposed for unit tests and the dashboard."""
    return _clamp(
        DRYNESS_BASELINE + (vpd_kpa / DRYNESS_VPD_DIVISOR),
        DRYNESS_FLOOR,
        DRYNESS_CEIL,
    )


def compute(
    zones: dict[str, ZoneConfig],
    weather: WeatherInputs,
    global_min_run_liters: float,
) -> CalculatorResult:
    """Run the full calculator over a set of zones.

    Args:
        zones: mapping of zone friendly_name → ZoneConfig
        weather: resolved weather inputs (with `None`s for missing sensors)
        global_min_run_liters: fallback minimum-run threshold for zones
            that don't have their own override

    Returns:
        CalculatorResult with per-zone breakdown and a total.
    """
    vpd = weather.effective_vpd
    rain = weather.effective_rain_today
    fc24 = weather.effective_fc24
    dryness = compute_dryness(vpd)

    out: List[ZoneCalc] = []
    total = 0.0
    runnable = 0

    for name, cfg in zones.items():
        # Zones not in the smart cycle still get a calc row (so the dashboard
        # can show "would have been Xl"), but they're flagged skipped.
        if not cfg.in_smart_cycle:
            out.append(
                ZoneCalc(
                    zone=name,
                    base_mm=cfg.base_mm,
                    factor=cfg.factor,
                    l_per_mm=cfg.l_per_mm,
                    dryness=dryness,
                    need_mm=0.0,
                    liters=0.0,
                    skipped=True,
                    skip_reason="not_in_smart_cycle",
                )
            )
            continue

        need_mm = max(0.0, cfg.base_mm * dryness - rain - FORECAST_DAMPENING * fc24)
        liters = need_mm * cfg.factor * cfg.l_per_mm

        min_run = (
            cfg.min_run_liters
            if cfg.min_run_liters is not None
            else global_min_run_liters
        )
        skipped = liters < min_run
        skip_reason = "below_min_run" if skipped else None

        out.append(
            ZoneCalc(
                zone=name,
                base_mm=cfg.base_mm,
                factor=cfg.factor,
                l_per_mm=cfg.l_per_mm,
                dryness=dryness,
                need_mm=round(need_mm, 3),
                liters=round(liters, 2),
                skipped=skipped,
                skip_reason=skip_reason,
            )
        )

        if not skipped:
            total += liters
            runnable += 1

    return CalculatorResult(
        weather=weather,
        dryness=dryness,
        zones=out,
        total_liters=round(total, 2),
        runnable_zones=runnable,
    )
