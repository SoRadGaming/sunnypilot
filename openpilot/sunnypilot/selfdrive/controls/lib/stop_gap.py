"""
FORK(HONDA_ACCORD_9G_AU): finish a gentle queue stop at the normal distance (stop_gap.py).

THE PROBLEM (measured, 50 clean rlog queue stops d0..183, r1110 trace/STOP_GAP.md and fix-stopgap/replay):
  The car does not rest where the MPC aims (6 m). It rests at the radar gap it has when its speed falls through
  STOPPING_SPEED (0.8 m/s, stopping_tune.py) while the MPC asks < 0.1 - true for any stopped lead within ~11 m - minus
  the stopping state's roll, 0.57 m [0.48, 0.68]. After a brisk approach the car reaches 0.8 m/s 1.3-2 m inside the
  MPC's desired distance (7.1 m at 0.8 m/s) and rests at 4.5-5.5 m. After a GENTLE approach - the model leading, a
  crawling queue, a lead still rolling, a short hop up the queue - it is still on that curve and rests at 6-7.4 m.
  Bounding a fix by the MPC would not help: at the long stops' entry the MPC itself asked -0.15..-0.48, within 0.1 of
  the model (customReserved10, 15d/180/182). Nothing re-closes the gap at rest.

WHAT THIS DOES - only below V_ARM, behind a radar-tracked, camera-confirmed, STOPPED (or creeping, <= 0.5 m/s) lead:
  1. LANDING LIFT: the plan's accel (the candidates' min(), after the re-entry ramp) may be RAISED by at most A_LIFT_MAX
     toward the constant deceleration that brings the car to V_ENTRY (0.77 m/s, today's measured entry) at REST_GAP +
     ROLL_ENTRY from the lead, so that today's stop - the same 0.8 m/s entry, the same stopping state, the same soft
     stop, the same ~0.57 m roll - ends at about REST_GAP. An approach that already brakes less than that profile (the
     brisk ones, which overshoot to 4.5-5.5 m) gets nothing: the lift only closes the distance between the plan and the
     landing profile, and the profile never aims inside REST_GAP.
     CATCH: once it has lifted in this stop, it also LOWERS the plan - by the same allowance - when the car has got
     ahead of a second, closer profile that lands at CATCH_GAP (4.7 m): a lifted stop whose candidates ease off late
     cannot be carried by the lift's extra speed past 4.7 m (0.2 m outside the MPC's 4.5 m standstill danger zone).
     Between the two profiles the plan is the candidates' own. It never lowers a stop it did not lift.
  2. THE QUEUE MOVING OFF ends it for that stop (PULL_AWAY: aLeadK over 0.3 or vLead over 0.5 m/s for 0.5 s, close
     follow's own rule): a lifted car must not turn into a rolling start.
  3. THE STOP IS NEVER DEFERRED. When the MPC's or cruise's 0.8 m/s rule fires (the stop entry) it lets go for that
     stop and today's stopping state runs. Deferring that rule to upstream's 0.3 while the car crawled on to the landing
     (v1) closed the stops behind a creeping lead too (logged 178 Thu 5 Nov 15:28:05, 182 Mon 9 Nov 15:46:55), but in
     the closed-loop sims a deferral that ended with the queue moving off left the car rolling at 0.6-0.9 m/s: no stop,
     no launch gates, a pull-away 2-3 m closer than push18's and up to 1.2 m less room when that lead then braked at
     -6 - outside close follow's bound (0.85 m). It was rejected, and this file has no code that defers a stop.
  The model's own stop flag (modeld: v < 0.3) and the stop rules are never touched: only the plan's accel is.

WHY THESE NUMBERS:
  REST_GAP 5.2 m (radar dRel): inside today's NORMAL stops (median 4.99 m [4.46, 5.48]; push18 5.36), 0.7 m outside
    the MPC's standstill danger zone (LEAD_DANGER_FACTOR 0.75 x STOP_DISTANCE 6 = 4.5 m), and well short of the
    owner's own 3.86 m (skeptic bound C1: bring the long stops to 4.9-5.4 m, never aim at 3.9).
  A_LIFT_MAX 0.30 m/s^2: what the long stops need at entry (0.20-0.29); close follow's lift is 0.5 on aggressive.
  swap_ok (on): the Elesys renumbers a car it keeps seeing (29 of the 50 logged stops carried 2-9 track ids in their
    last 9.5 s, 18 in the last 4 s);
    a new id that continues the old range within SWAP_TOL and that the camera still confirms is the same car. A car
    cutting in during the approach appears 40-60 % closer and trips on LEAD_JUMP / the camera (sims SX: unchanged).
  V_ARM 2.5 m/s (9 km/h): queue hops reach 1.4-2.6 m/s; above it a stop is still >= 3 s away.

THREE KINDS OF 'NO':
  HAZARD HOLD (watched at every speed, like close follow's hard-brake hold): a plan under A_HAZARD, a lead braking
    harder than LEAD_A_HAZARD, FCW or the MPC's crash count - nothing is lifted until HAZARD_HOLD_S after the last one.
    A stop that follows a hard brake is today's stop.
  TRIPS (the lift drops to zero on the same plan; nothing re-arms until the car is above V_ARM again or has stood
    still - one stop, one try): no radar lead, a held lead (radarTrackId < 0), a change of track (with swap_ok, one that
    does not continue the old range), a range jump (LEAD_JUMP), the queue moving off (PULL_AWAY); the camera has no lead
    or reads it more than CAM_TOL closer than the radar; a downhill steeper than PITCH_MIN (the stopping state has no
    grade term and rolls further); the gas pedal; a reset; the stop entry (a 0.8 m/s rule firing: today's stop runs);
    and, once it has lifted, the plan braking harder than A_PLAN_TRIP (the candidates want real braking: drop out for
    this stop).
  PAUSES (no lift this plan, the allowance starts again from zero): the lead faster than LEAD_V_MAX (moving away),
    reversing (vLead < LEAD_V_MIN) or still braking (aLeadK < LEAD_A_MIN); the plan under A_PLAN_TRIP before anything
    was lifted (a brisk approach, which needs nothing).

LOG: one `stopgap end= arm_v= arm_gap= max_lift= catch=` line per engagement (plannerd's cloudlog), when it lets go:
  the stop entry   `entry`, or the pause in force on that plan: `hazardHold`, `leadMoving`, `leadReversing`,
                   `leadBraking`, `leadPulling` (an engaged plan under A_PLAN_TRIP is a trip before it can be a pause)
  rest / fast      `standstill`: the car came to rest before the MPC's or cruise's 0.8 m/s rule fired (the model's own
                   flag or the red-light entry, e2e_stop.py, began the stop); `fast`: back above V_ARM
  trips            `radar`, `nolead`, `newTrack`, `leadJump`, `camera`, `downhill`, `planBraking`, `pullAway`, `gas`, `off`
  `error`          an exception: the plan passed through

Built only for this car with openpilot longitudinal, stock ACC mode off and HondaDynamicTuningEnabled on - the soft
stop's own gate - (stop_gap_applies). Every other car and stock ACC: None, upstream's plan bit for bit.
"""
import math

