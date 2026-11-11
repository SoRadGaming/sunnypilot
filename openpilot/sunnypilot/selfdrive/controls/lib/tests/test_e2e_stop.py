"""FORK(HONDA_ACCORD_9G_AU): the red-light stop entry (e2e_stop.py).

The unit tests pin the rule (v < STOPPING_SPEED, the model's accel < 0.1, the model's plan below 0.3 m/s 2 s out), the
latch and its release, the grade band, that the model's own flag always passes through, that it never raises, the one
log line per engagement, the build gate (e2e_stop_applies), and a replay of the logged approaches (fixture). The
planner's build gate is in selfdrive/controls/tests/test_stopping_debounce.py.
"""
import gzip
import json
import math
import os
import random
from types import SimpleNamespace

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


def step(s, *a, pitch=0.0):
  return s.update(*a, pitch=pitch)


def plan(v0, rest_t):
  """a speed plan falling linearly from v0 to 0 at rest_t, then held at 0"""
  return list(np.clip(v0 * (1 - T / rest_t), 0, None))


def crawl(v):
  return [v] * len(T)


class TestE2EStopEntry(OpenpilotTestCase):
  def test_constants(self):
    self.assertEqual((e.E2E_STOP_PLAN_T, e.E2E_STOP_PLAN_V), (2.0, 0.3))
    self.assertEqual((e.E2E_STOP_PITCH_MIN, e.E2E_STOP_PITCH_MAX), (-0.044, 0.0175))
    self.assertEqual(V_STOP, 0.8)

  def test_fires_below_the_stopping_speed_when_the_plan_comes_to_rest(self):
    s = e.E2EStopEntry(V_STOP)
    self.assertFalse(step(s, 0.81, -0.5, False, plan(0.81, 1.5), True))      # above 0.8: the model's own rule only
    self.assertTrue(step(s, 0.79, -0.5, False, plan(0.79, 1.5), True))

  def test_a_plan_that_does_not_come_to_rest_never_fires(self):
    for vx in (crawl(0.5), crawl(0.31), plan(0.79, 4.0), [], [0.0] * 32, [math.nan] * 33, None, "plan"):
      with self.subTest(vx=vx if not isinstance(vx, list) else len(vx)):
        s = e.E2EStopEntry(V_STOP)
        for _ in range(40):
          self.assertFalse(step(s, 0.6, -0.4, False, vx, True))

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
    """modelV2 frames (vEgo, action.desiredAcceleration, velocity.x) of the three rlog red-light stops and of 161 126.9,
    the crawl that kept rolling: the stops enter at 0.77-0.80 m/s, >= 1.8 s before the logged stop, and stay latched to
    the wheels reading zero; the crawl never enters."""
    if not os.path.exists(FIXTURE):
      self.skipTest("no fixture")
    with gzip.open(FIXTURE, "rt") as f:
      cases = json.load(f)
    self.assertGreaterEqual(len(cases), 4)
    for c in cases:
      with self.subTest(case=c["id"]):
        s = e.E2EStopEntry(V_STOP)
        out = [s.update(fr["v"], fr["da"], fr["mss"], fr["vx"], True, pitch=fr["pitch"]) for fr in c["frames"]]
        if c["kind"] == "stop":
          i = out.index(True)
          self.assertTrue(0.77 <= c["frames"][i]["v"] < 0.8, c["id"])
          self.assertLessEqual(c["frames"][i]["t"], -1.8, c["id"])
          self.assertTrue(all(out[i:]), c["id"])
        else:
          self.assertFalse(any(out), c["id"])
          s = e.E2EStopEntry(V_STOP)                           # and on the plan alone (it was on a +1.5 deg rise)
          self.assertFalse(any(s.update(fr["v"], fr["da"], fr["mss"], fr["vx"], True, pitch=0.0) for fr in c["frames"]), c["id"])
