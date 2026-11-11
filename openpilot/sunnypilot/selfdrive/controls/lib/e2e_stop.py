"""
FORK(HONDA_ACCORD_9G_AU): the red-light stop entry.

With a lead, the MPC candidate asks to stop below the car's STOPPING_SPEED (0.8 m/s, stopping_tune.py), and the stopping
state - its 0.8 m/s^3 ramp and the soft stop's ceiling (opendbc elesys_stop.py) - brings the car to rest. At a red light
there is no lead: the MPC follows a fake one 50 m ahead and cruise is positive, so the only stop request is the model's
own, which modeld hard-codes to v_ego < 0.3 m/s. Measured on the 4 hands-off red-light stops (12b 470.7, 142 263.7,
161 147.6, 170 233.0): the stopping state began at 0.28-0.29 m/s, 0.01-0.08 s before the wheels read zero, so the last
1.6-1.75 m below 1 m/s ran 2.5-3.4 s in the PID state on the model's crawl (-0.2 to -0.4 m/s^2) plus an integrator wound
to +0.25..+0.56 m/s^2 - the "lift" - and the car rested 0.66-0.77 m past where the plan, at 0.8 m/s, said it would.

WHAT: the e2e candidate also asks to stop when should_stop(v_ego, a_e2e, STOPPING_SPEED) holds (v_ego < 0.8 and the
model's accel < 0.1, exactly the MPC's rule) AND the model's own plan is below E2E_STOP_PLAN_V at E2E_STOP_PLAN_T - the
model itself means to stop, not to crawl on. Once on it stays on (latched) for as long as should_stop holds, so a plan
that recedes as the car slows cannot drop the stop at 0.5 m/s; it lets go the moment the model's accel reaches 0.1 or
the car is back above 0.8 m/s, which is when the MPC's own rule would. The model's own flag is passed through untouched.

Measured on every rlog route with modelV2 (45 routes, d1..161): on true stops it fires at 0.77-0.80 m/s, the same moment
the MPC's rule fires behind a lead; it never fired on an approach that went on to keep rolling (161 126.9 s, where the
plain v<0.8/a<0.1 rule would have, has the plan at 0.84 m/s 2 s out). Built only on this car with openpilot longitudinal,
stock ACC mode off and HondaDynamicTuningEnabled on - the switch the soft stop is built with - because without the soft
stop's ceiling an earlier stopping state is the old harsh stop (0.92 m/s^2 at rest). Every other car: None, upstream.

LOG: one `e2estop on v= a= deg= model=` line per engagement, on the frame it latches (plannerd's cloudlog, which reaches
the route as a logMessage): the speed and the model's accel at the latch, the grade in degrees, and whether the model's
own flag was already on. It is written after the latch is decided and cannot change it.
"""
import math

import numpy as np

from openpilot.selfdrive.controls.lib.drive_helpers import should_stop
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib.stopping_tune import STOPPING_SPEED
from openpilot.sunnypilot.selfdrive.controls.lib.reentry_ramp import reentry_ramp_applies

E2E_STOP_PLAN_T = 2.0      # s: how far out the model's plan must already be below E2E_STOP_PLAN_V
E2E_STOP_PLAN_V = 0.3      # m/s: the model's own stop speed (modeld: v_ego < 0.3)
# The grade band (carControl.orientationNED pitch, nose-up positive) the early stop is asked in. The stopping state's
# target is stopAccel -0.8 on the flat and carries no grade term: on a downhill steeper than ~2.5 deg it holds less than
# the PID's integrator would (replayed: 1.04-1.45 m from 0.8 m/s at -2..-3 deg against 0.8-0.95 on the flat), and on an
# uphill the 105-count ceiling plus gravity stops harder than the 0.5-0.6 m/s^2 round 8 chose (replayed: 0.49-0.74 at
# +1 deg, 0.66-0.84 at +2). Outside it - or with no pitch at all - the stop is today's (the model's own 0.3 m/s).
# All 54 clean stops on record were within -2.5..+2.6 deg; 3 were above +1.
E2E_STOP_PITCH_MIN = -0.044   # rad (-2.5 deg)
E2E_STOP_PITCH_MAX = 0.0175   # rad (+1.0 deg)


def plan_comes_to_rest(plan_vx) -> bool:
  """True when the model's 33-point speed plan (modelV2.velocity.x over T_IDXS) is below E2E_STOP_PLAN_V at
  E2E_STOP_PLAN_T. A missing, short or non-finite plan never is."""
  try:
    vx = np.asarray(list(plan_vx), dtype=float)
  except (TypeError, ValueError):
    return False
  if vx.shape != (len(ModelConstants.T_IDXS),) or not np.isfinite(vx).all():
    return False
  return bool(np.interp(E2E_STOP_PLAN_T, ModelConstants.T_IDXS, vx) < E2E_STOP_PLAN_V)


def grade_ok(pitch) -> bool:
  try:
    p = float(pitch)
  except (TypeError, ValueError):
    return False
  return bool(E2E_STOP_PITCH_MIN <= p <= E2E_STOP_PITCH_MAX)


class E2EStopEntry:
  def __init__(self, v_ego_stopping: float):
    self.v_ego_stopping = v_ego_stopping
    self.latched = False
    self.log_line = None     # one line per engagement (the frame it latches), for plannerd's cloudlog, like stop_gap's

  def update(self, v_ego: float, a_target_e2e: float, model_should_stop: bool, plan_vx, active: bool, pitch=None) -> bool:
    """The e2e candidate's should_stop. `active`: experimental mode (is_e2e) and long control not reset. `pitch`: rad,
    nose-up positive; the stop is only latched ON inside the grade band (once on, a grade change does not drop it)."""
    self.log_line = None
    was_latched = self.latched
    try:
      if not active or not should_stop(v_ego, a_target_e2e, v_ego_stopping=self.v_ego_stopping):
        self.latched = False
      elif not self.latched:
        self.latched = grade_ok(pitch) and plan_comes_to_rest(plan_vx)
    except Exception:
      self.latched = False                 # never raise in plannerd: the model's own flag still stands
    if self.latched and not was_latched:
      try:                                 # the log line only: it cannot change the latch
        self.log_line = (f"e2estop on v={float(v_ego):.2f} a={float(a_target_e2e):.2f} " +
                         f"deg={math.degrees(float(pitch)):.2f} model={int(bool(model_should_stop))}")
      except Exception:
        self.log_line = None
    return bool(model_should_stop or self.latched)


def e2e_stop_applies(CP, CP_SP) -> bool:
  """This car (a STOPPING_SPEED entry), openpilot longitudinal, stock ACC mode off, HondaDynamicTuningEnabled on."""
  try:
    if CP.carFingerprint not in STOPPING_SPEED or not reentry_ramp_applies(CP, CP_SP):
      return False
    from openpilot.common.params import Params
    return Params().get_bool("HondaDynamicTuningEnabled")
  except Exception:
    return False