V_ARM = 2.5             # m/s: the governor looks at nothing faster
V_ENTRY = 0.77          # m/s: where today's stop entry happens (median of 50 queue stops: 0.77 [0.75, 0.79])
ROLL_ENTRY = 0.57       # m: the stopping state's travel from V_ENTRY (median of 50 stops, [0.48, 0.68])
REST_GAP = 5.2          # m, radar dRel: where a lifted stop is aimed to come to rest
CATCH_GAP = 4.7         # m, radar dRel: after a lift, the plan is lowered (the catch) only to keep the stop from ending inside this
LIFT_ROOM = 0.30        # m: lift only while the predicted rest is more than this beyond REST_GAP
A_LIFT_MAX = 0.30       # m/s^2: the most the plan's accel is raised
LIFT_RATE = 0.60        # m/s^3: how fast the lift's allowance grows (it drops at once on a trip)
T_LAG = 0.30            # s: the plan acts this late on the car (the landing point is moved this much closer)
V_RADAR_MIN = 0.35      # m/s: below this the radar has no tracks (measured 0.35 [0.32, 0.41]); the landing profile below
                        # V_ENTRY leaves out the stopping state's last roll from here
A_PLAN_TRIP = -1.0      # m/s^2: a plan braking harder than this is real braking - no lift
A_HAZARD = -2.0         # m/s^2: a plan this hard, at any speed, starts the hazard hold
LEAD_A_HAZARD = -2.5    # m/s^2: a lead (aLeadK) braking this hard, at any speed, starts the hazard hold
HAZARD_HOLD_S = 3.0     # s: nothing is lifted for this long after the last hazard (close follow's hard-brake hold is 3 s)
LEAD_V_MAX = 0.5        # m/s: the lead's radar speed above which it is not a stopped queue (v1 had 1.0: see PULL_AWAY)
PULL_AWAY_A = 0.3       # m/s^2: the lead's aLeadK over this for PULL_AWAY_T, or its speed over LEAD_V_MAX for as long, is
PULL_AWAY_T = 0.5       # s      the queue moving off: drop out for this stop (close follow's pull-away rule, same numbers)
LEAD_V_MIN = -0.5       # m/s: a lead reversing (rolling back) - no lift
LEAD_A_MIN = -1.0       # m/s^2: the lead's aLeadK below which it is still braking - no lift
SWAP_TOL = 0.75         # m: swap_ok - a new radar track id this close to where the old track should be is the same car
LEAD_JUMP = 1.5         # m: leadOne's radar range this far off where it should be (last range + vRel x dt) - a new car
CAM_TOL = 1.0           # m: the camera's lead may read this much shorter than the radar (median 0.44 near the stop)
CAM_BIAS = 0.45         # m: the camera's usual short reading; the gap used is min(radar, camera + CAM_BIAS)
CAM_PROB = 0.5          # the camera lead's probability needed to confirm the radar lead
RADAR_TO_CAMERA = 1.52  # m, radard.RADAR_TO_CAMERA
PITCH_MIN = -0.044      # rad (-2.5 deg): steeper downhill rolls further in the stopping state - no governor
DT = 0.05               # s, plannerd's period

