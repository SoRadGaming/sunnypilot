"""FORK(STOP-GAP): the queue-stop governor (stop_gap.py).

The unit tests pin each gate, trip, pause and the catch, that the stop entry ends it (the stop is never deferred), that
it never raises, and a closed-loop point-mass check: long gentle stops land near REST_GAP, brisk ones are untouched.
stop_gap_applies() and the planner's build gate are in selfdrive/controls/tests/test_stopping_debounce.py.
"""
import math
from types import SimpleNamespace as NS

from openpilot.common.test import OpenpilotTestCase
from openpilot.sunnypilot.selfdrive.controls.lib import stop_gap as SG

DT = SG.DT


def lead(d=8.0, vl=0.0, al=0.0, tid=7, radar=True, present=True, vrel=None):
  return NS(present=present, status=present, radarTrackId=tid, radar=radar, dRel=d, vLead=vl, aLeadK=al,
            vRel=(vl if vrel is None else vrel))


def cam_x(d):            # the camera's lead x for a radar range d, reading CAM_BIAS short as it usually does
  return d + SG.RADAR_TO_CAMERA - SG.CAM_BIAS


def step(g, v, a, ld, rule=False, cam=None, standstill=False, pitch=0.0, fcw=False, crash=0, gas=False, active=True,
         prob=0.9):
  return g.update(active, v, a, rule, ld, prob, cam_x(ld.dRel) if (cam is None and ld is not None) else cam, standstill,
                  pitch, fcw, crash, gas)


def close_in(g, v, gap0, a_fn, n, **kw):
  """n plans at a constant v, the gap to a stopped lead closing by v*DT each (vRel = -v: the radar range continues, so
  nothing trips on a jump). Returns [(gap, a_plan, out)]."""
  rows, gap = [], gap0
  for _ in range(n):
    a = a_fn(gap)
    rows.append((gap, a, step(g, v, a, lead(gap, vrel=-v), **kw)))
    gap -= v * DT
  return rows


class _UnreadableLead:
  """A radarState lead whose dRel raises something _f() does not catch: the update's own except must."""
  present = status = radar = True
  radarTrackId = 7
  vLead = vRel = aLeadK = 0.0

  @property
  def dRel(self):
    raise RuntimeError("radarState unreadable")


def simulate(plan_fn, gap0=14.0, v0=2.4, governor=True, lag=0.3):
  """A point mass with a first-order lag, today's 0.8 m/s stopping rule and the stopping state's measured ~0.5 m/s^2,
  behind a stopped lead (radar blind below 0.35 m/s: the last range is held). Returns the rest gap."""
  g = SG.StopGap() if governor else None
  x, v, a_car, stopping, t = 0.0, v0, plan_fn(v0, gap0), False, 0.0
  while v > 0.0 and t < 20.0:
    gap = gap0 - x
    a_plan = plan_fn(v, gap)
    rule = v < 0.8 and a_plan < 0.1
    if g is not None:
      a_plan = g.update(True, v, a_plan, rule, lead(gap, vrel=-v), 0.9, cam_x(gap), False, 0.0, False, 0, False)
    if rule or v < 0.3:
      stopping = True
    tgt = -0.5 if stopping else a_plan
    for _ in range(5):                       # 100 Hz inside the 20 Hz plan
      a_car += (tgt - a_car) * 0.01 / (lag + 0.01)
      v = max(0.0, v + a_car * 0.01)
      x += v * 0.01
    t += DT
  return gap0 - x


def gentle(rest, cap=-0.8):   # a model that plans a gentle stop at `rest` (constant decel, a little early), never past cap
  return lambda v, gap: max(cap, -(v ** 2) / (2.0 * max(gap - rest, 0.3)) - 0.05)


