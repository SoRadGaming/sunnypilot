"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Names, defaults and speed bands of the Honda Nidec dynamic longitudinal tuner.

Deliberately dependency-free: the settings panels (raylib), the small-screen
page, the sunnylink schema generator (which runs inside sunnylinkd) and the
tests all need these, and none of them should have to import the tuner itself
to get them. The tuner lives in opendbc -- a submodule, and one that drags in
the whole car stack -- so importing it from a settings screen would mean a
broken submodule takes the settings screen down with it.

Source of truth is _PARAM_SPEC in
opendbc/sunnypilot/car/honda/dynamic_tuning.py; the values below mirror it and
common/params_keys.h. selfdrive/ui/tests/test_honda_dynamic_settings.py fails
if the three ever drift apart.
"""

TUNING_PARAM = "HondaDynamicTuningEnabled"
PCM_BLEND_PARAM = "HondaDynamicPcmBlendEnabled"

# Speed breakpoints of the learned pedal gain, in m/s. Mirrors ELESYS_GAS_BP /
# PEDAL_GAIN_BP in opendbc/sunnypilot/car/honda/{gas_interceptor,dynamic_tuning}.py.
PEDAL_GAIN_BP = (0.0, 3.0, 6.0, 10.0, 15.0, 20.0)

LEARNED_DEFAULTS: dict[str, float] = {
  "HondaDynPedalGain0": 1.0,
  "HondaDynPedalGain1": 1.0,
  "HondaDynPedalGain2": 1.0,
  "HondaDynPedalGain3": 1.0,
  "HondaDynPedalGain4": 1.0,
  "HondaDynPedalGain5": 1.0,
  "HondaDynGasFactor": 1.0,
  "HondaDynGasAlpha": 0.0,
  "HondaDynAverageFactor": 0.95,
  "HondaDynSpeedFactor": 4.0,
  "HondaDynSpeedAlpha": 0.0,
  "HondaDynWindFactor": 1.0,
  "HondaDynBrakeGain": 0.0,
}

PEDAL_GAIN_KEYS = tuple(f"HondaDynPedalGain{i}" for i in range(len(PEDAL_GAIN_BP)))


def gain_meaning(value: float) -> str:
  """Plain-English gloss for a learned pedal gain, for the row description."""
  delta = (value - 1.0) * 100.0
  if abs(delta) < 0.5:
    return "nothing learned here yet"
  return f"{abs(delta):.0f}% {'more' if delta > 0 else 'less'} pedal than stock at this speed"