# the stopping state's roll (m) from entry at v (m/s) on the flat: LongControl's ramp to stopAccel -0.8 at 0.8 m/s^3
# under the soft stop's 105-count ceiling. 0.77 -> 0.57 is the measured median (50 stops); below it, the replica.
ROLL_BP = [0.0, 0.30, 0.35, 0.50, 0.65, 0.77]
ROLL_V = [0.0, 0.10, 0.13, 0.25, 0.40, 0.57]


def roll(v: float) -> float:
  """The stopping state's travel from an entry at v (m/s), v <= V_ENTRY; above it, kinematic at the same mean decel."""
  v = max(0.0, float(v))
  if v >= ROLL_BP[-1]:
    return ROLL_V[-1] * (v / ROLL_BP[-1]) ** 2
  for i in range(1, len(ROLL_BP)):
    if v <= ROLL_BP[i]:
      f = (v - ROLL_BP[i - 1]) / (ROLL_BP[i] - ROLL_BP[i - 1])
      return ROLL_V[i - 1] + f * (ROLL_V[i] - ROLL_V[i - 1])
  return ROLL_V[-1]


def _f(x, default=float('nan')) -> float:
  try:
    v = float(x)
  except (TypeError, ValueError):
    return default
  return v if math.isfinite(v) else default


def landing_accel(v: float, gap: float, rest_gap: float = REST_GAP) -> float | None:
  """The accel (<= 0) of the constant-decel profile that ends where today's stop would leave the car rest_gap from the
  lead: above V_ENTRY, at V_ENTRY with rest_gap + ROLL_ENTRY to go; at or below it, at rest less the stopping state's
  last roll from V_RADAR_MIN. None when there is no room left (the plan stands)."""
  if v > V_ENTRY:
    d = gap - (rest_gap + ROLL_ENTRY) - v * T_LAG
    if d <= 0.2:
      return None
    return min(0.0, (V_ENTRY ** 2 - v ** 2) / (2.0 * d))
  d = gap - rest_gap - roll(V_RADAR_MIN) - v * T_LAG
  if d <= 0.1:
    return None
  return -(v ** 2) / (2.0 * d)


