# Red-light rolling: why the car stops past the plan (2026-11-04)

> **Shipped in push19 (2026-11-11):** Fix A (section 4) is on branch `push19` (sunnypilot `e2e_stop.py` and the
> planner hook) with opendbc `push19` (the soft stop's firm-up and MAX_ROLL by entry speed), as designed - grade band
> -0.044..+0.0175 rad unchanged - except that after the review the plan rule is 0.1 m/s, not 0.3 (corrections
> below), plus one `e2estop on v= a= deg= model=` log line per engagement.
> It ships together with the queue-stop governor from `DRIVES-17F-183-2026-11.md` section 3c (its dormant hold path
> removed). The next-drive checks are in `docs/CHANGELOG_SERIAL_STEERING.md` (push19). The text below is the report
> as written before the build.
>
> **Corrections from the push19 review (2026-11-11):**
> * **Section 4.4, "the owner was on the gas both times"** is not true of 130 at 113.9 s: no pedal until the gas at
>   +2.56 s, 0.86 s after the model's own go at +1.70 s, so the gas would not have prevented the stop. With Fix A the
>   car would have stood still at that give-way (right turn, no lead) from about +1.0 s to +2.1 s. 161 at 81.8 s no
>   longer latches (+2.33 deg, outside the grade band). Over 103 rlog routes with a pitch the rule latched on 3 of 8
>   slow roll-throughs (130, aa 437.8 - a light that turned green during the crawl - and de 518.6 behind a lead with the
>   gas 0.2 s later).
> * **Section 4.5's option was taken: the plan must be below 0.1 m/s at 2 s, not 0.3** (the owner's choice after the
>   review, 2026-11-12; `E2E_STOP_PLAN_V`). The give-way case no longer latches: at 130 113.9 the plan was 0.18 m/s 2 s
>   out, and a test now replays those frames (they latch with 0.3, not with 0.1). Over the 114 rlog routes de 518.6 and
>   9f 306.4 no longer latch either; every other no-lead red light and short stop latches on the same frame, and aa
>   437.8 still does (its plan was 0.04 m/s). What is lost: **161 145.8** (the stop at 147.6, behind a lead pulling
>   away, plan 0.14-0.21 m/s 2 s out) gets no early entry and is today's stop, the model's own at 0.29 m/s - the 0.21 m
>   (0.14-0.26) the replay saved there and its 0.41 m/s^2 at wheels-zero (0.26 today) are gone; and **170** (qlog)
>   latches one 2 Hz model frame later, 0.61 m/s instead of 0.76: 0.26 m saved in the replay's sim against 0.32 entered
>   at the 0.3 build's own latch (the table's 0.26 entered at the 0.8 m/s crossing), and 0.29 -> 0.20 in a second replay
>   with its plant fitted at each latch. In section 4 read the rule's "0.3 m/s at 2 s" as 0.1; in 4.3's table 161's row
>   is today's stop (the replay's sim with the entry at its 0.29 m/s: 0.01 m saved, 0.23 m/s^2 at wheel-zero) and 170's
>   is 0.26 m (0.22-0.30), 0.29 -> 0.43.
> * **At rest** the latch now lets go with the model's own flag below 0.1 m/s: modeld computes that flag on the
>   unsmoothed accel and publishes the smoothed one, so a latch held on the smoothed accel delayed launches by up to
>   0.14 s (4 of 21 on 182).

**Labels**
* **M** = measured. A stop id is the route hex plus seconds from route start. Local times are AEDT (UTC+11), except routes from before 02:00 on 4 Oct, which are AEST.
* **I** = inferred.
* **C** = read in the code.

**Conventions**
* Brake numbers are 0x1FA COMPUTER_BRAKE counts; 256 counts is full brake.
* Code references are openpilot `S:/OP/sp-live` @ `d510b78c9` (push18) and opendbc @ `14ec02f8`.
* Nothing was changed in any repo. Proposed code exists only as diffs in the scratchpad.

---

## 1. The short answer

**1. At a red light with nothing ahead, nothing asks the car to stop until it is at 0.28–0.29 m/s (C + M, 4 of 4 stops).**
* The model's own stop flag is hard-coded: `stop = v_ego < 0.3 and desired_accel < 0.1` (`openpilot/sunnypilot/modeld_v2/modeld.py:307`).
* The fork's 0.8 m/s stopping speed only reaches the MPC and cruise candidates (`longitudinal_planner.py:185,194`):
  * With no lead, the MPC follows a fake lead 50 m ahead. Its accel was +2.9 to +3.5 m/s² below 0.8 m/s, so it never asks to stop.
  * The cruise candidate is positive at a red light.
* Behind a stopped car the MPC asks at **0.77 m/s, 1.04 s before rest** (M, median of 50 queue stops).

**2. So the last 1.65–1.75 m below 1 m/s is a 2.5–3.4 s crawl in the PID state (M).**
* The car follows the model's gentle request of −0.2 to −0.4 m/s².
* Deceleration in the last second is 0.16–0.29 m/s², against 0.48 behind a car.

**3. The "lift" is real on flat roads (M).**
* The sent brake dips as the car slows through about 1 m/s:
  * 106 → 58 counts on 12b
  * 108 → 63 on 142
  * 128 → 72 on 170
