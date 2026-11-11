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

AT REST (v_ego < E2E_STOP_STILL_V) the model's own flag decides: the latch is kept only while that flag is on, and no new
latch is taken. modeld computes its flag from the same rule (v < 0.3, accel < 0.1) on the UNSMOOTHED accel but publishes
the smoothed desiredAcceleration, so at a green light its flag drops 1-4 plans (up to ~0.3 s) before the smoothed accel
reaches 0.1; a latch held on the smoothed accel would hold the stop - and delay the launch - by that much (replayed on
182: 4 of 21 launches 0.10-0.14 s later). Below 0.1 m/s the stop is already made, so the launch is push18's exactly.
Not at 0.3 m/s: modeld's speed lags, and on the final roll its flag comes on a plan late (12b, 142).

THE PLAN THRESHOLD is 0.1 m/s (E2E_STOP_PLAN_V): the plan has come to rest, not merely slowed to modeld's 0.3. The
design used 0.3, and on every rlog route with modelV2 (45 routes, d1..161) it fired on true stops at 0.77-0.80 m/s, the
same moment the MPC's rule fires behind a lead - and on one approach that went on to keep rolling: 130 113.9 s, a
give-way at a right turn with no lead and no pedal, where the model slowed the car to 0.78 m/s with its plan at 0.18 m/s
2 s out (meaning to creep through) and asked to go 1.7 s later; with 0.3 the car would have stood still there for about
a second where it rolled through at 0.4 m/s. The owner chose 0.1 (the push19 review's option b). Re-run over the 114
rlog routes (103 with a pitch): 130 113.9 no longer latches, nor 9f 306.4 (a right-turn stop the car made anyway, now on
the model's own flag 0.9 s later) or de 518.6 (a roll-through behind a lead, the driver's gas 0.2 s later); every other
no-lead red-light and short stop latches on the same frame as with 0.3, and so does aa 437.8 (a light that turned green
during the crawl: its plan was 0.04 m/s). The cost: 161 145.8 s - the red light at 147.6 behind a lead pulling away, its
plan 0.14-0.21 m/s 2 s out - loses its early entry and is the model's own stop at 0.29 m/s again (the push19 replay had
it 0.21 m shorter); 170 233.0 (a qlog, 2 Hz) latches one model frame later, at 0.61 m/s instead of 0.76; 30 other
latches come later (29 behind a lead), 17 of them where the MPC's own rule already had the stop. Three more drop, none a
red light or short stop: 12b 231.6 and 181 531.1, where the MPC's rule or the model's flag already had the stop, and
20 3323.6, a queue stop at a turn behind a lead (the model's own flag 1.85 s later). 161 126.9 s, where the plain
v<0.8/a<0.1 rule would have fired, has the plan at 0.84 m/s 2 s out; 161 81.8 s is outside the grade band (+2.3 deg).

Built only on this car with openpilot longitudinal, stock ACC mode off and HondaDynamicTuningEnabled on - the switch the
soft stop is built with - because without the soft stop's ceiling an earlier stopping state is the old harsh stop
(0.92 m/s^2 at rest). Every other car: None, upstream.

LOG: one `e2estop on v= a= deg= model=` line per engagement, on the frame it latches (plannerd's cloudlog, which reaches
the route as a logMessage): the speed and the model's accel at the latch, the grade in degrees, and whether the model's
own flag was already on. It is written after the latch is decided and cannot change it. It never latches at rest, so
an engagement at a standstill writes no line.
"""
import math

import numpy as np

from openpilot.selfdrive.controls.lib.drive_helpers import should_stop
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib.stopping_tune import STOPPING_SPEED
from openpilot.sunnypilot.selfdrive.controls.lib.reentry_ramp import reentry_ramp_applies

E2E_STOP_PLAN_T = 2.0      # s: how far out the model's plan must already be below E2E_STOP_PLAN_V
E2E_STOP_PLAN_V = 0.1      # m/s: the plan has come to rest, not a creep (130's give-way crept at 0.18; see above)
E2E_STOP_STILL_V = 0.1     # m/s: below this the model's own flag decides (the same rule on the unsmoothed accel): no new
                           # latch, and a latch lets go with that flag, so a launch is not held back by the smoothing
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
    nose-up positive; the stop is only latched ON inside the grade band (once on, a grade change does not drop it).
    At rest (v_ego < E2E_STOP_STILL_V) the model's own flag decides: no new latch, and a latch lets go with that flag."""
    self.log_line = None
    was_latched = self.latched
    try:
      if not active or not should_stop(v_ego, a_target_e2e, v_ego_stopping=self.v_ego_stopping):
        self.latched = False
      elif v_ego < E2E_STOP_STILL_V:
        self.latched = self.latched and bool(model_should_stop)
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