class TestStopGap(OpenpilotTestCase):
  def test_no_lead_vision_or_held_changes_nothing(self):
    for ld in (None, lead(radar=False, tid=-1), lead(tid=-3), lead(present=False)):
      g = SG.StopGap()
      for _ in range(40):
        self.assertEqual(step(g, 1.5, -0.6, ld, cam=cam_x(9.0)), -0.6)

  def test_brisk_approach_untouched(self):
    # 1.5 m/s, 6.5 m: the landing profile asks harder braking than the plan (-0.5): the car is already closer than it
    g = SG.StopGap()
    self.assertTrue(SG.landing_accel(1.5, 6.5) is None or SG.landing_accel(1.5, 6.5) < -0.5)
    for _ in range(40):
      self.assertEqual(step(g, 1.5, -0.5, lead(6.5)), -0.5)
    self.assertFalse(g.engaged)

  def test_gentle_long_approach_lifts_toward_the_profile_and_never_past_it(self):
    g = SG.StopGap()
    goal = SG.landing_accel(1.5, 9.0)
    self.assertTrue(goal is not None and goal > -0.9)
    lifts = []
    for _ in range(40):
      a = step(g, 1.5, -0.9, lead(9.0))
      lifts.append(a + 0.9)
      self.assertLessEqual(a, goal + 1e-9)
      self.assertLessEqual(a + 0.9, SG.A_LIFT_MAX + 1e-9)
    self.assertAlmostEqual(lifts[0], SG.LIFT_RATE * DT, delta=1e-9)          # ramps in
    self.assertTrue(max(lifts) > 0.29 or abs(max(lifts) - (goal + 0.9)) < 1e-9)

  def test_not_above_v_arm_and_no_lift_at_standstill(self):
    g = SG.StopGap()
    for _ in range(20):
      self.assertEqual(step(g, SG.V_ARM + 0.1, -0.9, lead(14.0)), -0.9)
      self.assertEqual(step(g, 0.0, -0.9, lead(9.0), standstill=True), -0.9)

  def test_hazard_hold_after_hard_braking_at_any_speed(self):
    g = SG.StopGap()
    step(g, 6.0, -2.5, lead(15.0))                           # a hard plan at 21.6 km/h
    n = int(SG.HAZARD_HOLD_S / DT)
    for i in range(n - 2):
      self.assertEqual(step(g, 1.5, -0.9, lead(9.0)), -0.9, i)
    for _ in range(10):
      a = step(g, 1.5, -0.9, lead(9.0))
    self.assertGreater(a, -0.9)
    g2 = SG.StopGap()
    step(g2, 5.0, -0.5, lead(15.0, vl=3.0, al=-3.0))          # a lead braking hard
    self.assertEqual(step(g2, 1.5, -0.9, lead(9.0)), -0.9)
    g3 = SG.StopGap()
    step(g3, 5.0, -0.5, lead(15.0), fcw=True)
    self.assertEqual(step(g3, 1.5, -0.9, lead(9.0)), -0.9)

  def test_pauses_restart_the_allowance(self):
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0))
    for ld in (lead(9.0, vl=1.2), lead(9.0, al=-1.5), lead(9.0, vl=-0.8)):
      self.assertEqual(step(g, 1.5, -0.9, ld), -0.9)
      self.assertEqual(g.allow, 0.0)
      self.assertFalse(g.spent)
    a = step(g, 1.5, -0.9, lead(9.0))
    self.assertAlmostEqual(a + 0.9, SG.LIFT_RATE * DT, delta=1e-9)

  def test_trips_latch_until_standstill_or_v_arm(self):
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertTrue(g.engaged)
    a = step(g, 1.5, -0.9, lead(9.0), cam=cam_x(9.0) - 1.6)   # the camera sees something 1.6 m closer
    self.assertEqual(a, -0.9)
    self.assertTrue(g.spent)
    self.assertIn('camera', g.log_line)
    for _ in range(10):
      self.assertEqual(step(g, 1.4, -0.9, lead(8.9)), -0.9)    # one stop, one try
    step(g, 0.0, 0.0, lead(8.0), standstill=True)
    self.assertFalse(g.spent)

  def test_new_track_and_jump_trip_and_swap_ok(self):
    for swap_ok, tid, d, tripped in ((False, 8, 8.93, True), (True, 8, 8.93, False), (True, 8, 7.0, True)):
      g = SG.StopGap(swap_ok=swap_ok)
      for _ in range(10):
        step(g, 1.5, -0.9, lead(9.0, vrel=-1.5))
      step(g, 1.5, -0.9, lead(d, tid=tid, vrel=-1.5))
      self.assertEqual(g.spent, tripped, (swap_ok, tid, d))

  def test_downhill_gas_and_disengage(self):
    g = SG.StopGap()
    self.assertEqual(step(g, 1.5, -0.9, lead(9.0), pitch=-0.06), -0.9)
    self.assertFalse(g.spent)                                  # not engaged: nothing to latch
    g = SG.StopGap()
    for _ in range(5):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertEqual(step(g, 1.5, -0.9, lead(9.0), gas=True), -0.9)
    self.assertTrue(g.spent)
    g = SG.StopGap()
    for _ in range(5):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertEqual(step(g, 1.5, -0.9, lead(9.0), active=False), -0.9)
    self.assertFalse(g.engaged)

  def test_plan_braking_hard_pauses_before_and_trips_after_a_lift(self):
    g = SG.StopGap()
    self.assertEqual(step(g, 1.5, -1.2, lead(9.0)), -1.2)
    self.assertFalse(g.spent)
    for _ in range(5):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertEqual(step(g, 1.5, -1.2, lead(9.0)), -1.2)
    self.assertTrue(g.spent)

  def test_catch_only_after_a_lift_and_never_below_the_profile(self):
    g = SG.StopGap()
    # never lifted: a car ahead of the profile is left to the plan
    for _ in range(10):
      self.assertEqual(step(g, 1.5, -0.3, lead(6.6)), -0.3)
    # lifted from 9 m, then the candidates ease off to -0.2 while the car closes in at 1.4 m/s: every plan is lowered to
    # the 4.7 m profile, or by the allowance (A_LIFT_MAX) where the profile asks for more - never further
    g = SG.StopGap()
    rows = close_in(g, 1.4, 9.0, lambda gap: -0.9 if gap > 7.6 else -0.2, 40)
    self.assertTrue(g.engaged and not g.spent)
    caught = [(gap, a, out) for gap, a, out in rows if a == -0.2]
    self.assertGreater(len(caught), 10)
    for gap, a, out in caught:
      a_catch = SG.landing_accel(1.4, gap, SG.CATCH_GAP)
      self.assertLess(out, a)                                                   # it caught on every one of them
      self.assertAlmostEqual(out, a - SG.A_LIFT_MAX if a_catch is None else max(a_catch, a - SG.A_LIFT_MAX), delta=1e-9)
      self.assertGreaterEqual(out, a - SG.A_LIFT_MAX - 1e-9)
    self.assertTrue(any(SG.landing_accel(1.4, gap, SG.CATCH_GAP) < a - SG.A_LIFT_MAX for gap, a, _ in caught))  # the bound bit
    self.assertAlmostEqual(g.max_catch, -SG.A_LIFT_MAX, delta=1e-9)

  def test_the_stop_entry_ends_it_and_is_never_deferred(self):
    # a 0.8 m/s rule firing: the plan passes through untouched, one log line, and nothing more this stop
    g = SG.StopGap()
    for _ in range(5):
      step(g, 0.9, -0.5, lead(7.6))
    self.assertTrue(g.engaged)
    self.assertEqual(step(g, 0.75, -0.4, lead(7.4), rule=True), -0.4)
    self.assertTrue(g.spent)
    self.assertTrue(g.log_line.startswith('stopgap end=entry '), g.log_line)
    for _ in range(10):
      self.assertEqual(step(g, 0.6, -0.4, lead(7.3), rule=True), -0.4)
      self.assertIsNone(g.log_line)
    # the module has no way to defer the stop: no hold state, no hold switch
    self.assertFalse(any(hasattr(g, k) for k in ('hold', 'hold_on', 'hold_t', 'hold_d', 'hold_budget')))
    self.assertFalse(any(k.startswith('HOLD_') for k in vars(SG)))

  def test_one_log_line_per_engagement(self):
    g = SG.StopGap()
    lines = []
    for _ in range(20):
      step(g, 1.5, -0.9, lead(9.0))
      lines.append(g.log_line)
    step(g, 0.75, -0.4, lead(8.95), rule=True)               # the stop entry (the lead's range continues: no jump)
    lines.append(g.log_line)
    for _ in range(10):
      step(g, 0.5, -0.4, lead(8.9), rule=True)
      lines.append(g.log_line)
    logged = [x for x in lines if x is not None]
    self.assertEqual(len(logged), 1)
    for k in ('end=entry', 'arm_v=1.50', 'arm_gap=', 'max_lift=0.30', 'catch=0.00'):
      self.assertIn(k, logged[0])

  def test_garbage_never_raises(self):
    g = SG.StopGap()
    for args in ((True, float('nan'), -0.5, False, lead(9.0), 0.9, 9.0, False, 0.0, False, 0, False),
                 (True, 1.5, None, False, lead(9.0), None, None, False, None, False, None, False),
                 (True, 1.5, -0.5, False, object(), 'x', 'y', False, 0.0, False, 0, False)):
      a = g.update(*args)
      self.assertIsInstance(a, float)
      self.assertTrue(math.isfinite(a))

  def test_closed_loop_long_stops_land_near_rest_gap_normal_ones_untouched(self):
    for rest in (6.5, 7.0, 7.5):
      today = simulate(gentle(rest, -0.6), governor=False)        # a model braking up to 0.6 (the logged long stops: 0.3-0.7)
      fixed = simulate(gentle(rest, -0.6), governor=True)
      self.assertGreater(today, 6.0)
      self.assertTrue(SG.REST_GAP - 0.35 <= fixed <= SG.REST_GAP + 0.45, (rest, today, fixed))
      today = simulate(gentle(rest, -0.8), governor=False)        # braking up to 0.8: the 0.3 cap binds, it gets part way
      fixed = simulate(gentle(rest, -0.8), governor=True)
      self.assertTrue(SG.REST_GAP - 0.35 <= fixed < today - 0.5, (rest, today, fixed))
    for rest in (4.0, 4.6, 5.0):
      today = simulate(gentle(rest, -1.5), governor=False)
      fixed = simulate(gentle(rest, -1.5), governor=True)
      self.assertLessEqual(fixed, today + 0.05, (rest, today, fixed))                       # never makes a normal stop longer
      self.assertGreaterEqual(fixed, min(today, SG.CATCH_GAP) - 0.05, (rest, today, fixed))  # nor shorter than the catch allows
    self.assertLess(abs(simulate(gentle(4.0, -1.5), governor=False) - simulate(gentle(4.0, -1.5))), 0.02)   # a brisk one: untouched

  def test_an_insistent_model_wins(self):
    # a model that will not be talked out of its 6.5 m: its request climbs past A_PLAN_TRIP as the lifted car closes in;
    # the governor drops out for that stop and the stop ends between the model's rest and today's
    today = simulate(gentle(6.5, -1.5), governor=False)
    fixed = simulate(gentle(6.5, -1.5), governor=True)
    self.assertTrue(today - 1.0 < fixed <= today + 1e-6 and fixed > SG.REST_GAP + 0.5, (today, fixed))

  def test_queue_moving_off_ends_it_and_a_pulling_lead_pauses(self):
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertTrue(g.engaged)
    a = step(g, 1.5, -0.9, lead(9.0, al=0.5))                 # pulling: a pause at once
    self.assertEqual(a, -0.9)
    self.assertEqual(g.pause, 'leadPulling')
    self.assertFalse(g.spent)
    for _ in range(int(SG.PULL_AWAY_T / DT) + 1):
      step(g, 1.5, -0.9, lead(9.0, vl=0.7, al=0.5))
    self.assertTrue(g.spent)
    self.assertIn('pullAway', g.reason or '')

  # --- the gates and trips one at a time, the bounds, the except path, the constants (push19 review) ----------------

  def test_constants(self):
    self.assertEqual((SG.V_ARM, SG.V_ENTRY, SG.ROLL_ENTRY, SG.REST_GAP, SG.CATCH_GAP, SG.LIFT_ROOM), (2.5, 0.77, 0.57, 5.2, 4.7, 0.30))
    self.assertEqual((SG.A_LIFT_MAX, SG.LIFT_RATE, SG.T_LAG, SG.V_RADAR_MIN), (0.30, 0.60, 0.30, 0.35))
    self.assertEqual((SG.A_PLAN_TRIP, SG.A_HAZARD, SG.LEAD_A_HAZARD, SG.HAZARD_HOLD_S), (-1.0, -2.0, -2.5, 3.0))
    self.assertEqual((SG.LEAD_V_MAX, SG.PULL_AWAY_A, SG.PULL_AWAY_T, SG.LEAD_V_MIN, SG.LEAD_A_MIN), (0.5, 0.3, 0.5, -0.5, -1.0))
    self.assertEqual((SG.SWAP_TOL, SG.LEAD_JUMP, SG.CAM_TOL, SG.CAM_BIAS, SG.CAM_PROB), (0.75, 1.5, 1.0, 0.45, 0.5))
    self.assertEqual((SG.PITCH_MIN, SG.DT), (-0.044, 0.05))
    self.assertEqual((SG.ROLL_BP, SG.ROLL_V), ([0.0, 0.30, 0.35, 0.50, 0.65, 0.77], [0.0, 0.10, 0.13, 0.25, 0.40, 0.57]))
    from openpilot.selfdrive.controls.radard import RADAR_TO_CAMERA
    self.assertEqual(SG.RADAR_TO_CAMERA, RADAR_TO_CAMERA)

  def test_the_camera_must_confirm_with_its_probability(self):
    unsure = SG.CAM_PROB - 0.2                                 # a finite x the camera gives little probability
    g = SG.StopGap()
    for _ in range(10):
      self.assertEqual(step(g, 1.5, -0.9, lead(9.0), prob=unsure), -0.9)
    self.assertFalse(g.engaged)
    self.assertEqual(step(g, 1.5, -0.9, lead(9.0), prob=SG.CAM_PROB), -0.9)   # at the threshold: not confirmed
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertTrue(g.engaged)
    self.assertEqual(step(g, 1.5, -0.9, lead(9.0), prob=unsure), -0.9)        # engaged: it trips
    self.assertTrue(g.spent)
    self.assertEqual(g.reason, 'camera')

  def test_a_range_jump_on_the_same_track_trips(self):
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0, vrel=-1.5))
    self.assertTrue(g.engaged)
    self.assertEqual(step(g, 1.5, -0.9, lead(7.0, vrel=-1.5)), -0.9)          # the same id 7, 1.9 m short of where it should be
    self.assertTrue(g.spent)
    self.assertEqual(g.reason, 'leadJump')
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0, vrel=-1.5))
    self.assertGreater(step(g, 1.5, -0.9, lead(9.0 - 1.5 * DT - 1.0, vrel=-1.5)), -0.9)   # 1.0 m off: inside LEAD_JUMP
    self.assertFalse(g.spent)

  def test_a_new_track_id_is_the_same_car_only_within_swap_tol(self):
    for off, tripped in ((0.5, False), (1.0, True)):              # 1.0 m: outside SWAP_TOL, though inside LEAD_JUMP
      g = SG.StopGap()
      for _ in range(10):
        step(g, 1.5, -0.9, lead(9.0, vrel=-1.5))
      step(g, 1.5, -0.9, lead(9.0 - 1.5 * DT - off, tid=8, vrel=-1.5))
      self.assertEqual(g.spent, tripped, off)
      self.assertEqual(g.reason, 'newTrack' if tripped else '', off)

  def test_the_mpcs_crash_count_starts_the_hazard_hold(self):
    g = SG.StopGap()
    step(g, 5.0, -0.5, lead(15.0), crash=1)
    for i in range(int(SG.HAZARD_HOLD_S / DT) - 2):
      self.assertEqual(step(g, 1.5, -0.9, lead(9.0)), -0.9, i)
      self.assertEqual(g.pause, 'hazardHold')

  def test_engaging_starts_the_hazard_hold(self):
    g = SG.StopGap()
    step(g, 1.5, -0.9, lead(9.0), active=False)                  # openpilot not yet engaged (or reset) on this plan
    for i in range(int(SG.HAZARD_HOLD_S / DT) - 2):
      self.assertEqual(step(g, 1.5, -0.9, lead(9.0)), -0.9, i)
      self.assertEqual(g.pause, 'hazardHold')
    for _ in range(4):
      a = step(g, 1.5, -0.9, lead(9.0))
    self.assertGreater(a, -0.9)

  def test_the_queue_moving_off_on_the_leads_speed_alone(self):
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0))
    for _ in range(int(SG.PULL_AWAY_T / DT) + 1):
      self.assertEqual(step(g, 1.5, -0.9, lead(9.0, vl=0.6)), -0.9)          # just over LEAD_V_MAX, no accel: a pause
    self.assertTrue(g.spent)
    self.assertEqual(g.reason, 'pullAway')
    g = SG.StopGap()
    for _ in range(20):
      a = step(g, 1.5, -0.9, lead(9.0, vl=0.45))                             # creeping at 0.45 m/s: still a stopped queue
    self.assertGreater(a, -0.9)
    self.assertFalse(g.spent)

  def test_the_lift_stops_at_the_landing_profile(self):
    goal = SG.landing_accel(1.5, 9.0)
    self.assertTrue(-0.5 < goal < -0.5 + SG.A_LIFT_MAX)          # the full allowance would carry the plan past it
    g = SG.StopGap()
    out = [step(g, 1.5, -0.5, lead(9.0)) for _ in range(20)]
    self.assertAlmostEqual(out[-1], goal, delta=1e-12)
    self.assertTrue(all(o <= goal + 1e-12 for o in out))

  def test_an_exception_passes_the_plan_through_with_one_line(self):
    g = SG.StopGap()
    self.assertEqual(step(g, 1.5, -0.9, _UnreadableLead(), cam=cam_x(9.0)), -0.9)
    self.assertIsNone(g.log_line)                                 # not engaged: nothing to say
    g = SG.StopGap()
    for _ in range(10):
      step(g, 1.5, -0.9, lead(9.0))
    self.assertTrue(g.engaged)
    self.assertEqual(step(g, 1.5, -0.9, _UnreadableLead(), cam=cam_x(9.0)), -0.9)
    self.assertEqual(g.reason, 'error')
    self.assertTrue(g.log_line.startswith('stopgap end=error '), g.log_line)
    self.assertEqual(step(g, 1.5, -0.9, _UnreadableLead(), cam=cam_x(9.0)), -0.9)
    self.assertIsNone(g.log_line)

  def test_an_engagement_that_ends_at_rest_or_above_v_arm_writes_its_line(self):
    # no 0.8 m/s MPC or cruise rule before the rest (the model's flag or the red-light entry began the stop), or the car
    # back above V_ARM: the line is written, and the governor re-arms for the next stop as before
    for v, standstill, end in ((0.0, True, 'standstill'), (SG.V_ARM + 0.1, False, 'fast')):
      g = SG.StopGap()
      for _ in range(5):
        step(g, 1.5, -0.9, lead(9.0))
      self.assertTrue(g.engaged)
      self.assertEqual(step(g, v, -0.9, lead(9.0), standstill=standstill), -0.9)
      self.assertTrue(g.log_line.startswith(f'stopgap end={end} arm_v=1.50 '), g.log_line)
      self.assertFalse(g.engaged or g.spent)
      self.assertEqual(step(g, v, -0.9, lead(9.0), standstill=standstill), -0.9)
      self.assertIsNone(g.log_line)