* The car nearly coasts for 0.5–0.8 s (aEgo −0.08 to +0.09).
* The firm press, the 189-count hold, only arrives **0.55–0.64 s after the wheels read zero**. While the car is rolling it never comes.

**4. Result: all 4 hands-off red-light stops on record ended 0.90–1.55 m past the HUD's planned-stop figure as it stood 2–3 s before the stop (M).**
* The same happened on every build from the 10-06 build to push18.
* Behind a car, the median is +0.08 m.

**5. The soft-stop cap (105) is not the cause at red lights.**
* It was armed for only 0.02–0.08 s on these stops.
* Its cost there is about 0 m (M).

**6. Recommended: Fix A.**
* At a red light, ask to stop at 0.8 m/s, the same rule the MPC already uses behind a car, once the model's own plan is below 0.3 m/s 2 s out.
* Let the soft-stop ceiling firm up while the car is still rolling and slowing less than 0.5 m/s².
* Replayed (I):
  * Flat stops: +0.69 → +0.06 m and +0.66 → −0.19 m past where the plan said the car would rest.
  * Deceleration at the stop: 0.28 → 0.49 m/s².
  * Downhill stops improve by only 0.21–0.26 m.
  * Queue stops are unchanged.

---

## 2. What the data shows

### 2.1 Stops counted (M)

**Routes d0–170, re-extracted:** 145 engaged arrivals at standstill from above 3 m/s, with longActive at some point in the last 12 s.
* **54 clean**, meaning no pedal input from −6 s to rest:
  * **4 with nothing ahead.**
  * **50 behind a stopped car.** The car ahead was 3.0–6.3 m away, median 4.39 m [4.00, 4.92].
* **59 engaged approaches with no lead:**
  * 4 clean.
  * **51 ended with a brake take-over**, and 4 with some other take-over.
  * 41 of the 51 brake take-overs came at a moment when the model's plan had **no stop within its 10 s horizon**.
  * **6 came in the final crawl**, at 0.73–1.54 m/s, 0.5–1.25 s before rest, with the plan's stop 0.13–1.30 m ahead.

**push18 (routes 16a–170, all qlog):** 7 engaged approaches.
* 1 clean red-light stop: 170_233.0.
* 2 clean queue stops: 16b_388.3 and 16b_751.1.
* 4 take-overs:
  * 16a_189.1: gas for 0.4 s at 1.1 m/s, then brake.
  * 16a_229.6: other.
  * 16b_810.9: brake at 11.5 m/s.
  * 16e_152.8: no lead; brake at 13 m/s, 8.2 s before rest, with no stop planned (Tue 3 Nov 00:28).

**Correction to the first measurement pass.** It reported 27 clean red-light stops.
* 24 of them had a stopped car 3.8–5.9 m ahead.
* Before route 155 the lead flag is stored as `radarState.leadOne.status`. The first pass read only `.present`, so it counted every stop before route 155 as having no lead.
  * Example: 142 at 884–888 s has status true, with radar track 1496 closing from 10.8 to 3.9 m.
* Its findings describe queue stops, not red lights:
  * stopping entry at 0.78 m/s
  * the cap binding in 23 of 27 stops
  * a brake dip just before stopping entry
  * the "1 in 3 goes 0.5–1.55 m past"

### 2.2 The four red-light stops (M)

| stop | local time | build | soft-stop cap | grade | log | past the HUD figure at −3 / −2 / −1 s (m) | distance / time below 1 m/s | decel in last 1 s | stopping began |
|---|---|---|---|---|---|---|---|---|---|
| 12b_470.7 | Fri 9 Oct 18:04 | e6a18c839 | 125 | 0.0° | rlog | +1.08 / +0.79 / +0.44 | 1.72 m / 2.83 s | 0.25 | 0.288 m/s, 0.08 s before wheel-zero |
| 142_263.7 | Sun 18 Oct 17:42 | push9 55d9562b6 | 125 | −0.3° | rlog | +1.04 / +0.88 / +0.40 | 1.75 m / 3.42 s | 0.16 | 0.277 m/s, 0.05 s |
| 161_147.6 | Thu 29 Oct 23:47 | 6c61f095b | 105 | −2.2° | rlog | (no plan stop at −3 s) / +0.97 / +0.40 | 1.65 m / 2.54 s | 0.29 | 0.280 m/s, 0.02 s |
| 170_233.0 | Tue 3 Nov 01:24 | push18 d510b78c9 | 105 | −1.3° | qlog | +1.55 / +1.21 / +0.35 | 1.72 m / 2.81 s | 0.23 | 0.288 m/s, 0.01 s |

* The skeptic re-measured these from the raw parquet: +1.03 (12b), +1.00 (142) and +0.90 (161, from −2 s).
* 170 is a qlog route. Its plan is rebuilt from the 2 Hz drivingModelData. That rebuilt plan differs from the real model plan by a median 0.07–0.11 m (p90 0.18–0.28 m).

### 2.3 Red light compared with a queue stop (M)