class StopGap:
  def __init__(self, v_stopping: float = 0.8, dt: float = DT, rest_gap: float = REST_GAP, a_lift_max: float = A_LIFT_MAX,
               swap_ok: bool = True):
    self.v_stopping = v_stopping
    self.dt = dt
    self.rest_gap = rest_gap
    self.a_lift_max = a_lift_max
    self.swap_ok = swap_ok    # the Elesys renumbers a car it keeps seeing; with this a new id that continues the old range
                              # (SWAP_TOL) and that the camera still confirms is the same car. Off: any new id trips
    self.allow = 0.0          # m/s^2: the lift's current allowance (ramped up, dropped on a trip)
    self.lift = 0.0           # m/s^2: what was added to the plan this frame
    self.spent = False        # tripped or released this stop: nothing re-arms until v > V_ARM or a standstill
    self.reason = ''          # why it last let go (for the log line)
    self.max_lift = 0.0
    self.max_catch = 0.0      # m/s^2 (<= 0): the most the catch lowered the plan this stop
    self.log_line = None      # one line per engagement, for plannerd's cloudlog (like opendbc's 'hondastop')
    self.engaged = False
    self._tid = None
    self._arm_v = self._arm_gap = float('nan')
    self.since_hazard = 1e9   # s since the last hazard (at any speed)
    self.pull_t = 0.0         # s the lead has been moving off (PULL_AWAY)
    self._last_d = float('nan')
    self.pause = ''

  # --- the gate: a radar-tracked, camera-confirmed, (nearly) stopped real lead
  def lead_gap(self, lead, cam_prob, cam_x):
    """(gap m or None, why)."""
    if lead is None:
      return None, 'nolead'
    present = bool(getattr(lead, 'present', False) or getattr(lead, 'status', False))
    tid = int(_f(getattr(lead, 'radarTrackId', -1), -1))
    if not present or tid < 0 or not bool(getattr(lead, 'radar', False)):
      return None, 'radar'
    d, vl = _f(getattr(lead, 'dRel', None)), _f(getattr(lead, 'vLead', None))
    expected, self._last_d = self._last_d + _f(getattr(lead, 'vRel', None), 0.0) * self.dt, d
    if not (math.isfinite(d) and math.isfinite(vl)):
      return None, 'radar'
    if self._tid is not None and tid != self._tid:
      if not (self.swap_ok and math.isfinite(expected) and abs(d - expected) < SWAP_TOL):
        return None, 'newTrack'
      self._tid = tid
    if self._tid is not None and math.isfinite(expected) and abs(d - expected) > LEAD_JUMP:
      return None, 'leadJump'
    cx = _f(cam_x)
    if not (_f(cam_prob, 0.0) > CAM_PROB and math.isfinite(cx)):
      return None, 'camera'
    cam_d = cx - RADAR_TO_CAMERA
    if cam_d < d - CAM_TOL:
      return None, 'camera'
    return min(d, cam_d + CAM_BIAS), ''

  @staticmethod
  def lead_pause(lead) -> str:
    vl, al = _f(getattr(lead, 'vLead', None), 0.0), _f(getattr(lead, 'aLeadK', None), 0.0)
    if vl > LEAD_V_MAX:
      return 'leadMoving'
    if vl < LEAD_V_MIN:
      return 'leadReversing'
    if al < LEAD_A_MIN:
      return 'leadBraking'
    if al > PULL_AWAY_A:
      return 'leadPulling'
    return ''

  def _let_go(self, why: str):
    if self.engaged and not self.spent:
      self.log_line = (f"stopgap end={why} arm_v={self._arm_v:.2f} arm_gap={self._arm_gap:.2f} max_lift={self.max_lift:.2f} " +
                       f"catch={self.max_catch:.2f}")
    self.spent = True
    self.reason = why
    self.allow = 0.0
    self.lift = 0.0

  def _rearm(self):
    self.spent = False
    self.engaged = False
    self.allow = 0.0
    self.max_lift = 0.0
    self.max_catch = 0.0
    self.pull_t = 0.0
    self._tid = None

  def update(self, active: bool, v_ego: float, a_plan: float, rule_stop: bool, lead, cam_prob, cam_x, standstill: bool,
             pitch, fcw: bool, crash_cnt, gas: bool) -> float:
    """One plan. a_plan: the plan's accel (the candidates' min() after the re-entry ramp); rule_stop: the MPC's or
    cruise's own should_stop under STOPPING_SPEED (v < 0.8, a < 0.1) - the stop entry, which ends it for that stop.
    Returns the plan's accel: lifted (or, after a lift, caught) or a_plan itself."""
    self.log_line = None
    self.lift = 0.0
    self.pause = ''
    try:
      v = _f(v_ego, 0.0)
      a = _f(a_plan, 0.0)
      # the hazard hold, watched at every speed
      al = _f(getattr(lead, 'aLeadK', None), 0.0) if lead is not None else 0.0
      lead_on = lead is not None and bool(getattr(lead, 'present', False) or getattr(lead, 'status', False))
      if not active or a < A_HAZARD or (lead_on and al < LEAD_A_HAZARD) or fcw or int(_f(crash_cnt, 0)) > 0:
        self.since_hazard = 0.0
      else:
        self.since_hazard += self.dt
      if not active or gas or standstill or v > V_ARM:
        # every engagement writes its line; at rest or above V_ARM that is all _let_go() changes, since _rearm() follows
        if self.engaged and not self.spent:
          self._let_go('off' if not active else 'gas' if gas else 'standstill' if standstill else 'fast')
        if standstill or v > V_ARM or not active:   # re-arm for the next stop
          self._rearm()
        return a
      if self.spent:
        return a
      gap, why = self.lead_gap(lead, cam_prob, cam_x)
      if gap is not None and _f(pitch, 0.0) < PITCH_MIN:
        gap, why = None, 'downhill'
      if gap is not None and self.engaged and a < A_PLAN_TRIP:
        gap, why = None, 'planBraking'
      if lead is not None:
        moving_off = _f(getattr(lead, 'aLeadK', None), 0.0) > PULL_AWAY_A or _f(getattr(lead, 'vLead', None), 0.0) > LEAD_V_MAX
        self.pull_t = self.pull_t + self.dt if moving_off else 0.0
      if gap is not None and self.engaged and self.pull_t >= PULL_AWAY_T:
        gap, why = None, 'pullAway'      # the queue is moving off: the stop is today's (no rolling start from a lift)
      if gap is None:
        if self.engaged:
          self._let_go(why)
        return a
      if self.since_hazard < HAZARD_HOLD_S:
        self.pause = 'hazardHold'
      elif a < A_PLAN_TRIP:
        self.pause = 'planBraking'
      else:
        self.pause = self.lead_pause(lead)

      pred_rest = gap - roll(min(v, V_ENTRY))     # where a stop entered now would leave the car
      a_goal = landing_accel(v, gap, self.rest_gap)

      # 2. the stop entry: a 0.8 m/s rule has fired - today's stop runs (never deferred); the lift has nothing left to do
      if rule_stop and v < self.v_stopping:
        if self.engaged:
          self._let_go(self.pause or 'entry')
        self.spent = True
        return a

      # 1. the lift: raise the plan toward the landing profile, by at most the allowance; after a lift, the catch
      if self.pause:
        self.allow = 0.0
      elif a_goal is not None and pred_rest > self.rest_gap + LIFT_ROOM and a_goal > a:
        self.allow = min(self.a_lift_max, self.allow + LIFT_RATE * self.dt)
        a_out = min(a_goal, a + self.allow)
        self.lift = max(0.0, a_out - a)
      elif self.engaged and ((a_catch := landing_accel(v, gap, CATCH_GAP)) is None or a_catch < a):
        self.allow = min(self.a_lift_max, self.allow + LIFT_RATE * self.dt)
        a_out = a - self.allow if a_catch is None else max(a_catch, a - self.allow)
        self.lift = min(0.0, a_out - a)
        self.max_catch = min(self.max_catch, self.lift)
      if self.lift > 0.0:
        if not self.engaged:
          self.engaged = True
          self._arm_v, self._arm_gap = v, gap
          self._tid = int(_f(getattr(lead, 'radarTrackId', -1), -1))
        self.max_lift = max(self.max_lift, self.lift)
      return a + self.lift
    except Exception:
      self._let_go('error')                      # never raise in plannerd: today's plan stands
      return _f(a_plan, 0.0)


def stop_gap_applies(CP, CP_SP) -> bool:
  """This car (a STOPPING_SPEED entry), openpilot longitudinal, stock ACC mode off, HondaDynamicTuningEnabled on."""
  try:
    from openpilot.sunnypilot.selfdrive.controls.lib.stopping_tune import STOPPING_SPEED
    from openpilot.sunnypilot.selfdrive.controls.lib.reentry_ramp import reentry_ramp_applies
    if CP.carFingerprint not in STOPPING_SPEED or not reentry_ramp_applies(CP, CP_SP):
      return False
    from openpilot.common.params import Params
    return Params().get_bool("HondaDynamicTuningEnabled")
  except Exception:
    return False
