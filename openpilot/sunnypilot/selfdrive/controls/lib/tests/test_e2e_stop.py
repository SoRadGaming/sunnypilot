"""FORK(HONDA_ACCORD_9G_AU): the red-light stop entry (e2e_stop.py).

The unit tests pin the rule (v < STOPPING_SPEED, the model's accel < 0.1, the model's plan below 0.1 m/s 2 s out), the
latch and its release (at rest, the model's own flag decides), the grade band, that the model's own flag always passes
through, that it never raises, the one
log line per engagement, the build gate (e2e_stop_applies), a replay of the logged approaches (fixture), and that the
130 give-way, where the model meant to creep through, does not latch. The planner's build gate is in
selfdrive/controls/tests/test_stopping_debounce.py.
"""
import gzip
import json
import math
import os
import random
from types import SimpleNamespace
from unittest import mock

import numpy as np

from opendbc.car.honda.values import CAR
from opendbc.sunnypilot.car.honda.values_ext import HondaFlagsSP
from openpilot.common.params import Params
from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.sunnypilot.selfdrive.controls.lib import e2e_stop as e
from openpilot.sunnypilot.selfdrive.controls.lib.stopping_tune import STOPPING_SPEED

T = np.array(ModelConstants.T_IDXS)
V_STOP = STOPPING_SPEED["HONDA_ACCORD_9G_AU"]
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "e2e_stop_frames.json.gz")
# What the rule does on each logged approach in the fixture ("kind" is what the car did on the road):
EARLY = ("12b_470.7", "142_263.7")     # red lights it enters at 0.77-0.80 m/s, >= 1.8 s before the logged stop
MODEL_ONLY = ("161_147.6",)            # a red light (lead pulling away) whose plan stayed at 0.14-0.21 m/s 2 s out: since
                                       # the threshold is 0.1 it never latches, and the stop is the model's own (0.29 m/s)
ROLLED_ON = ("161_126.9", "130_113.9")  # the crawl that kept rolling, and the 130 give-way: never enter


def load_fixture():
  with gzip.open(FIXTURE, "rt") as f:
    return {c["id"]: c for c in json.load(f)}


def replay(frames, pitch=None):
  """(outputs, latched, log lines) of a fresh E2EStopEntry over fixture frames; pitch overrides the logged one"""
  s = e.E2EStopEntry(V_STOP)
  out, held, lines = [], [], []
  for fr in frames:
    out.append(s.update(fr["v"], fr["da"], fr["mss"], fr["vx"], True, pitch=fr["pitch"] if pitch is None else pitch))
    held.append(s.latched)
    if s.log_line is not None:
      lines.append((fr["t"], s.log_line))
  return out, held, lines


def step(s, *a, pitch=0.0):
  return s.update(*a, pitch=pitch)


def plan(v0, rest_t):
  """a speed plan falling linearly from v0 to 0 at rest_t, then held at 0"""
  return list(np.clip(v0 * (1 - T / rest_t), 0, None))


def crawl(v):
  return [v] * len(T)