| | red light (n=4) | queue (n=50) |
|---|---|---|
| stopping state begins | 0.28–0.29 m/s, 0.01–0.08 s before wheel-zero | 0.77 m/s [0.75, 0.79], 1.04 s [0.93, 1.18] before |
| distance / time below 1 m/s | 1.72 m [1.70, 1.73] / 2.82 s [2.74, 2.98] | 0.99 m [0.84, 1.12] / 1.53 s [1.32, 1.73] |
| decel in last 1 s | 0.24 m/s² [0.21, 0.26] | 0.48 m/s² [0.42, 0.53] |
| past the 0.5 m/s plan point, 1 s out | +0.35 to +0.44 m | +0.17 m [+0.03, +0.32] |
| past it, 3 s out | +0.90 to +1.55 m | +0.08 m [−0.40, +0.36] |
| soft-stop ceiling active while rolling | 0.02–0.08 s, never binding | 0.60 s [0.44, 0.82] (first pass) |
| roll after wheel-zero | 0.06 / 0.04 / 0.14 / 0.03 m (camera) | 0.007 m median, 0.11 max |

The HUD hides the figure when a real lead is within the figure plus 10 m (`hud_model.py:568-569`). So "planned stop versus where the car stops" is only visible at red lights with nothing ahead (I). That is why the complaint is about red lights.

### 2.4 By build (M)

**Red lights**
* There is one clean stop per build (table 2.2), all about 1 m past. No build trend can be measured from n=1 per build.
* No no-lead approach before the soft stop arrived (10-01) finished hands-off: 0 of 25.

**Queue stops**

| group | n (qlog) | past the HUD point @3 s | past the HUD point @1 s | vs the plan's own rest @1 s | stopping entry | decel in last 1 s | below 1 m/s |
|---|---|---|---|---|---|---|---|
| before the 09-27 merge, no soft stop | 13 (0) | +0.08 | +0.24 | −0.09 | 0.75 | 0.45 | 0.98 m |
| after the merge, no soft stop | 3 (0) | +0.03 | +0.08 | −0.21 | 0.76 | 0.59 | 0.78 m |
| cap 125 (10-03 → push9) | 20 (1) | −0.01 | +0.04 | −0.33 | 0.77 | 0.47 | 1.02 m |
| cap 105 (39cbb01be → push18) | 14 (10) | +0.20 | +0.21 | −0.28 | 0.78 | 0.48 | 1.19 m |

* **125 → 105:** +0.05 m against the plan's own rest point. The replayed cost of the cap itself is 0.00 m at 125 and 0.04 m at 105 (maximum 0.18).
* 10 of the 14 cap-105 stops are qlogs, so a 0.15 m difference cannot be separated from the measurement method.

**Push18's own changes (C):**
* AccelBoost is zero below 4.47 m/s.
* A_CRUISE_MIN of −0.5 and the cruise falling bound only matter when the set speed is below vEgo.
* None of them acts in the final approach to a red light.

### 2.5 Worst stops (M)

| stop | local time | build | lead | past the HUD point @3 s / @1 s | note |
|---|---|---|---|---|---|
| 170_233.0 | Tue 3 Nov 01:24 | push18 | none | +1.55 / +0.35 | red light, downhill −1.3°, qlog |
| 13d_380.8 | Sat 17 Oct 22:44 | push9 | 5.0 m | +1.50 / +0.51 | queue; soft stop released by max_roll |
| 12b_470.7 | Fri 9 Oct 18:04 | e6a18c839 | none | +1.08 / +0.44 | red light, flat |
| 142_263.7 | Sun 18 Oct 17:42 | push9 | none | +1.04 / +0.40 | red light, flat |
| 161_147.6 | Thu 29 Oct 23:47 | 6c61f095b | none | +0.97 @2 s / +0.40 | red light, −2.2° |
| 142_888.1 | Sun 18 Oct 17:52 | push9 | 3.9 m | +0.97 / +0.33 | queue |
| fc_271.9 | Fri 25 Sep 15:02 | pre-merge | 3.8 m | +0.89 / +0.43 | queue |
| 151_1140.6 | Fri 23 Oct 18:02 | 39cbb01be | 4.0 m | +0.88 / +0.60 | queue, qlog |
| 15d_520.2 | Wed 28 Oct 01:22 | 2984df599 | 6.3 m | +0.83 / +0.17 | queue, max_roll |
| 168_237.9 | Sun 1 Nov 17:09 | 6c61f095b | 3.3 m | +0.82 / +0.55 | queue, qlog |

**Crawl take-overs** (the owner braked in the last 0.5–1.25 s):

| stop | local time | speed | grade | brake drop | log |
|---|---|---|---|---|---|
| 115_343.1 | Sun 4 Oct 00:46 AEST | 0.73 m/s | | | |
| 115_500.8 | Sun 4 Oct 00:49 AEST | 1.25 m/s | −3.4° | | |
| 12d_458.3 | Sat 10 Oct 15:43 | 1.54 m/s | −3.0° | 150→96 | |
| 130_226.1 | Sun 11 Oct 18:00 | 1.41 m/s | | | |
| 154_163.3 | Mon 26 Oct 00:41 | 1.09 m/s | | 176→92 | qlog |
| e2_890.7 | (pre-merge) | 1.00 m/s | | | |

---

## 3. The causes (with the skeptic's corrections)

### 3.1 The stop request comes too late (C + M, 4 of 4 stops)

**Code path (C):**
* `longitudinal_planner.py:212` takes `min()` of the candidates.
* `:227` sets `output_should_stop = any(...)`.
* With no lead, only the e2e candidate can ask to stop, and modeld only asks below 0.3 m/s.
* The plan source was e2e for 100% of the last 6 s on all 4 stops.

**What follows (M + C):**
* The stopping state (`longcontrol.py:122-128`: ramp to stopAccel −0.8 at 0.8 m/s³), the soft-stop ceiling (`elesys_stop.py`) and the 189 hold all start after the car is in practice already stopped.
* The `hondastop` lines show this, e.g. `rise=settle t=0.64 roll=0.08` on 12b and `t=0.58 roll=0.02` on 161.

**Counterfactual (I, the skeptic's plant).** Entering stopping at 0.8 m/s with today's cap would have saved:
* 0.50–0.68 m on 12b and 0.67–0.88 m on 142 (flat).
* Only 0.09–0.17 m on 161 and 0.13–0.23 m on 170 (downhill).

### 3.2 The dip at about 1 m/s on flat roads: the "lift" (M)

**What happens.** It is a dip with a partial recovery, not a steady fall:
* 12b: 106 counts at 2.11 m/s → **58** at 0.71 → about 100 in the crawl.
* 142: 108 → **63** → 106.
* 170: 128 at 2.17 m/s → **72** at 1.06 → 118.
* Around the low point the car coasts for 0.5–0.8 s (aEgo −0.08 to +0.09). The counts then recover by 29–46 during the crawl.

**Where the drop below 2.2 m/s comes from:**

| stop | model's request easing | creep table adding back | change in the integrator |
|---|---|---|---|
| 12b | −95 counts | +37 | −2 |
| 142 | −83 counts | +44 | −18 |
| 170 | −51 counts | +28 | −11 |

The model's request goes from −1 to −2 m/s² to −0.2 to −0.4 below 1 m/s.

**What deepens it on the flat.**
* The PID integrator (`controlsState.uiAccelCmd`) is wound to +0.52 / +0.46 / +0.24 (12b) and +0.39 / +0.30 / +0.12 (142) at −3 / −2 / −1 s.
* That holds the command 25–55 counts below the planner's own request.
* For about 1.1 s the sum goes positive (+0.09 / +0.11). The brake law then fades the creep term (`carcontroller.py:45`), which drops about twice as many counts per m/s² (211–240 instead of 98.5).
* kp is 0, so nothing faster than the integrator corrects it. It unwinds at about 0.24 m/s² per s.

**Why the integrator is positive (M):** the brake law's creep offset is too high.
* At a given count the car decelerates 0.21–0.48 m/s² more than the creep table assumes, at every speed below 5 m/s (42 clean stops, 11.5k samples, grade-corrected).
* The slope is right. The pooled fit is 2.4 m/s² per 256 counts in the crawl band and 2.9 at 1.2–3 m/s, against the law's 2.6.
* The fitted push at zero counts is 0.29–0.60 m/s², against the table's 0.8–1.15.

**The learned brake gain was at its floor on both flat approaches (M, checked in logMessage for this report):**
* 12b: `brake=0.948 brakec=1.019` at −9.2 s, then `brake=0.850 brakec=1.018` at −4.2 s.
* 142: `0.850` against `1.006` at both −8.6 s and −3.6 s.
* 161: `0.971` against `0.985`.
* So the "0.985, negligible" figure holds only for 161. On the flat approaches about 15% fewer counts were sent above 1 m/s, fading to none at standstill (`dynamic_tuning.py:1088-1089`).
* Inference (I): the learner and the integrator are compensating for the same creep-offset error. The learner runs out of range at 0.85 and the integrator takes the rest. Not replayed.

### 3.3 Downhill: the pitch feed-forward fades out (M + C)

* The term `hill_accel = g·sin(pitch)·interp(v, [2, 5], [0, 1])` (`dynamic_tuning.py:833-836`) fades out between 5 and 2 m/s, and is 0 in the stopping state.
* The integrator has to take over the grade at ki 0.8–1.2 /s.
* **161 (−2.2°):**
  * The brake fell 266 → 132 counts between 5.6 and 1.5 m/s.
  * The integrator went −0.11 → −0.50 between −3 s and −1 s.
  * The car decelerated at −0.26 to −0.36 against aTarget −0.51 to −0.66.
  * There is no dip in the crawl itself.
* **170 (−1.3°):**
  * The integrator went +0.22 → −0.23 between −3.9 s and −2.0 s.
  * The car spent about 0.8 s at 1.05–1.10 m/s with decel of −0.03 to +0.12.
* This loss happens above 0.8 m/s, so an earlier stop entry cannot recover it.

### 3.4 The figure on the HUD (M + C)

* **What it measures:** `plan_stop_m` (`hud_model.py:606-617`) is the plan's position at the first node below **0.5 m/s**. The model plans another 0.22–0.54 m of crawl after that point.
* **What the definition costs:** 0.15 m (12b) and 0.19 m (142) against the point where the plan reaches wheel-zero speed.
* **When it disappears:** it is hidden below 1 m.
  * The last "1" was shown at −3.11 s with 1.98 m actually left (12b).
  * It was shown at −3.49 s with 1.79 m left (142).
  * On 161 no figure was ever shown.
* **The model's own speed estimate is biased (skeptic, M).**
  * The plan's starting speed is +16–19% above vEgo at 1–5 m/s with no lead (+3–8% with a lead).
  * It is 0.05–0.10 m/s below vEgo under 0.75 m/s.
  * So the figure reads long at range: on 142 at −6 s it showed 9.1 m with 7.5–7.8 m actually left. It then falls faster than the car moves, and in the crawl the car covers 0.13–0.20 m per second more than each plan says.
  * vEgo itself is right: within 0.7% of GPS above 6 m/s and within 1% of the raw wheel speeds down to 0.6 m/s.
* **The plan's stop point recedes:** by 0.72–1.06 m between −3 s and the stop. The model re-plans a fresh crawl from wherever the car is.
* In the end the car rests within 0.00–0.14 m of where the plan from 1 s earlier said it would.

### 3.5 Splitting the overshoot (skeptic, M), metres past the raw HUD figure

| stop | total | HUD definition | planner's aTarget softer than its own plan | car slowing less than aTarget | roll after wheel-zero |
|---|---|---|---|---|---|
| 12b, flat | +1.03 | 0.15 | 0.20 | **0.67** | 0.06 |
| 142, flat | +1.00 | 0.19 | 0.12 | **0.70** | 0.04 |
| 161, −2.2° (from −2 s) | +0.90 | 0.10 | **0.74** | 0.06 (plus 0.94 lost between −3 s and −2 s) | 0.14 |

### 3.6 What is not the cause (M unless marked)

* **The soft-stop cap at red lights:** 0 m, because it never binds.
  * In queue stops it costs a median 0.004 m (cap 125: 0.00 m; cap 105: 0.04 m, maximum 0.18).
* **The 32-count release limiter:** it never bound while rolling, in any of the 54 clean stops.
* **The comma pedal:** there was no pedal input from −8 s to +1 s on the 4 stops, and the gas command was 0 in the last 3 s of all 54 clean stops.
* **Stopping → PID exits:** 0 on the 4 red-light stops.
* **AccelBoost:** zero below 4.47 m/s (C).
* **Within the queue stops, entry speed shows no dose-response:** a higher entry speed goes with a *longer* crawl (ρ = +0.30, p = 0.03). The evidence that entry speed is the lever comes from the code, from the red-light vs queue comparison, and from the replays. No natural experiment within the queue stops shows it.

---

## 4. Recommended fix: A, red-light stop entry at 0.8 m/s plus the soft-stop firm-up

**Why A over B.**
* It extends a rule that already finishes every queue stop: the MPC's `v < 0.8 and a < 0.1`, which on 50 queue stops enters at 0.77 m/s and lands +0.17 m at 1 s.
* It does not add a new controller.
* Its replay was validated on the 50 queue stops: distance error median −0.009 m (range −0.066 to +0.007), counts RMS 1.9.
* It keeps the softer stop chosen in round 8.
* Fix B's extra gain is concentrated on the downhill stops, which is exactly where its own replay was least accurate (§5).

### 4.1 What it does

1. **Planner.** The e2e candidate also asks to stop when all of these hold:
   * `should_stop(v_ego, a_e2e, 0.8)` holds, which is exactly the MPC's rule;
   * the model's own plan is below 0.3 m/s at 2 s;
   * the pitch is between −2.5° and +1.0°.

   Once on, it stays latched while `v < 0.8 and a < 0.1`, so a receding plan cannot drop it. It lets go when the model's accel reaches 0.1 (the light has changed) or the car is back above 0.8 m/s. The model's own flag passes through untouched.

   It is built only for this car with openpilot longitudinal, stock ACC mode off and `HondaDynamicTuningEnabled` on. On every other path it is `None`.
2. **Soft stop.**
   * **Firm-up:** while the wheels turn, once the command has sat at the ceiling for 0.3 s, a deceleration weaker than 0.5 m/s² raises the ceiling by 150 counts/s per m/s² of shortfall (at most 75 counts/s).
     * It only rises, never past the command.
     * It freezes at wheel-zero.
     * An unknown aEgo counts as the full shortfall.
   * **MAX_ROLL:** grows with the entry speed: 1.9 s up to 0.6 m/s, plus 2.5 s per m/s above that, so 2.4 s at 0.8 m/s.
     * With the planner change alone, MAX_ROLL fired in 17 of 24 replays, inside the last 0.3 m/s. With this change it fired in none.

### 4.2 Code sketch (diffs in `.../redstop/fix-softstop/fix/`)

**New file: `openpilot/sunnypilot/selfdrive/controls/lib/e2e_stop.py`** (`E2EStopEntry`, `e2e_stop_applies`, about 90 lines).

**`openpilot/selfdrive/controls/lib/longitudinal_planner.py` @ d510b78c9:**
* Import after line 20 (next to the `STOPPING_SPEED` import).
* Build in `__init__` after line 81: `self.e2e_stop = E2EStopEntry(self.v_ego_stopping) if e2e_stop_applies(CP, CP_SP) else None`.
* After line 189 (`is_e2e = self.is_e2e(sm)`), before the candidates at :207-210:
  ```python
  if self.e2e_stop is not None:
    orientation = sm['carControl'].orientationNED
    output_should_stop_e2e = self.e2e_stop.update(v_ego, output_a_target_e2e, output_should_stop_e2e,
                                                  sm['modelV2'].velocity.x, is_e2e and not reset_state,
                                                  pitch=orientation[1] if len(orientation) == 3 else None)
  ```

**`opendbc/sunnypilot/car/honda/elesys_stop.py` @ 14ec02f8:**
* After :126, add the constants `SOFT_STOP_FIRM_DECEL = 0.5`, `SOFT_STOP_FIRM_GAIN = 150.`, `SOFT_STOP_FIRM_MAX_ERR = 0.5`, `SOFT_STOP_MAX_ROLL_FROM_V = 0.6` and `SOFT_STOP_MAX_ROLL_PER_MS = 2.5`.
* Add `firm_cb` and `max_roll` to `SoftStopState`.
* Add `soft_stop_max_roll(v)` after `soft_stop_cap` (:163-169).
* Set `max_roll` at entry (:189-192).
* Add the firm-up block after `settled` in the rolling branch (:211-213).
* Replace `SOFT_STOP_MAX_ROLL` with `st.max_roll` at :219.
* Append `firm=N v=entry_v` to the `hondastop` line.

**Not changed:** `carcontroller.py`, `longcontrol.py`, the 189 hold, the release limiter, brake320, the pump rule and the HUD.

### 4.3 Counterfactual (I)

The replay runs the real `soft_stop_ceiling` inside a re-implementation of the brake block. It uses 6 plants: K = 1.5 / 2.4 / 2.9 m/s² per 256 counts, delay 0.3 / 0.5 s. Values are the median, with the range in brackets.

| stop | metres saved | past the plan's rest at entry, today → fix | past the HUD figure at −3 s, today → fix | decel at wheel-zero, today → fix |
|---|---|---|---|---|
| 12b, flat | 0.63 (0.52–0.70) | +0.69 → **+0.06** (−0.01…+0.17) | +1.03 → +0.40 | 0.33 → 0.53 |
| 142, flat | 0.85 (0.72–0.91) | +0.66 → **−0.19** (−0.25…−0.06) | +1.00 → +0.15 | 0.28 → 0.48 |
| 161, −2.2° | 0.21 (0.14–0.26) | +0.77 → **+0.56** | +0.90 → +0.69 | 0.26 → 0.41 |
| 170, −1.3° (qlog) | 0.26 (0.19–0.32) | (no plan in the qlog) | – | 0.29 → 0.51 |

* **Time below 1 m/s:** 2.82 → 1.89 s.
* **Deceleration:** at most 0.59 m/s² at wheel-zero and at most 0.64 at rest. That is inside round 8's 0.5–0.6 and below the old harsh stop's 0.92.
* **The dip:** time below 90 counts on the two flat stops goes 2.77 → 0.50 s and 1.93 → 0 s.
* **Estimated jerk:** 8.2 → 9.6 m/s³ (IMU regression, r = 0.57). For comparison, queue stops today: 10.3 at cap 105 (n=4), 9.9 at cap 125 (n=19), 15.2 before the soft stop (n=16).
* **Cross-check:** the skeptic's independent plant gives 0.50–0.68 / 0.67–0.88 / 0.09–0.17 / 0.13–0.23 m for the entry alone. Fix A's entry-alone figures are 0.62 / 0.82 / 0.10 / 0.19.
* **Queue stops (50 stops × 6 plants = 300 replays):**
  * rest point moves a median 0.000 m (at most 0.22 m shorter);
  * decel at wheel-zero 0.57 → 0.57;
  * MAX_ROLL fires 48 → 0 times, WEAK 11 → 8.

### 4.4 When the entry rule fires on the logs (M)

* **Red-light stops:**
  * The 3 rlog stops: at 0.78 / 0.79 / 0.79 m/s, 2.50 / 3.19 / 1.87 s before the stop. It held to the stop with 0 breaks.
  * 170 (qlog): 0.76 m/s, 1.94 s before the stop.
* **Queue stops:** at 0.74–0.80 m/s, the same moment as the MPC's rule, so nothing changes there.
* **Give-way / slow-turn false positives:**
  * Over 45 rlog routes it fired on 2 approaches that did not end in a stop: 130 at 113.9 s (Sun 11 Oct about 17:58: v 0.78 m/s, plan 0.18 m/s at 2 s, the car slowed to 0.39 m/s then went on to 5.2 m/s) and 161 at 81.8 s (Thu 29 Oct about 23:46).
  * The owner was on the gas both times.
  * Without the gas, the car would have been braked toward a stop until the model's accel reached 0.1.
* **The plain v < 0.8 rule without the plan check** would also have fired at 161 at 126.9 s. There the car went on to 7 m/s. The plan check prevents that.

### 4.5 Risks

* **Give-ways (above).** A stricter test, requiring the plan below 0.1 m/s within 2 s (as Fix B does), would avoid them:
  * On 12b and 142 it fires on the same frame (−2.50 s and −3.19 s).
  * On 161 the plan never went below 0.1 m/s before the stop, so that stop would lose its early entry.
  * This is a choice to make before building; it has not been replayed.
* **Downhill.** The stopping state's −0.8 has no grade term.
  * From 0.8 m/s, synthetic replays need 1.04–1.45 m at −2° to −3° when K is 2.4 or more, but 1.6–3.8 m at K 1.5.
  * Hence the −2.5° limit.
  * 2 of the 6 crawl take-overs (115_500.8 at −3.4°, 12d_458.3 at −3.0°) are outside the band and keep today's behaviour.
* **Uphill.** The 105 cap plus gravity gives 0.49–0.74 m/s² at wheel-zero at +1°, and 0.66–0.84 at +2°. Hence the +1° limit.
  * All 54 clean stops on record were between −2.5° and +2.6°; 3 were above +1°.
* **Stopping short.** On 142 the car may stop 0.06–0.25 m short of the plan.
  * Today the model's accel after a red-light stop is 0.01 m/s² or less (3 of 3), so it does not ask to creep. This is unproven with the fix.
* **Wet road or weak brake.** The firm-up compensates up to the command's −0.8 net. WEAK and MAX_ROLL stay as backstops.
* **CMBS / AEB (C).**
  * The output is still `min(command, ceiling)`.
  * The firm-up only moves the ceiling toward the command, never past it.
  * Panda forwards stock AEB whenever its brake is at least ours, so a lower command can only start that forwarding earlier.
  * The planner change only adds stop requests.
* **MAIN_ON=0 stand-down (C).** Untouched. The rule is not built in stock ACC mode, and it is inactive with long control off or reset.

### 4.6 Tests

**opendbc** (run in a scratch copy of 14ec02f8):
* `test_elesys_stop.py`: **35 pass**, with 2 updated and 5 new. The new ones cover:
  * the firm-up is proportional and bounded;
  * an unknown aEgo counts as the full shortfall;
  * it acts only at the ceiling;
  * it freezes at wheel-zero;
  * it never raises the command;
  * MAX_ROLL scales with entry speed.
* `tests/test_elesys.py`: **142 pass**. `test_panda_allows_every_flashed_frame` fails only because it needs the panda build; it fails on the original code too.
* `test_dynamic_tuning_integration.py`: all checks pass.

**openpilot:**
* New `tests/test_e2e_stop.py`: **16 pass**, run with stub imports. The fixture holds the logged model frames and pitch for 12b, 142 and 161, plus the 161 crawl at 126.9 s.
* **Still to add:** a case in `test_stopping_debounce.py` checking that the planner builds `e2e_stop` only for this car with the toggle on. It needs the compiled MPC, so it has not been run.

### 4.7 Drive check that would confirm it

The drive needs full rlogs uploaded. qlogs lack modelV2 and the `hondastop` lines, and carry carOutput at only 10 Hz.

For each red-light stop with nothing ahead:
1. The stopping state begins at 0.74–0.80 m/s, 1.5–2.5 s before wheel-zero. Today it is 0.28 m/s and 0.01–0.08 s.
2. The `hondastop` line shows `rise=settle … firm=N v=0.7x`, with no `max_roll` and no `weak`.
3. The car rests within 0.3 m of the plan's rest point at entry on the flat (today +0.66 to +0.77), and within 0.4 m of the HUD figure seen 3 s out (today +0.90 to +1.55).
4. The 0x1FA counts do not fall between stopping entry and wheel-zero, and fall by no more than 40 below 2.2 m/s (today 46–51 on the flat).
5. IMU deceleration at the stop is 0.4–0.65 m/s², and jerk is about 11 m/s³ or less.
6. There is no switch from stopping back to the PID within 3 s after rest, and fewer crawl take-overs (today 6 of 55 no-lead approaches).

Across the drive:
7. Queue stops still rest about 4.4 m from the lead, with no MAX_ROLL.
8. The pitch is logged at each stop. Stops outside −2.5° to +1° still enter at 0.28 m/s.
9. Every stopping entry is followed by a rest within 3 s. Any that is not is a give-way false positive (§4.4).

---

## 5. Alternatives

### 5.1 B: the planner "stop point" (`.../redstop/fix-approach/`)

**New module** `openpilot/sunnypilot/selfdrive/controls/lib/stop_point.py` (268 lines). It acts below 3 m/s, in experimental mode, with no real lead:

1. **Target.** It takes the plan's rest point (the first node below 0.1 m/s) and places it on the road using integrated vEgo, less the model frame's age.
   * It arms once that point has held for 3 frames.
   * The target moves nearer freely but never further. The exception is a jump of 2 m or more held for 3 frames, meaning the light changed.
2. **Request.** `aTarget = min(aTarget, −decel)`, where the decel profile ends at the target and tapers to 0.5 m/s² at rest.
   * It looks 0.3 s ahead for the brake's lag.
   * It asks for at most 0.8 m/s² at 0.5 m/s and 1.2 m/s² at 1.5 m/s and above.
3. **Stop entry.** Below 0.8 m/s it latches shouldStop when the plan rests within 2 s, or when the distance is at most v²/1.0 + 0.1 m. It does not do this on grades steeper than 3°.

**Hooks in `longitudinal_planner.py`:**
* line 22: the import;
* line 84: build it, gated on the toggle;
* after line 220, before the reentry ramp: the `min()` and the `stoppoint` log line;
* line 227: `… or stop_point_stop`.

**opendbc is untouched**, including the soft stop.

**Replay.** 4 plants × 2 ways of replaying the model's request. Values are the median of 8.

| stop | past the nearest rest point, today → B | vs the HUD figure at −3 s | decel in the last 0.3 s | count fall below 2.2 m/s |
|---|---|---|---|---|
| 12b | +0.87 → −0.15 | +1.00 → −0.02 | 0.54 → 0.52 | 71 → 38 |
| 142 | +0.77 → −0.22 | +1.02 → +0.02 | 0.55 → 0.47 | 76 → 14 |
| 161 | +1.22 → +0.44 (0.26–0.64) | +1.23 → +0.45 | 0.42 → **0.71** | 52 → 52 |
| 170 (qlog) | +2.35 → +0.09 (−0.58…+0.61) | +2.19 → −0.07 | 0.47 → **0.69** | 59 → 14 |

**Arming scan (M).** Over every engaged experimental stretch of the 41 rlog routes 10f–161, it armed 9 times, and every one ended at rest within 3 s:
* 3 completed stops;
* 5 owner take-overs;
* 1 where a lead came in.

It did not arm at 130 t113.8 or 161 t81.8. On 5 of the 6 crawl take-overs, the replay stops 0.12–2.15 m before the point where the owner braked.

**Its replay is less certain where it gains most.** Replaying today's controller, it reproduced the real stops within:
* +0.02 m (12b) and −0.09 m (142);
* −0.18 m (161);
* −0.61 m (170).

**Why it is the alternative, not the recommendation:**
* It adds a second controller, braking up to 1.2 m/s² on a target built from a biased plan.
* It finishes slope stops firmer (0.68–0.87 m/s² at the stop, against the 0.5–0.6 chosen in round 8).
* On flat roads it stops 0.15–0.22 m short of the model's rest point, though at the HUD figure. Whether the model then creeps forward is not measured.
* Its MAX_ROLL behaviour with the unchanged soft stop was not reported.
* Its stop entry on its own leaves 161 at +1.22 m and 170 at +2.31 m, so on slopes all of its benefit comes from the governor.

**Choose it if** fixing slopes matters more than keeping the soft finish.

### 5.2 Considered and rejected (I, replay)

* **Entering at 1.0 m/s instead of 0.8:** gains only +0.07–0.20 m, and moves queue-stop entry from about 0.77 to about 0.97 m/s.
* **Starting the stopping ramp from aTarget:** gains 0.00–0.04 m.
* **Removing the cap:** gives 0.76–1.20 m/s² at rest, i.e. the harsh stop.
* **B's governor without the early entry:** +0.27 m, but 0.94 m/s² at the stop.
* **Freezing or lag-compensating the integrator:** stops 0.4–0.9 m short.
* **Keeping the pitch feed-forward down to 0.3 m/s, or holding the brake gain at its converged value:** these act at 2–6 m/s. The replay moved by up to 1.7 m depending on how the request was replayed, so its numbers cannot be trusted.
  * Also, on 142 the pitch follows the braking (−2.1° at 1.1 m/s² falling to −0.2°), so it is partly nose-dive, not grade.

### 5.3 Separate follow-ups (not part of this fix)

* **Re-fit the brake law's creep offset.** The zero-count push measures 0.29–0.60 m/s², against the table's 0.8–1.15. This is the root of the positive integrator and probably of the learner's 0.85 floor. It touches every low-speed brake, so it needs its own replay.
* **HUD:** show the plan's rest point (below 0.1 m/s) instead of the 0.5 m/s point, which is +0.22–0.32 m further, and keep a figure below 1 m. This changes only what is shown, not where the car stops.

---

## 6. What is not known

* **The sample is small.** There are only **4** clean red-light stops in the whole history (2 flat, 2 downhill), and **1** on push18 (170, qlog: 10 Hz brake, 2 Hz plan). Treat each per-stop metre as ±0.2–0.3 m.
* **All fix numbers are simulations** on a fitted brake plant. R² is 0.47–0.53 at 0.8–3 m/s but only 0.18–0.34 in the crawl band. The plant also overstates the roll after wheel-zero (0.11–0.17 m in the plant against 0.03–0.08 m measured by camera).
* **Settle jerk cannot be simulated.** The IMU proxies are weak (r = 0.57 for A's regression, 0.32 for B's check).
* **The 41 of 51 no-lead brake take-overs** came while the model had no stop planned within 10 s. It is not known whether the model reacts late to lights or the owner brakes early. Neither fix acts on these.
* **Whether the model creeps forward** after a stop short of its rest point is not measured.
* **How often the give-way false positive happens** on push18: its routes are qlog-only, so the 2 Hz scan there is weak.
* **The learner at its 0.85 floor** on flat red-light approaches is measured on 2 stops. Its effect has not been replayed, and the queue-stop comparison (ratio 1.00 over 92 lines) was not re-checked for this report.
* **The cap-105 vs cap-125 difference** in queue stops (+0.05 m) is inside the qlog/rlog measurement difference.

## Files

All in the study's scratchpad, `scratchpad/redstop/` (not in the repo):

* **The chain:** `trace/CHAIN.md`
* **Corrected stop table:** `diagnose/full/stops.csv`
* **Independent re-measurement:** `challenge/` (`c1_out_four.txt`, `c4_out.txt`, `c5_misc_out.txt`)
* **Fix A:**
  * code: `fix-softstop/fix/` (`e2e_stop.py`, `longitudinal_planner.diff`, `elesys_stop.diff`, tests)
  * replay: `fix-softstop/s5_nolead.csv`, `s6_queue.csv`, `s7_summary.csv`
  * false-positive scan: `s2_events.csv`
* **Fix B:** `fix-approach/` (`stop_point.py`, `planner.diff`, `test_stop_point.py`, `final_out.txt`, `arm_scan_out.txt`, `takeovers_cf.csv`)