class TestE2EStopEntry(OpenpilotTestCase):
  def test_constants(self):
    self.assertEqual((e.E2E_STOP_PLAN_T, e.E2E_STOP_PLAN_V, e.E2E_STOP_STILL_V), (2.0, 0.1, 0.1))
    self.assertEqual((e.E2E_STOP_PITCH_MIN, e.E2E_STOP_PITCH_MAX), (-0.044, 0.0175))
    self.assertEqual(V_STOP, 0.8)

  def test_fires_below_the_stopping_speed_when_the_plan_comes_to_rest(self):
    s = e.E2EStopEntry(V_STOP)
    self.assertFalse(step(s, 0.81, -0.5, False, plan(0.81, 1.5), True))      # above 0.8: the model's own rule only
    self.assertTrue(step(s, 0.79, -0.5, False, plan(0.79, 1.5), True))
    s = e.E2EStopEntry(V_STOP)
    self.assertTrue(step(s, 0.79, -0.5, False, crawl(0.099), True))         # just under 0.1 m/s 2 s out comes to rest

  def test_a_plan_that_does_not_come_to_rest_never_fires(self):
    # crawl(0.18): 130's give-way, where the model slowed to creep through at 0.18 m/s 2 s out, meaning to go on
    for vx in (crawl(0.5), crawl(0.31), crawl(0.3), crawl(0.18), crawl(0.1), plan(0.79, 4.0), plan(0.79, 2.5), [], [0.0] * 32,
               [0.0] * 34, [math.nan] * 33, None, "plan"):
      with self.subTest(vx=vx if not isinstance(vx, list) else len(vx)):
        s = e.E2EStopEntry(V_STOP)
        for _ in range(40):
          self.assertFalse(step(s, 0.6, -0.4, False, vx, True))
        self.assertFalse(e.plan_comes_to_rest(vx))         # the helper itself answers False (0.1 is not below 0.1), never raises

  def test_the_accel_rule_and_the_gate(self):
    for a, active in ((0.1, True), (0.5, True), (-0.5, False), (math.nan, True)):
      with self.subTest(a=a, active=active):
        s = e.E2EStopEntry(V_STOP)
        self.assertFalse(step(s, 0.6, a, False, plan(0.6, 1.0), active))

  def test_latched_while_should_stop_holds_and_released_with_it(self):
    s = e.E2EStopEntry(V_STOP)
    self.assertTrue(step(s, 0.78, -0.4, False, plan(0.78, 1.5), True))
    self.assertTrue(step(s, 0.6, -0.3, False, crawl(0.5), True))                # the plan recedes: still stopping
    self.assertTrue(step(s, 0.4, 0.09, False, crawl(0.5), True))
    self.assertFalse(step(s, 0.4, 0.1, False, crawl(0.5), True))                # the model asks to go: released
    self.assertFalse(step(s, 0.4, -0.3, False, crawl(0.5), True))               # and it needs the plan to come to rest again
    self.assertTrue(step(s, 0.4, -0.3, False, plan(0.4, 1.0), True))
    self.assertFalse(step(s, 0.85, -0.3, False, plan(0.4, 1.0), True))          # back above 0.8
    self.assertTrue(step(s, 0.7, -0.3, False, plan(0.7, 1.0), True))
    self.assertFalse(step(s, 0.7, -0.3, False, plan(0.7, 1.0), False))          # disengaged / chill mode

  def test_at_rest_the_models_own_flag_decides(self):
    # modeld's flag is the same rule on the UNSMOOTHED accel, and at a green light it drops before the smoothed accel
    # reaches 0.1: below E2E_STOP_STILL_V the latch lets go with it (held on the smoothed accel, 4 of 21 launches on 182
    # left the stopping state 0.10-0.14 s later than push18's)
    s = e.E2EStopEntry(V_STOP)
    self.assertTrue(step(s, 0.79, -0.4, False, plan(0.79, 1.5), True))          # latched on the approach
    self.assertTrue(step(s, 0.2, -0.3, False, crawl(0.0), True))                # still rolling: the latch holds the stop
    self.assertTrue(step(s, 0.0, -0.1, True, crawl(0.0), True))                 # at rest, the model's flag on
    self.assertTrue(s.latched)
    self.assertFalse(step(s, 0.0, 0.05, False, crawl(0.0), True))               # its flag drops, accel still under 0.1: released
    self.assertFalse(s.latched)
    self.assertFalse(step(s, 0.0, -0.1, False, plan(0.0, 1.0), True))           # and at rest nothing latches again
    self.assertTrue(step(s, 0.0, -0.1, True, plan(0.0, 1.0), True))             # the model's own flag still passes through
    self.assertFalse(s.latched)
    self.assertTrue(step(s, 0.79, 0.05, False, plan(0.79, 1.0), True))          # moving again, a new stop: a new latch
    # an engagement at a standstill takes no latch and writes no line
    s = e.E2EStopEntry(V_STOP)
    self.assertFalse(step(s, 0.0, 0.0, False, crawl(0.0), True))
    self.assertFalse(s.latched)
    self.assertIsNone(s.log_line)
    # 0.1 m/s is not at rest: the latch is taken there as anywhere below 0.8
    s = e.E2EStopEntry(V_STOP)
    self.assertTrue(step(s, e.E2E_STOP_STILL_V, -0.2, False, crawl(0.0), True))
    self.assertTrue(s.latched)
    self.assertIsNotNone(s.log_line)

  def test_the_models_own_flag_always_passes_through(self):
    rng = random.Random(7)
    s = e.E2EStopEntry(V_STOP)
    for _ in range(500):
      out = step(s, rng.uniform(0, 2), rng.uniform(-1, 1), True, rng.choice([crawl(1.0), plan(0.7, 1.0), None]), rng.random() < 0.5)
      self.assertIs(out, True)

  def test_never_raises(self):
    s = e.E2EStopEntry(V_STOP)
    for args in ((None, None, False, None, True), ("x", object(), False, object(), True), (math.inf, -math.inf, False, [1] * 33, True)):
      self.assertIn(step(s, *args), (True, False))
    self.assertIn(s.update(0.79, -0.4, False, plan(0.79, 1.5), True, pitch=object()), (True, False))

  def test_one_log_line_per_engagement(self):
    s = e.E2EStopEntry(V_STOP)
    lines = []
    for v, a, vx in ((0.9, -0.4, plan(0.9, 1.5)), (0.79, -0.42, plan(0.79, 1.5)), (0.6, -0.3, crawl(0.5)), (0.3, -0.2, crawl(0.5)),
                     (0.0, 0.0, crawl(0.0)), (0.0, 0.2, crawl(0.5)), (0.5, -0.3, plan(0.5, 1.0)), (0.4, -0.3, plan(0.4, 1.0))):
      step(s, v, a, False, vx, True, pitch=-0.0214)
      lines.append(s.log_line)
    logged = [(i, x) for i, x in enumerate(lines) if x is not None]
    self.assertEqual([i for i, _ in logged], [1, 6])                            # the latch, then the second engagement
    self.assertEqual(logged[0][1], "e2estop on v=0.79 a=-0.42 deg=-1.23 model=0")
    s = e.E2EStopEntry(V_STOP)
    s.update(0.79, -0.4, True, plan(0.79, 1.5), True, pitch=0.0)
    self.assertEqual(s.log_line, "e2estop on v=0.79 a=-0.40 deg=0.00 model=1")
    s = e.E2EStopEntry(V_STOP)                                                    # the model's flag alone logs nothing
    s.update(0.2, 0.0, True, crawl(0.5), True, pitch=0.0)
    self.assertIsNone(s.log_line)

  def test_the_log_line_cannot_change_the_output(self):
    # the same frames with and without a log line that fails to format give the same outputs and latch
    class BadFloat(float):
      def __float__(self):
        raise ValueError("no")
    a, b = e.E2EStopEntry(V_STOP), e.E2EStopEntry(V_STOP)
    for v in (0.79, 0.7, 0.6):
      oa = a.update(v, -0.4, False, plan(v, 1.5), True, pitch=0.0)
      ob = b.update(BadFloat(v), -0.4, False, plan(v, 1.5), True, pitch=0.0)
      self.assertEqual((oa, a.latched), (ob, b.latched))
    self.assertTrue(a.latched)

  def test_only_this_car_with_the_toggle(self):
    def cp(fp=CAR.HONDA_ACCORD_9G_AU, brand='honda', op_long=True):
      return SimpleNamespace(brand=brand, carFingerprint=fp, openpilotLongitudinalControl=op_long)
    sp = SimpleNamespace(flags=0)
    params = Params()
    params.put_bool("HondaDynamicTuningEnabled", True, block=True)
    self.assertTrue(e.e2e_stop_applies(cp(), sp))
    self.assertFalse(e.e2e_stop_applies(cp(CAR.HONDA_CIVIC), sp))
    self.assertFalse(e.e2e_stop_applies(cp(op_long=False), sp))
    self.assertFalse(e.e2e_stop_applies(cp(), SimpleNamespace(flags=HondaFlagsSP.ELESYS_STOCK_ACC.value)))
    self.assertFalse(e.e2e_stop_applies(SimpleNamespace(), sp))                 # never raises
    params.put_bool("HondaDynamicTuningEnabled", False, block=True)
    self.assertFalse(e.e2e_stop_applies(cp(), sp))

  def test_only_inside_the_grade_band(self):
    for pitch, fires in ((0.0, True), (-0.044, True), (0.0175, True), (-0.039, True),       # 161 147.6 was -2.23 deg
                         (-0.045, False), (0.018, False), (-0.1, False), (0.05, False), (None, False), (math.nan, False)):
      with self.subTest(pitch=pitch):
        s = e.E2EStopEntry(V_STOP)
        self.assertIs(s.update(0.79, -0.4, False, plan(0.79, 1.5), True, pitch=pitch), fires)
    s = e.E2EStopEntry(V_STOP)
    self.assertTrue(s.update(0.79, -0.4, False, plan(0.79, 1.5), True, pitch=0.0))
    self.assertTrue(s.update(0.6, -0.4, False, plan(0.6, 1.5), True, pitch=-0.06))        # once on, a grade change keeps it
    self.assertTrue(s.update(0.6, -0.4, True, crawl(1.0), True, pitch=0.2))               # and the model's own flag is never gated

  def test_replay_of_the_logged_approaches(self):
    """modelV2 frames (vEgo, action.desiredAcceleration, velocity.x, orientationNED pitch) of the three rlog red-light stops,
    of 161 126.9 (the crawl that kept rolling) and of the 130 give-way: 12b and 142 enter at 0.77-0.80 m/s, >= 1.8 s
    before the logged stop, and stay latched to the wheels reading zero; 161 147.6, whose plan never came under 0.1 m/s
    2 s out, is the model's own stop (0.29 m/s, 0.07 s before the logged stop); the two that kept rolling never enter."""
    if not os.path.exists(FIXTURE):
      self.skipTest("no fixture")
    cases = load_fixture()
    self.assertEqual(sorted(cases), sorted(EARLY + MODEL_ONLY + ROLLED_ON))
    for cid, c in cases.items():
      with self.subTest(case=cid):
        frames = c["frames"]
        out, held, _ = replay(frames)
        self.assertEqual(c["kind"], "no_stop" if cid in ROLLED_ON else "stop")
        if cid in EARLY:
          i = out.index(True)
          self.assertTrue(held[i] and not frames[i]["mss"], cid)        # the latch, not the model's flag
          self.assertTrue(0.77 <= frames[i]["v"] < 0.8, cid)
          self.assertLessEqual(frames[i]["t"], -1.8, cid)
          self.assertTrue(all(out[i:]), cid)
        elif cid in MODEL_ONLY:
          self.assertFalse(any(held), cid)
          self.assertEqual(out, [fr["mss"] for fr in frames], cid)       # the model's own flag on every frame: push18's stop
          i = out.index(True)
          self.assertTrue(0.25 <= frames[i]["v"] < 0.3 and -0.1 <= frames[i]["t"] < 0.0, cid)
          self.assertTrue(all(out[i:]), cid)
          # what the 0.1 m/s threshold costs here: at 0.3 it entered at 0.79 m/s, 1.87 s before the logged stop
          with mock.patch.object(e, "E2E_STOP_PLAN_V", 0.3):
            out3, _, lines3 = replay(frames)
          self.assertEqual(lines3, [(-1.874, "e2estop on v=0.79 a=-0.46 deg=-2.26 model=0")], cid)
          self.assertTrue(all(out3[out3.index(True):]), cid)
        else:
          self.assertFalse(any(out) or any(held), cid)
          out0, held0, _ = replay(frames, pitch=0.0)                       # and on the plan alone (161 126.9 was on a +1.5 deg rise)
          self.assertFalse(any(out0) or any(held0), cid)

  def test_the_130_give_way_does_not_latch(self):
    """130 113.9 s: a right turn at a give-way, no lead, no pedal. The model slowed the car to 0.78 m/s with its plan at
    0.18 m/s 2 s out - meaning to creep through - and asked to go 1.7 s later; the car rolled through at 0.39 m/s. With
    the design's 0.3 m/s plan threshold the rule latched there and, hands-off, the car would have stood still for about a
    second. With 0.1 no frame latches, no line is written, and the e2e candidate's flag is the model's own (off)."""
    if not os.path.exists(FIXTURE):
      self.skipTest("no fixture")
    frames = load_fixture()["130_113.9"]["frames"]
    self.assertEqual(len(frames), 100)
    self.assertFalse(any(fr["mss"] for fr in frames))                   # the model never asked to stop
    self.assertLess(min(fr["v"] for fr in frames), 0.8)                 # and the car was well inside the 0.8 m/s rule
    out, held, lines = replay(frames)
    self.assertEqual((any(out), any(held), lines), (False, False, []))
    # the frames do exercise the threshold: the same frames latch with the design's 0.3, at 113.88 s, as push19's first
    # build logged on the route - so this fails if the threshold is put back
    with mock.patch.object(e, "E2E_STOP_PLAN_V", 0.3):
      out3, _, lines3 = replay(frames)
    self.assertEqual(lines3, [(113.884, "e2estop on v=0.78 a=-0.76 deg=0.16 model=0")])
    i = out3.index(True)
    self.assertTrue(0.1 < float(np.interp(e.E2E_STOP_PLAN_T, T, frames[i]["vx"])) < 0.3)   # 0.18 m/s 2 s out
