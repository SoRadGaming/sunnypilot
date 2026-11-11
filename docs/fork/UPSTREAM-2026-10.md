# Upstream review 2026-10-29: what arrived since the 2026-09 sync, and what to do with it

This is a review done before any merge. It lists what upstream added since the fork's 2026-09-27 sync, what each item
would do on this car, and whether to take it now, take it with the next sync, or skip it. It follows the method and
format of `docs/fork/UPSTREAM-2026-09.md`. Every repo was read-only: no checkout, merge or commit. Merge previews are
`git merge-tree` runs in a throwaway bare clone (`forkmap/mt/sp.git`, merged tree `091a09e1e`).

| | sunnypilot | opendbc | panda |
|---|---|---|---|
| fork now | `558016374` push17 (2026-10-29) | `469d12c7` (sp-master) | `74a0adce` |
| fork's upstream base | `a5f44653d` (2026-09-14) | `f95f996f` | `74a0adce` |
| upstream sunnypilot tip | `6f7a2c94c` (2026-10-29) | `aa9bff6f` (pinned by upstream) | `8a16e089` (pinned by upstream) |
| new upstream since base | 282 commits, 26 on the first-parent line; includes commaai syncs #2036 `3323aafb5` (10-06) and #2059 `0739fe823` (10-18) | 116 | 2 syncs (#126, #127), about 35 content commits |
| commaai not yet in sunnypilot | 33 (`35e78a9d9..8ba9f4bae`) | 20 | `f38f504f` and later |
| fork-only | 337 commits (310 non-merge), 268 paths (182 added, 86 modified) | 108 commits, 56 files | none (upstream's pin) |
| files changed by both sides | 41 | 16 | - |

The car: HONDA_ACCORD_9G_AU (`HondaFlags.ELESYS`, right-hand drive), Nidec-style brakes, comma pedal, openpilot
longitudinal, MADS, a comma 4 (mici UI), and steering through the EPS-LKAS gateway board.

**The rule from 2026-09 still applies.** Take upstream, but keep this car's behaviour wherever upstream changes it.
Every other car gets upstream's behaviour. Code that keeps the car's behaviour is gated on `HONDA_ACCORD_9G_AU` or
`HONDA_ELESYS` and tagged `FORK(...)`.

**How this was checked.** The upstream changes were sorted into 19 candidates (C1-C19). An evaluator checked each one
against the code and the owner's routes (`S:/OP/sunny_logs`, `S:/OP/comma_logs`), and then a skeptic checked the
evaluator. The verdicts below already include the skeptics' corrections; the main ones are listed under
[Corrections](#corrections-made-during-the-review). Notes and scripts for each candidate are in the folder beside this
file (`C1-spi-revert/`, `C1-skeptic/`, … `forkmap/`).

Car impact column (same meanings as 2026-09):
- **changes this car**: arrives with a sync and does something on this car.
- **kept**: upstream changed it for every car; the recommendation keeps this car's behaviour.
- **available**: opt-in.
- **internal**: no behaviour change, but a merge or tooling concern.
- **n/a**: does not apply to this car.

**What is in sunnypilot and what is comma-only.** The owner tracks sunnypilot only. Checked with
`git merge-base --is-ancestor <sha> refs/remotes/upstream/master` (sunnypilot `6f7a2c94c`, 2026-10-29). Everything is
in sunnypilot except these commaai commits. They reach the fork only when sunnypilot next syncs commaai, or by a hand pick:

| commit | part of | what it means without it |
|---|---|---|
| `2ab952d5e` no ramp delay on set-speed drops | C4 | sunnypilot brings only `263e8d196`, the -0.5 floor for every car, which is the half that hurts this car. Keep -1.2 in the merge. |
| `6f68efea6` pandad reads the panda debug log (0xb6) | C12 | sunnypilot's panda `8a16e089` moves the debug log, so today's panda log stops arriving in routes. Pick it with the sync. |
| `e37616881` names the new panda faults (bit-27 mask) | C12 | the phantom relayMalfunction stays latent, as it is today |
| `730c7c663` swaglog datagram socket | C16 | nothing; it was "wait" anyway |
| `14652aacb` camera-client caching | C19 | nothing new; the leak is as it is today |
| opendbc `b8a277e7`, `1bce882c` CANParser | C14 | nothing; it was "wait" anyway |

---

## The short answer

1. **Now, as its own push: C1, the pandad SPI busy-wait revert.** It is an 11-line cherry-pick that applies cleanly.
   It frees about 21 percentage points of core 3 and brings CAN back to 100.000 Hz, which makes `cumLagMs` usable
   again. Ship it **after** push17's first drive has been analysed with check16, so it does not blur the push16/17
   verdict. Optional in the same push: the one-hunk mask of the phantom "Harness Relay Malfunction" (C12, from
   commaai `e37616881`).
2. **The full sync later, not now.** Do it once push16/17 has been judged and one C1 drive has been read, aiming for
   mid-November. sunnypilot has pulled in commaai about every two weeks (09-16, 10-06, 10-18). If its next commaai
   sync lands by then, take that one: it would probably bring AGNOS 20.1, `2ab952d5e` and `6f68efea6` in one OS
   flash. If not, sync onto `6f7a2c94c` and port those two by hand.
3. **Estimated cost of the sync:** about 3-4 working days of merge work, then about a week of normal drives to verify.
   The 15 content conflicts are the smaller part. The bigger part is about 8 silent breakages that auto-merge and then
   crash or misbehave at runtime (see [Merge hot-spots](#merge-hot-spots)). Two of them would leave the car with no
   car interface or no longitudinal plan.
4. **Decisions the owner must make before the sync:**

| decision | upstream default | recommendation |
|---|---|---|
| cruise deceleration floor (C4) | -0.5 m/s² for every car | Port `2ab952d5e`, gated to set-speed drops. Keep -1.2 for this car after a set-speed drop or a forceDecel, and take upstream's -0.5 for braking back to the set speed after a gas press. |
| gas-override boost (C6) | on for every car | A `HONDA_ACCORD_9G_AU` param, **off** by default until the owner says yes |
| engage set speed (C13) | max(vEgo, 40 km/h) | Set `InitialCruiseSpeedKph` to 105 on the device, which reproduces today's behaviour |
| distance-button hold (C5) | does nothing (the experimental toggle is gone) | Swallow the hold, so it does not step a bar |
| LongIndicator on the comma 4 (C15) | shown | Hide it for this car. The owner rejected a following-distance item on 2026-10-03, and it has 3 bars against his 4. |
| lane change into a road edge (C7) | a nudge overrides the edge | Keep the hard block for this car, as decided on 2026-10-12 |
| Blendful (C18) | off, alpha | Leave off for now |
| Navigation (Alpha) toggle | appears on non-release branches | Leave off |

---

## The relayed error: Cabana "Invalid CM_ SG_ line format"

The error was
`[.../opendbc/dbc/generator/honda/accord_au_2015_fork_469d12c7.dbc:327] Invalid CM_ SG_ line format: CM_ SG_ 506 AEB_REQ_3 "HONDA_ELESYS: bit 27, …`.

- **Cause.** The Cabana that raised it is the Qt build from June 2026 at `~/openpilot/tools/cabana`, built
  2026-06-03. The fork's opendbc `469d12c7` has two comments that span several lines:
  `CM_ SG_ 506 AEB_REQ_3` and `CM_ SG_ 506 CMBS_BRAKE`, at `opendbc/dbc/generator/honda/_nidec_common.dbc` lines 60-64.
  The generated DBC carried them. The old Qt loader can join a multi-line comment only when the lines end in LF.
  - C17 reproduced the exact message at line 327 on a **CRLF** copy of the generated file.
  - The same file with LF endings loads in that old build: 54 messages, 455 signals.
  - The loader now in the fork and upstream trees (`06a73f538`, plain C++ with `commentComplete`) loads both copies.
- **Current state.** The copy at that path was rewritten today at 19:35. It has LF endings, 697 lines, and both
  comments on one line (AEB_REQ_3 is now line 599, CMBS_BRAKE line 595), so it loads.
- **To stop it happening again**, any one of these is enough:
  - Rebuild Cabana from the fork tree (`S:/OP/sp-live` or `~/sp-merge`). Since `3a13b67b6` that is the ImGui build,
    and Qt is gone.
  - Keep generated DBCs LF. Upstream's new `.gitattributes` `* text=auto eol=lf` does this for files inside the repo
    after the sync.
  - Put the two `_nidec_common.dbc` comments on one line in opendbc, so old tools can read them too.
- **Car effect:** none. This is PC only.

---

## Ranked candidates

The ranking is by what each item is worth to this car, after the skeptics' corrections.

| # | item | refs | verdict | how / when | effort | risk |
|---|---|---|---|---|---|---|
| 1 | C1 pandad SPI busy-wait revert | commaai `910c08e08` (#39038) | **adopt now** | cherry-pick as its own push | trivial | low |
| 2 | C4 cruise decel: no delay on set-speed drops; keep this car's floor | `2ab952d5e` (commaai only), `263e8d196` | **adopt, gated** | hand port at the sync | small | medium |
| 3 | C12 panda fault telemetry and the panda log | panda `20cd3584`, `d2c0ce91a`, commaai `6f68efea6`, `e37616881` | **adopt** | comes with the sync, plus 2 small picks | small | low |
| 4 | C2 keep native crash reports in routes | `6bbdf8ad1` (#38790) | **adopt** | a FORK resolution of about 5 lines in `tombstoned.py` at the sync | trivial | low |
| 5 | C8 GPS start-up aiding plus the mapd position repair | `4c5355776` `1623441a9` `6eb63e045`, sp `09b2f4bbe` (#2064) | **adopt (must pair)** | comes with the sync | trivial | low |
| 6 | C3 Ratekeeper resync after a stall | `fe7ccf958` (#39095) | **adopt with a card fix** | comes with the sync, plus a never-reset `cumLagMs` counter in `card.py` | small | low |
| 7 | C11 MADS duplicate no-entry alert fix | sp `27c132984` (#1949) | **adopt** | comes with the sync | trivial | low |
| 8 | C10 modeld seeds curvature while lateral is inactive | `2b09bc94a` (#39091) | **adopt** | comes with the sync | trivial | low |
| 9 | C13 configurable initial cruise speed | `24c26487f` `75b2ccca6` `fcf4b0d39` | **forced; set 105** | comes with the sync | trivial | low |
| 10 | C5 Autospeed: Experimental/chill removed, DEC gone | `f21bfc36b` `f50108b4a` `0d57eadd7` …, sp `5ec0c0219`, `2149006ec` | **forced; accept, no chill path** | comes with the sync | medium | medium |
| 11 | C9 updater can install pre-move releases | `64be6c80d` (#39063) | **adopt** | comes with the sync; test one rollback | trivial | low |
| 12 | C19 camera-client caching on the mici view | commaai `14652aacb` (#39166, tici only) | **adopt as a port** | fork port at the sync (draft in `C19/port/`) | small | low |
| 13 | C15 mici lead bar and LongIndicator | `78dccf0b4`, `035a447d1` | **take the bar, hide the indicator** | comes with the sync; re-apply `real_lead`, make the bar cheaper | small | low |
| 14 | C6 gas-override acceleration boost | `ab8c84c39` (#39015) | **owner decides; param, off** | comes with the sync | trivial | low |
| 15 | C14 CANParser frequency fix and batched logs | opendbc `b8a277e7`, `1bce882c` (commaai only) | **wait** | sunnypilot's next opendbc sync | trivial | low |
| 16 | C16 swaglog over a Unix datagram socket | commaai `730c7c663` | **wait** | later sync; check for drops under a flood first | small | medium |
| 17 | C18 Blendful lateral policy (alpha) | sp `97135965e` `24f531b83` | **skip for now** | merge cost is paid anyway (capnp @3) | small | medium |
| 18 | C7 nudge overrides a road edge | sp `a06366ce9` (#2049) | **skip for this car** | take upstream's structure and keep the hard edge block for this car | small | low |
| 19 | C17 Cabana from the fork tree | `06a73f538`, `06d76bdb2`, `3a13b67b6` | **do now (PC only)** | rebuild Cabana; this answers the relayed error | trivial | none |

### 1. C1: revert the pandad SPI busy-wait (adopt now)

- **What it does.** It removes the two 400 µs spin-waits that `aa0ac919b` (#38464) added to pandad's SPI path. pandad
  runs at FIFO 54 on core 3. The fork's `spi.cc` (blob `369032a5`) is identical to `910c08e08^`, so the revert
  applies cleanly. The result is byte-identical to what the car ran in July (build `4e06ff3e4`, route 1f).
- **Measured on this car.**

  | measure | route 1f (July, no spin) | routes 157 and 15d (now) |
  |---|---|---|
  | pandad CPU, started | 23.5 % | 44.7 % / 44.3 % |
  | core 3 busy | 42.5 % | about 70 % |
  | CAN rate | 99.999 Hz | 99.52-99.57 Hz |

  The 99.5 Hz is why `cumLagMs` drifts. The +21 pp matches the arithmetic of the spins.
- **Value: moderate, mostly diagnostic.** It brings the COMM-ISSUE 9.9 July baselines back into comparison and frees
  room for hardwared, which push16 moved to cores 0-3. It does **not** touch the commIssue root cause, which is on
  cores 4-6. Nothing on this car acts on the `cumLagMs` drift.
- **Cost, corrected by the skeptic.** `spiErrorCount` returns to about 3/s, as in July (3.09/s on 1f). These are NACKs
  that happen *before* the panda executes the request, so there are no duplicated sendcan blocks. On route 1f: 5630
  panda-side errors and 2256 host "got NACK" lines, with zero ACK timeouts, bad checksums or transfer failures.
- **First-drive check.**
  - CAN about 100.00 Hz; `cumLagMs` slope about 0; pandad about 24 %; core 3 about 45-50 %.
  - Read pandad's rlog `logMessage`. "got NACK" lines are expected. Any "timed out waiting for ACK", "bad checksum",
    "RX data len larger" or "transfer failed" means act.
  - `spiErrorCount` is a uint16 and wraps after about 5.9 h at 3/s.
- **Fallback, corrected.** If errors climb, shorten **both** waits to about 100-150 µs, not only the middle one. About
  half of July's NACKs were header NACKs.
- **Treat it as interim.** The full sync replaces `spi.cc` with "simple SPI" (`50319fa70`: request ids and CRC-32,
  needs panda 8a16e089). With the revert in, the sync gives 3 conflict hunks in `spi.cc`. Resolve them by taking
  upstream's file whole, together with `panda_comms.h` and the panda bump.

### 2. C4: cruise deceleration after set-speed drops (adopt, gated)

- **There are two upstream pieces, and they pull in opposite directions.**
  - `263e8d196` (already in sunnypilot) changes `A_CRUISE_MIN` from -1.2 to **-0.5** for every car. In the merge it
    applies **silently**, with no conflict marker.
  - `2ab952d5e` (commaai only, #39127) starts the jerk-limited lower bound from
    `min(a_cruise_prev, previous output)`. A drop then no longer waits for a stale positive `a_cruise` (+0.7 to +2.0
    while the car is below its set speed) to drain first.
- **Effect on this car, with the skeptic's held-plan simulation over 31 drops on routes 10f-15d.** Median distance
  driven more than 2 km/h over the new speed:

  | variant | median distance over |
  |---|---|
  | today (-1.2) | 81 m |
  | -1.2 + `2ab952d5e` | **49 m** |
  | -0.8 + `2ab952d5e` | 57 m |
  | -0.5 + `2ab952d5e` (upstream) | 81 m |

  So `2ab952d5e` cuts about 40 %, not the about 85 % the first simulation claimed. Route 129 t=812.9 (110→100):
  logged 4.4 s / 99 m; the port gives 1.6 s / 24 m.
- **Drops applied at the sign (SLA "now", NSW zones).** These start with no wind-up, so only the floor matters there.

  | drop | -1.2 | -0.5 |
  |---|---|---|
  | 110→100 | 3.4 s / 83 m | 5.4 s / 142 m |
  | 80→60 | 5.7 s / 101 m | 11.0 s / 204 m |
  | 60→40 | 5.6 s / 71 m | 11.0 s / 146 m |

  These distances are measured from the moment the set speed changes. The armed limit applies 4.0-4.4 s after "now",
  which is 20-70 m past the sign.
- **Risk the skeptic found.** -1.2 combined with `2ab952d5e` makes braking back to the set speed after a gas lift-off
  harsher. That is the floor's most frequent use: 98 episodes in 5 h. Over 116 lift-offs, median `a_cruise` at 1 s goes
  from -0.57 to -0.73, and an overtake-and-lift such as 14c t=801.8 starts braking 0.5 s after lift-off instead of
  3.3 s. Nobody upstream has run this combination.
- **Recommendation.**
  - Port `2ab952d5e` gated to a `v_cruise` decrease, meaning set speed, SLA, SCC target or forceDecel within the last
    few seconds. That is the commit's stated purpose.
  - Use a split floor for this car in `stopping_tune.py`: -1.2 (or -1.0) after a drop or a forceDecel, and -0.5 when
    returning to the set speed after an override.
- **Trap.** sunnypilot's `update_targets()` overwrites `self.output_a_target` before `get_cruise_accel`, so a literal
  port lets SCC-V's own accel bypass the jerk limit, which is a brake jab. Capture the previous output before
  `update_targets`. Add a unit test: SCC-V entering, `a_cruise` wound up, and |Δoutput| ≤ j·dt.
- **Also.** `2ab952d5e` removes about 2-3 s of wind-up delay before a DM no-response or soft-disable forceDecel starts
  braking, which is a safety gain. `bend_ease`'s `DECEL` 0.6 is unreachable under a -0.5 floor.

### 3. C12: panda fault telemetry and the panda debug log (adopt)

- **What it does.** With panda `20cd3584` (in pin 8a16e089), an NMI or HardFault resets the panda and reports
  `pandaStates.nmiReset @40` / `hardfaultReset @41`. Those are in the qlog on every frame.
- **Today, at 74a0adce,** a fault hangs the panda in `Infinite_Loop` with the relay GPIOs frozen.
  - Nothing reconnects: the SPI `connected` flag is never cleared.
  - `pandaStates` stops, hardwared goes offroad after 5 s, and **the route stops recording**.
  - The cuatro's alert audio also goes through the panda, so alert sound would stop or stick.
- **After the sync.** The route continues and carries the flag. But `comms_healthy` is sticky, so after a fault reboot
  mid-drive `can` stays empty and invalid until key-off. You would see canError or commIssue plus controlsMismatch.
  Brown-out resets are not flagged, and nothing here would have helped the KTuner episode (the panda stayed up then).
- **Two small picks are needed**, because sunnypilot does not have them:
  - commaai `6f68efea6`: pandad reads the panda log with request `0xb6` instead of `0xe0`. At 8a16e089, `0xe0` is
    gone, so without this the panda log forwarding that **works today** goes dead, and the ring fills with
    "NO HANDLER".
  - The first hunk of commaai `e37616881`: panda fault bit 27 (`FAULT_INTERRUPT_RATE_SOUND_DMA`) is counted but not
    mapped, so it becomes a phantom entry 0 = `relayMalfunction` and an IMMEDIATE_DISABLE. That latent bug exists in
    the fork **today**; whether it has ever fired was not checked. It can go in the C1 push.
- **CPU.** `78cf6990` makes "can_push failed!" print unconditionally, so a queue overflow becomes about 17 extra SPI
  reads per pandad loop. Cap the `0xb6` drain at 2-4 reads per loop in the fork's pick.
- **Optional.** Before `pandad.py` resets or recovers the panda, log `nmi_reset`/`hardfault_reset` from health.
  Otherwise a fault offroad is erased.

### 4. C2: keep native crash reports in routes (adopt)

- **Today.** sunnypilot's `sentry.init()` returns True, so `tombstoned` always logs
  `{'tombstone': '<exe> - Signal - <function>'}` at ERROR level, which reaches the qlog.
- **After the sync** (`6bbdf8ad1`), the gate is `comma_remote and "commaai" in git_origin and …`, which is False on
  SoRadGaming/openpilot. Every native crash would then be **deleted without a log line**. That would arrive silently:
  the file auto-merges.
- **Value: marginal, as insurance (skeptic's correction).** `managerState` already records `exitCode` (for example -11)
  in the qlog, and a crashed process is not restarted, so the name and signal reach the route anyway. The tombstone
  line adds only the crash function, and only if `apport-retrace` works on AGNOS. Across 124,817 `managerState` rows
  (75 routes, about 17 h) no process died.
- **Better resolution than the one-liner.**
  - Always parse and log the tombstone line, then delete the file.
  - Keep upstream's gate for copying the `.crash` file into `<log_root>/crash`. A gated-on copy carries a CoreDump of
    up to 100 MB. The uploader sends `crash/` files before qlogs, and the 12 h metered hold never applies to them (an
    upstream path-match bug).
  - Use its own `FORK(...)` marker, not `COMM-ISSUE`, add its own small guard test, and add a README inventory row.
- **Also.** Removing Sentry drops a synchronous `log_fingerprint` flush from card start (up to 2 s on a half-working
  link) and stops sending the dongle ID and fingerprint to sunnypilot's Sentry.

### 5. C8: GPS start-up aiding, plus #2064 (adopt; the two must go together)

- **What it does.** pigeond sends the host's UTC and the last position (if under 7 days old) at init, and the minimum
  satellite elevation becomes 0°. ubloxd saves `LastGPSPosition` once a minute, and the key is now **BYTES**.
- **#2064 (`09b2f4bbe`) must come with it.** Without it, `mapd_manager` seeds the key with the str `"{}"`, gets a
  TypeError, and its main thread dies. With it gone there is no `liveMapDataSP`: no OSM limit, no NSW zones, no NSW
  cameras, and no SLA map source. `NswZoneMapData` inherits the fix through `super().update_location()`. The fork's
  tests use fakes that would not catch a str write.
- **Value on this car: modest.**
  - Time to first fix over 139 routes: median 4.8 s, p75 19.4 s, p90 33.1 s. 17 of 119 routes were moving before the
    first fix.
  - The slow starts (20-54 s) are offline starts at the far end of a trip with no AssistNow download. These have valid
    system time, so the new time and position aid should help them most.
  - Cold boots (fc, 114, 13d, 14c) have no valid system time at pigeond init, so the new aid is skipped on exactly
    those starts.
- **Correction.** The shortlist and the must-know list said ubloxd's 60 s write blocks its loop. It does not.
  `Params.put(block=False)` goes to `putNonBlocking` on an async writer thread, so no ParamsWriter is needed.

### 6. C3: Ratekeeper resyncs after a stall (adopt, with a card fix in the same push)

- **What it does.** `keep_time()` loops skip missed frames instead of bursting through them after a stall. The loops
  that benefit:
  - mapd_manager: 1 Hz, FIFO 5 on cores 0-3. It ran 7-8 back-to-back ticks after route 158's 8.4 s `/data` stall, and
    fed the NSW matcher the same fix several times.
  - proclogd, soundd, micd, the UI touch thread, sensord's temperature poller, and sunnylink statsd.
- **What it does not do.** Nothing for cores 4 or 6: card, controlsd and selfdrived only call `monitor_time()`.
- **The catch.** card publishes `carState.cumLagMs = -rk.remaining`. After this change that value becomes a 0-10 ms
  sawtooth, and check16 would misjudge card on core 6:
  - With no fix, a healthy card reads as starved: residual p99 4.4-4.8 ms against 0.8-0.9 ms.
  - The evaluator's "unwrap the resets on a qlog" fix is **wrong**. It hides real starvation: 1.0-1.2 ms when the
    truth is 3.7-3.9 ms.
  - Process replay and the fork's own sync replay both ignore `cumLagMs`, so nothing would catch it.
- **Required in the same push:** a `FORK(COMM-ISSUE)` never-reset counter for card's `cumLagMs`
  (`next_t += 0.01` per frame), with a guard test. Also update COMM-ISSUE.md:629-634 and :721,
  CHANGELOG_SERIAL_STEERING.md:343, and check16's header and comments.
- **Timing.** Do not cherry-pick it while push16/17 is being judged by `cumLagMs`.

### 7. C11: MADS duplicate no-entry alert (adopt)

- `update_alerts()` also clears NO_ENTRY events when the current alert is ENABLE or USER_DISABLE.
- **Simulated on the fork's own alert raisers** (diagnostic tool, VSA stored fault, gateway override pause, MADS off,
  P gear). Today the refusal plays twice, with a second "openpilot Unavailable" about 0.2 s after a MADS toggle or a
  silent pause. With #1949 it plays once.
- No change when the refusal comes on the same frame MADS turns on (S4) or with repeated presses (S5).
- All 85 fork alert tests pass both ways.
- `selfdrived.py` is a conflict file anyway, so keep the line in that resolution.

### 8. C10: modeld seeds the previous curvature while lateral is inactive (adopt)

- When `latActive` is false, `prev_action.desiredCurvature = controlsState.curvature`. Lateral restarts often on this
  car (MADS, gateway pauses, the driver-override pause), so the first command after a resume starts from the measured
  curvature. That should shrink the step the board sends to the EPS.
- **Merge.** modeld now subscribes `controlsState`. The SubMaster of **both** modelds must be the union with the fork's
  `carStateSP`; either side alone raises KeyError.
- **Check.** The first engaged seconds after a gateway pause.
- This candidate was not separately simulated.

### 9. C13: initial cruise speed (forced; set 105)

- `InitialCruiseSpeedKph` (default 40, range 40-145) replaces the 105 km/h experimental initial. This car has
  `pcmCruise` False, so it engages at `clip(max(vEgo, setting), 40, 145)`.
- **On routes 153-160,** every first engage set 105 and SLA then pulled it down to the limit within a few seconds
  (preActive, then active).
- **At 40,** engages at 15-37 km/h (route 160, 15d) set 40. The SLA prompt then flips from "press −" to "press +".
  If he ignores it, the car holds a flat 40 in a 60 or 80 zone, which would look like the slow-climb complaint had got
  worse.
- **Set 105** in Settings after the sync. The key is PERSISTENT, not BACKUP, so a sunnylink restore will not carry it.
- card re-reads the param at 10 Hz on core 6. That is a read only, and small.

### 10. C5: Autospeed (forced; accept it, with no chill path)

- **Driving barely changes.** Every analysed route ran with ExperimentalMode on and DEC off. e2e is already in the
  planner's min(), and the chill accel, turn and coast limits never applied. Do not carry a chill path for this car;
  it would re-add `get_max_accel`, the turn and coast limits, CruiseHelper and the toggle to the most conflicted file.
- **What he loses:**
  - the "DEC on" lever for the slow climb;
  - the cruise-law briskness (about 1 m/s² at 40-80 km/h) that he named on 2026-10-12 as the path if he wants a
    quicker climb later. After the sync that would need a fork planner change, including `get_max_accel`;
  - the long-press toggle.
- **What breaks in the merge if not fixed:**
  - `longitudinal_planner.py`: the auto-merged close-follow calls at about L144 and L181 still use `self.is_e2e(sm)`
    and `self.allow_throttle`. **plannerd would crash-loop on the first plan.** Compute close follow's coast trip
    fork-side from `gasPressProbs[1] > 0.4 or vEgo <= 2.5`; `notE2e` becomes dead.
  - `selfdrived.py`: a kept `get_bool("ExperimentalMode")` raises UnknownKeyName and kills the params thread
    (personality, MADS, lane-block and car-stock reads). `CruiseHelper` and `experimental_mode_switched` go.
  - `honda_stock_acc.py`: `REMOVED_KEYS` still lists the removed keys, so the snapshot is silently dropped and stock-ACC
    mode stops preserving SCC-V, SCC-M and SLA.
  - Tests: `selfdriveState.experimentalMode` is now in `deprecated`, so 5 fork test files raise AttributeError.
    `test_distance_bars` imports the deleted `cruise_helpers`.
- **Rollback trap.** The first boot of the synced build deletes the ExperimentalMode key (`clearAll`). The pre-sync
  fork defines it with no default, so a rollback to 558016374 or 49c99f88d boots in **chill**: no stopping for lights
  without a radar lead, initial set speed 40. Give the fallback branch a default of "1" before pushing the sync, or
  write it into the rollback notes.
- **mici files: merge both sides, do not "take upstream".** The conflicts in `augmented_road_view.py` and
  `model_renderer.py` are the HUD rail against nav, radar dots against the lead bar, and `real_lead` against the lead
  de-dup. Taking upstream would lose the HUD rail and radar dots and draw held leads.
- **Stock ACC mode.** Upstream now seeds the MPC from the measured vEgo/aEgo there, which changes `crash_cnt` and so
  FCW. Check the FCW counts on one stock-ACC drive.

### 11. C9: the updater can install pre-move releases (adopt; comes with the sync)

- The change is four lines. `launch_chffrplus.sh` flashes the old release's AGNOS, and `updated.py` falls back to
  `system/hardware/tici/agnos.json`.
- It answers the README's "a pre-move snapshot cannot install", but it turns a rollback into an AGNOS downgrade
  (19.9 → 19.7). Test one real rollback install, parked, before calling the `pre-<date>` snapshot a rollback.
- This candidate was not separately simulated.

### 12. C19: camera-client caching on the mici view (adopt as a small port)

- commaai `14652aacb` creates one VisionIpcClient per stream and reuses it, because destroying one does not free its
  msgq reader slot. It fixed only the tici UI. The comma 4 switches road↔wide below and above 5-10 m/s, so each
  switch takes a slot.
- **Evidence is mixed.**
  - July routes 14, 1f and 20 logged modeld "frames out of sync" exactly at the **14th** switch to wide.
  - No route since September shows it, including 129 (18 switches), 150 (16) and 13f (15).
  - So it is unproven that it still bites. The port is cheap insurance either way.
- A lazy-client draft is in `C19/port/cameraview-port.diff`.

### 13. C15: mici lead bar and LongIndicator (take the bar, hide the indicator)

- **Lead bar.**
  - It reads `radarState` directly, so `real_lead()` has to be re-applied in the new `_update_leads()`. Otherwise an
    ELESYS held lead is drawn as a white bar on empty road, and its made-up distance can de-dup a real `leadTwo` away.
  - **CPU.** About 274 µs per frame with 2 leads on a PC. Times 4-6 for the device, that is about 4-10 % of a core-5
    core onroad, on a core at 85-91 %. Port plain-Python geometry: 17 µs against 153 µs per bar. Also skip the draw
    when the fade is below 1/255.
- **LongIndicator.**
  - It sits **left**, under the driver-monitoring icon (not top-right, as first described).
  - It shows personality+1 bars, so 1-3 against the fork's 4 dash bars. Aggressive and 1-bar close follow both show 1.
  - The owner rejected a following-distance item on 2026-10-03.
  - Hide it for this car.
- **Also.** `test_radar_dots` must accept `_draw_path()`.

### 14. C6: gas-override acceleration boost (owner decides)

- **What it does.** After a gas override while the model was limiting, it adds 0.05 m/s² per override, up to 0.2, to
  the e2e candidate. It is speed-scaled from 16 to 32 km/h and kept until disengage; every brake press clears it.
- **Replayed on routes 129-160 (about 4 h engaged).**
  - A boost was held on 43 % of the time engaged with the foot off, and it actually raised the plan on 21 %.
  - Episodes: median 37 s, longest 17.6 min.
- **It does not fix the slow climb.** It reaches 22-52 % of no-lead climbs, and those stay about 5-10× below the
  cruise law.
- **It cuts against "brake sooner".** It softens the model's gentle braking by up to 0.2 m/s². Of the boosted mild
  model braking, about 176 s of 289 s had a radar lead, where the model was braking earlier than the MPC. Lead brake
  assist is still shadow-only, so nothing counteracts it.
- **It is invisible.** No UI cue. `longitudinalPlan.accelBoost` logs the total, not the applied amount.
- **The merge is clean.** It lands after the close-follow lift, which is the right order, and `@40` does not clash.
- **Recommendation:** a 9G_AU param, default **off**, until the owner says yes. Do not pool LBA or bend-ease shadow
  statistics from before and after the sync.

### 15. C14: CANParser frequency off-by-one and batched invalid logs (wait)

- Learned timeouts on slow frames get slightly longer (3.3 Hz: 2.4 s → 3.0 s). The per-message "not valid" logs become
  one line per bus every 10 s, which is less spam when the board (0x700-0x70F) or the BLR board (0x620-0x62F) goes
  quiet. The batching can also hide a second onset inside the 10 s window.
- It is small and commaai-only. Let it come with sunnypilot's next opendbc sync.

### 16. C16: swaglog over a Unix datagram socket (wait)

- It saves CPU and memory in every daemon, because there is no ZMQ context per process.
- **Risk.** Drops become silent kernel drops. Replayed through the new path, route 145 (the KTuner bus-off, where
  pandad floods "sendcan too old to send") would **lose 289 ERROR lines** with the default queue, or 135 with 8 MB
  buffers. Those are exactly the lines the owner diagnoses from.
- A cherry-pick conflicts in `pyproject.toml` and `uv.lock` and leaves ZMQ in the test.
- **Wait for sunnypilot.** When it comes, rate-limit pandad's flood line and size the queue.

### 17. C18: Blendful lateral policy (skip for now)

- **Correction.** It **is** available to this owner. He runs modeld_v2 with the WMI V12 tinygrad bundle, and his
  CameraOffset -0.12 only works there.
- After a sync the model catalogue goes from v22 to v25. The hash check resets his selection, so he must re-select WMI
  V12 and let `modeld_warmup` build its cache offroad. **Put that in the first-boot list.**
- If he ever trials Blendful, the fork should:
  - gate it on `latActive`;
  - turn it off with a blinker on, because below 52 km/h it would pull against a manual lane change;
  - make the toggle offroad-only;
  - hide the 190×76 readout pill;
  - road-check the kerb lane.
- Cost: about 1-2 ms per frame on core 7.
- The merge cost exists either way: ModelDataV2SP @3-@9, and `modelDataV2SP` listed twice in `ui_state`.

### 18. C7: a nudge overrides a road edge (skip for this car)

- **On 2026-10-12 the owner declined this exact PR and kept the refusal.** The merged version is the same code.
- **Corrected counts.** Refusals could only be logged from route 134 on. Of 17 refused nudges, 10 were below 52 km/h
  and 7 at 52 or above. Of those 7, 4 were followed by a lane change within 0.4-2.8 s.
- **The merge cannot keep "ours".** `auto_lane_change.py` auto-merges a new signature, so the fork's 2-argument call
  raises TypeError in modeld at the first blinker at 52 km/h or above.
- **Resolution.**
  - Take upstream's structure and pass `torque_applied and not (edge_hard_block and edge_detected)` as the 4th
    argument, so upstream's `lane_change_blocked` carries the hard block.
  - Keep `and not below_lane_change_speed`.
  - Do the refusal test after the `alc` call.
  - Pin it with tests, including that both modelds publish `laneChangeNudgeRefused` (moved to @10).

### 19. C17: Cabana from the fork tree (do now, PC only)

See [The relayed error](#the-relayed-error-cabana-invalid-cm_-sg_-line-format). Upstream's Cabana is now ImGui (Qt
removed) and adds heatmaps, multiplexed-signal filtering, docked charts and recorded CAN without a DBC. Its live
device streams need webrtcd, which is commaai-only for now. Re-check `dbc/eps-lkas-gw.dbc` in it.

---

## Forced changes a sync brings

### Would break the car if missed

1. **`HondaFlags.HAS_BSM = 1024` is the same bit as the fork's `HondaFlags.ELESYS = 1024`.** Checked in both
   `values.py`.
   - With both kept, IntFlag makes ELESYS an alias of HAS_BSM. Every 9G_AU CarParams then carries HAS_BSM, carstate
     looks up `DBC[...][Bus.body]`, and card raises KeyError at start, so there is **no car interface**.
   - Move ELESYS to 8192, which is free on both sides (4096 is BOSCH_TJA_CONTROL, 2048 is HYBRID upstream), and add a
     unique-flag test.
   - `CP.enableBsm` becomes `has_bsm(CP, CP_SP)`.
   - Old routes' `flags` 1024 will decode as HAS_BSM.
2. **opendbc "Remove car mass"** (`b3bd79a6`), steerRatioRear and lateralParams removed, and the Honda torque lookup
   removed (`cdf27c4b`).
   - 9G_AU `CarSpecs(mass=...)` raises TypeError at import.
   - About 30 `ret.lateralParams` writes and the `test_elesys` asserts fail.
   - STEER_MAX now comes from CarControllerParams, and its default of 2560 gives an identical 0x0E4.
   - paramsd and car_kf must be taken together.
   - Offline replays that build a VehicleModel from pre-merge CarParams will be wrong.
3. **Panda, opendbc and pandad move in lockstep.** These must land in the **same push**, or the comma 4 cannot talk to
   its panda:
   - panda 74a0adce → 8a16e089 (simple-SPI wire protocol, `safety_tick(void)`);
   - opendbc's `safety_tick` signature;
   - pandad `spi.cc` / `panda_comms.h` (`50319fa70`).

   The panda reflashes on the first boot. `eps_lkas_flasher.py` uses the rewritten Python panda SPI layer, so **run
   one gateway-board update after the merge**.
4. **Autospeed runtime breaks** (C5): the plannerd crash-loop, selfdrived's params thread dying, and the stock-ACC
   snapshot drop.
5. **The lane-change TypeError** in modeld (C7).
6. **LastGPSPosition is BYTES.** Take #2064 with it, or the map sources go dead (C8).
7. **The capnp ordinal clash.** Upstream Blendful takes ModelDataV2SP @3-@9; move the fork's
   `laneChangeNudgeRefused` from @3 to @10.
   - Old routes then decode the refused-nudge bit as `blendfulGoingAround`. Keep refusal history coming from
     `onroadEventsSP` @32.
   - `modelDataV2SP` is now in the qlog at 2 Hz.
   - The fork's OnroadEventSP @26-@36 are free. `experimentalModeSwitched` becomes DEPRECATED @14.
8. **Keep the fork's `pandad.py`**, as sunnypilot did. commaai's rewrite (`d3f0aab96`, `cb1d6f11a`) would break the
   EPS-LKAS and BLR flasher hooks (`flash_if_requested(panda_serials[0])`, `skip_panda_reset`, `watch_for_request`).
9. **The tombstoned gate** (C2) and **`6f68efea6`** (C12) both arrive silently.

### Changes every drive

- **The cruise floor -0.5** (C4), unless the fork keeps the car floor. **AccelBoost** (C6). **Initial set speed 40**
  (C13).
- **The new DM model "Super Leicht" and a "sleep" distraction type** (`5ae0da0e4`, sleepProb > 0.75). Watch for false
  sleep alerts at night or with sunglasses (right-hand drive). Expect small conflicts with the fork's `policy.py`
  Params handle.
- **Louder warning sounds.** sunnypilot took `28917bb3a`'s wavs, with `AMBIENT_DB` still 26, so every warning gets
  louder, including the board alarms. This touches the owner's earlier "no volume features" decision, so tell him.
- **The stock modeld/DM runner is reworked** (tinygrad ONNX compiler, `file_chunker` removed, `driving_supercombo.onnx`
  re-exported). Re-apply the fork's `modeld.py` and `modeld_v2` hunks. Check `modelV2` in model replay and modeld
  frame time and `frameDropPerc` on core 7.
- **CPU and RT changes:**
  - modeld goes to FIFO 54 on core 7 only after its models load (`c5543b1a0`), so rerun `test_cpu_layout`.
  - hardwared gets a 1 Hz chestnut USB-scan thread on HARDWARED_CORES 0-3 (`d38264c42`, `f2c772ff1`); gate it on
    `chestnut_compiled()`.
  - The Ratekeeper resync (C3).
  - No upstream change moves card off core 6 or touches core 4.

### First boot

- **AGNOS 19.7 → 19.9:** a blocking OS flash. Do it parked, with internet. Re-baseline the push16 kernel-log baselines.
- **Panda reflash.**
- **Custom model reset.** Re-select WMI V12, then let `modeld_warmup` finish offroad.
- **Set `InitialCruiseSpeedKph` to 105.**

### Diagnostics, tools and repo

- **Sentry removed.** Python crashes now go to `cloudlog.exception`.
- **`cumLagMs` semantics change** (C3).
- **Scripts that read `selfdriveState.experimentalMode` will misreport.** Examples in the 7997fd41 scratchpad:
  `bars1027/*`, `cfbars/rev_logic/rv_sd.py`, `brake320/rev_sim`, `batch2/integ/vcreplay.py`. `customReserved10`
  `notE2e` stays 0 from now on.
- **LFS moved to Hugging Face.** sunnypilot uses `huggingface.co/sunnypilot/sunnypilot-lfs`. Model pkls are now in LFS.
  Never set `INCLUDE_BIG_MODEL` in mirror builds.
- **`.gitattributes` `* text=auto eol=lf`** renormalises the Windows checkout. Check the WSL merge, `GIT_LFS_SKIP_PUSH`
  and the mirror CI against it. It also keeps in-repo DBCs LF, the cause of the relayed error.
- **Honda AEB block in panda safety** (`99953f99`) is compatible: the fork sends zeros in the checked bits. But
  `honda.h` conflicts with the `msg_matches` rewrite:
  - re-apply the stock-ACC refusal and the `pcm_gas` exception;
  - override the inherited `test_block_aeb` in `TestHondaElesysStockAccSafety`;
  - safety tests now run under UBSan with a 100 % line-coverage gate;
  - drop the `libsafety_py` cdef;
  - use `safety_tick()` in `mads_common`;
  - keep `ignore_frequency_check` (sunnypilot `e3f1487d`);
  - make the fork's TX arrays `static const`.
- **`test_runner` now collects `parameterized_class` tests,** so fork tests that were silently skipped may start
  running and failing.
- **Regenerate `settings_ui.json`** (`compile_settings_ui.py --check`) and `car_list.json`.
- **The Navigation (Alpha) toggle** appears because the fork is not a release branch. Leave it off: mapsd renders at
  20 Hz.
- **commaai is already at AGNOS 20.1** (2.1 GB system image, modem moved into the OS). A later sync will force it.
  Future commaai panda `f38f504f` adds an MPU, goes **silent** on permanent faults (no 0x0E4, so the board's silence
  path takes over) and renames FaultType ordinals, which breaks route tools that read faults by name.

---

## What upstream added since a5f44653d, by area

Hashes with no prefix are sunnypilot's tree (commaai commits included). **[cc]** marks a commit that is commaai-only
and not yet in sunnypilot.

### Longitudinal

| item | commits | car impact |
|---|---|---|
| Autospeed: e2e always in min(); chill accel, turn and coast limits removed; ExperimentalMode params removed; "Following Distance" | `f21bfc36b` `f50108b4a` `0d57eadd7` `42ccc5ceb` `41acce17f` `4429ec0c8` `cd3d5b005` `f5bcd10a2` `90932d9b5` `4f3626dc9` | **changes this car**, little in driving (C5) |
| DEC sunset; distance-button long-press toggle deleted | sp `5ec0c0219` (#2056), `2149006ec` | **changes this car**: the hold does nothing (C5) |
| `A_CRUISE_MIN` -1.2 → -0.5 | `263e8d196` (#39060) | **kept** at -1.2 after drops (recommended; C4) |
| No delay lowering the set speed | `2ab952d5e` (#39127) [cc] | **changes this car** if ported (C4) |
| Gas-override boost, `longitudinalPlan.accelBoost @40` | `ab8c84c39` (#39015) | owner decides (C6) |
| Configurable initial cruise speed | `24c26487f` `75b2ccca6` `fcf4b0d39` | **changes this car**: set 105 (C13) |

### Lateral and lane change

| item | commits | car impact |
|---|---|---|
| A road edge is no longer a blind spot; a nudge overrides an edge | sp `a06366ce9` (#2049) | **kept** (C7) |
| modeld seeds the previous curvature when lateral is inactive | `2b09bc94a` (#39091) | **changes this car** (C10) |
| Blendful lane-centre policy (alpha, modeld_v2) | sp `97135965e` `24f531b83` | available (C18) |
| Car mass, steerRatioRear and lateralParams removed; Honda torque lookup removed | `2713630e7`, opendbc `b3bd79a6` `25730a51` `cdf27c4b` | internal; blocks the merge until fixed |
| Curvature-controller low-speed saturation | `7ee974ab5` | n/a (torque car) |

### MADS, alerts and sounds

| item | commits | car impact |
|---|---|---|
| Duplicate no-entry alert fix | sp `27c132984` (#1949) | **changes this car** (C11) |
| Localizer alerts only once seen; bookmark-not-paired | `68d829c7c` `268991775` `521db4c82` `4d9d1bc34` | small |
| Louder warning wavs | `28917bb3a` (wavs taken, `AMBIENT_DB` not) | **changes this car** |
| Critical-alert ramp to max | `f00d226d3` | n/a (sunnypilot kept its own `soundd.py`) |
| `Offroad_UploadsIgnored` | `35e78a9d9` | internal (a `Params.remove` every 5 s offroad) |

### Driver monitoring

| item | commits | car impact |
|---|---|---|
| "Super Leicht" model and sleep distraction | `5ae0da0e4` | **changes this car** |
| AlwaysOnDMLock | `ef317505d` [cc] | n/a (fresh installs only) |

### Driving model and modeld

| item | commits | car impact |
|---|---|---|
| Stock runner rework (tinygrad ONNX compiler, chunking removed) | `50fb67f71` … `49bbba371` (19 commits) | internal; the main regression surface |
| modeld RT priority set after model load | `c5543b1a0` | **changes this car** (CPU layout) |
| Custom-model pipeline: plain GPU artifacts, parallel downloads, `modeld_warmup`, catalogue v25 | sp `4ff90ff8d` `e6864661c` `1aa3a430f` `9d029d683` (#2051, #2052) | **changes this car**: re-select WMI V12 |
| Big models, chestnut eGPU | `6f4c0faf1` `1e219d778` `9fba666fd`, `3f06ed3bc` and others | n/a |

### comma 4 (mici) UI

| item | commits | car impact |
|---|---|---|
| Lead bar; LongIndicator | `78dccf0b4`, `035a447d1` | **changes this car** (C15) |
| Bookmark fill, camera gates, wide camera on op long | `5b2a59d28` `46b97e619` | **changes this car** (now keyed on op long, not on experimental) |
| Touch, scroll and keyboard fixes | `690fa743b`; `ef4b6cc78` `9c6887c61` `06ed8252d` `d486c143a` `815a90f60` [cc] | small |
| Camera-client caching (tici only) | `14652aacb` [cc] | port (C19) |
| Settings, pairing, prime, eSIM and QR pages; descriptions | F15 group (22 commits) | merge noise in `software.py` and `toggles.py` |
| Torque arc width clamp | sp #2078 | visual |
| Navigation (Alpha), navd + mapsd | `4c362ca32` | available; leave off |

### GPS and maps

| item | commits | car impact |
|---|---|---|
| AssistNow time fix, position aid, minimum elevation 0° | `4c5355776` `1623441a9` `6eb63e045` | **changes this car** (C8) |
| mapd position write restored as bytes; SCC-Map on raw GPS | sp `2149006ec` `b6170ac5e`/`0dacd0eec` (net zero) `09b2f4bbe` | must take with the above |

### Panda and pandad

| item | commits | car impact |
|---|---|---|
| SPI turnaround revert | `910c08e08` (#39038) | **changes this car** (C1) |
| Simple SPI (request ids, CRC-32) | `50319fa70`, panda `835e4c31` | **changes this car**; lockstep |
| NMI/HardFault reset flags | `d2c0ce91a`, panda `20cd3584` | **changes this car** (C12) |
| UART removed; debug ring over SPI `0xb6` | panda `8b5d328f` `6089c53f`; pandad read `6f68efea6` [cc] | needs the pick (C12) |
| Fault-bit mask (bit 27) | `e37616881` [cc] | pick the mask (C12) |
| `safety_tick` matches opendbc | panda `43ab39f7` | lockstep |
| Siren on power loss while engaged; mic buffers; ST bootloader ACK timeout | panda `a5919516` `92eb5651` `c174561b` | small |
| pandad DisableDriverCameraIR offroad | `7bfe6ba4d` | small |
| commaai pandad rewrite (always reset, DFU recover) | `d3f0aab96` `cb1d6f11a` | **not taken**; keep the fork's |

### Process, CPU and logging

| item | commits | car impact |
|---|---|---|
| Ratekeeper resync | `fe7ccf958` (#39095) | **changes this car** (C3) |
| hardwared chestnut state thread | `d38264c42` `f2c772ff1` | **changes this car** (CPU; gate it) |
| Sentry removed; tombstoned gate | `6bbdf8ad1` (#38790) | **changes this car** (C2) |
| swaglog over a Unix datagram socket | `730c7c663` [cc] | wait (C16) |
| msgq ZMQ removal; bridge replaced by webrtcd | `d0198e020` `b1e88c235` `f2f9d5d42` [cc] | needs a sunnypilot msgq sync |
| encoderd waits for loggerd | `ff47f484e` [cc] | small |
| calibrationd reset on car change | `ef03ef80f` `371e4ef88` `8ba9f4bae` [cc] | n/a |

### Updater and AGNOS

| item | commits | car impact |
|---|---|---|
| AGNOS 19.8 / 19.9 | `cab53438a` `134517ceb` `f15544b48` `4dbdd66e0` | **changes this car** (OS flash) |
| Downgrade to pre-move releases | `64be6c80d` (#39063) | **changes this car** (C9) |
| AGNOS 20.1, modem in the OS | `34d4241e1` `079cd4729` `8d10a9deb` [cc] | the next sync |
| Prime SIM always metered | `9b585d58f` | n/a |

### opendbc (Honda and safety)

| item | commits | car impact |
|---|---|---|
| `enableBsm` → per-car flags (`HAS_BSM` = 1024) | `326d848a` (#3788) | **blocks the merge**: flag clash |
| Honda AEB actuation blocked in safety | `99953f99` (#3744) | compatible; test override needed |
| Safety refactors: `msg_matches`, 100 % coverage, UBSan, const tables, packed RX descriptors | `ba9fba2e` `fe0cfca0` `95195b31` `8e14e978` `a70751bf` `9186cbe5` `06ade56b` and others | internal; `honda.h` conflict |
| Safety-test harness: CFFI extracted, central setUp | `dd074c80` `836e54ce` `a6735052` `34d36133` | internal |
| `ignore_frequency_check` restored | sp opendbc `e3f1487d` | keep |
| New Honda/Acura platforms (ADX, Prelude 6G, Pilot MMR, CR-V Hybrid 2027) and fingerprints | `b24113c2` `a477f06c` `4c18a75a` `c8838cd2` and others | n/a |
| CANParser frequency fix and batched logs | `b8a277e7` `1bce882c` [cc] | wait (C14) |

### Tools, repo and CI

| item | commits | car impact |
|---|---|---|
| Cabana ported to ImGui, Qt removed | `06d76bdb2` `3a13b67b6` and about 66 more | PC (C17) |
| jotpluggler, replay retries, route parsing, `op.sh`, MetaDrive | F19 group | PC |
| LFS on Hugging Face; `eol=lf`; initData deprecations | F17 group, sp #2036 resolution | internal |
| scons cache and faster CI | sp #2055 #2046 #2062 #2063 #2066 #2074 | internal (a faster mirror gate) |

---

## The plan

### Options

| option | what ships when | merge cost | risk |
|---|---|---|---|
| A. full sync now | everything, this week | 3-4 days | It lands while push16/17 is still being judged: Ratekeeper, SPI and CPU changes would confound check16. Two OS flashes (19.9 now, 20.1 at the next sync). |
| **B. C1 now, full sync later** (recommended) | C1 (+ bit-27 mask) after push17's verdict; the sync mid-November | about 1 h now, 3-4 days later | lowest; one variable at a time |
| C. cherry-picks only | C1, C11, C3 with the card counter, maybe C6 | about 1 day | Every forced item (car mass, HAS_BSM, Autospeed, simple SPI) still waits, and the gap to upstream grows by about 2 weeks of commits each cycle. |

### Merge hot-spots

The merge-tree of 558016374 against 6f7a2c94c gives **15 content conflicts, 1 submodule conflict and 1 modify/delete**.
The **silent** rows below auto-merge and then break at runtime; they matter more than the conflicts.

| file | kind | resolution |
|---|---|---|
| `opendbc_repo` | submodule conflict | Do opendbc first (README Step 1) and pin the merged sp-master |
| opendbc `values.py` | **silent** | ELESYS → 8192; unique-flag test |
| opendbc `interface.py`, `test_elesys.py` | conflict / break | drop `mass=` and the lateralParams writes; STEER_MAX via CarControllerParams |
| opendbc `honda.h`, safety tests, `libsafety_py.py`, `mads_common.py` | conflict | re-apply the stock-ACC refusal and the `pcm_gas` exception; `test_block_aeb` override; `safety_tick()`; static const TX arrays |
| `cereal/custom.capnp` | conflict | `laneChangeNudgeRefused` @3 → @10 |
| `cereal/services.py` | conflict (adjacent) | keep both; take `modelDataV2SP` decimation 10 |
| `longitudinal_planner.py` | 2 hunks + **silent** L144/L181 | upstream signature; close-follow coast trip from `gasPressProbs`; the C4 port with the previous output captured before `update_targets`; this car's floor; boost after the lift |
| `plannerd.py` | 1 hunk | fork PubMaster + upstream SubMaster |
| `selfdrived.py` | 2 hunks + **silent** params thread | drop CruiseHelper and ExperimentalMode; keep #1949; distance-button hold |
| `desire_helper.py` | 2 hunks; TypeError if "ours" | C7 resolution |
| `modeld/modeld.py`, `modeld_v2/modeld.py` | conflicts | SubMaster union (`carStateSP` + `controlsState`); keep the `laneChangeNudgeRefused` line plus Blendful's 7 fields |
| `dec/dec.py` | modify/delete | accept the delete; drop the `real_lead` hunk |
| mici `toggles.py` (3), `software.py` (1) | conflicts | keep CloseFollow and radar dots; take Following Distance, InitialCruiseSpeedButton and `InfoLayoutMici` |
| mici `augmented_road_view.py`, `model_renderer.py` | conflicts | **merge both sides**: HUD rail, radar dots, `real_lead` in `_update_leads`; LongIndicator gate |
| sunnypilot mici `hud_renderer.py` | conflict | keep the fork's hooks (guarded by a test) |
| `ui/sunnypilot/ui_state.py` | conflict | union; de-dup `modelDataV2SP` |
| `hardwared.py` | conflict | fork LoopTimer, sensor workers, HARDWARED_CORES + upstream's chestnut thread, gated |
| `tombstoned.py` | **silent** | C2 resolution |
| `honda_stock_acc.py` | **silent** | remove the two keys from REMOVED_KEYS |
| `card.py`, `cruise.py` | auto | `initialize_v_cruise(CS, InitialCruiseSpeedKph)` with the fork's SLA grace; the never-reset `cumLagMs` counter |
| `pandad/spi.cc`, `panda_comms.h`, panda pointer | lockstep | take upstream whole with panda 8a16e089 |
| `pandad/panda.cc` | pick | `6f68efea6` (`0xb6`), with a capped drain |
| `pandad.py`, `soundd.py` | keep the fork's / sunnypilot's | not commaai's |
| fork tests | break | `test_distance_bars`, `test_close_follow`, `test_lead_brake_assist`, `test_reentry_ramp`, `test_bend_ease`, `test_elesys_radar_guard`, `test_honda_stock_acc`, `test_lane_change_nudge_refused`, `test_radar_dots`, plus newly collected `parameterized_class` tests |

### Effort estimate

| step | estimate |
|---|---|
| opendbc: flag move, car-mass removal, `honda.h` against `msg_matches`, safety-test harness, UBSan/coverage | 4-6 h |
| sunnypilot: 15 conflicts, the modify/delete, the 8 silent breaks, capnp | 8-12 h |
| fork follow-ups: C4 port and floor, C2 gate, C3 card counter, C12 picks, C15 `real_lead` and perf, C19 port, AccelBoost param, LongIndicator gate, distance-button hold | 6-8 h |
| tests, settings/car_list regeneration, closed-loop replays (10f/129, 12c/131/134, 143, 14d), model replay | 4-6 h |
| **total** | **about 3-4 working days**, then about a week of normal drives |

### Order of work

Follow the README merge procedure:
0. snapshot;
1. opendbc first;
2. sunnypilot;
3. tests for new upstream code;
4. regenerate;
5. grep the carry-set;
6. tests;
7. on the car;
8. land it.

Before landing, push the `pre-<date>` snapshot with an ExperimentalMode default of "1" (the C5 rollback trap), and
test that it installs (C9).

---

## What to verify on the car afterwards

These come in addition to README Step 7, which still applies in full.

**Parked, first boot (with internet):**
- AGNOS 19.9 flashed.
- The panda reflashed, with `signature` and `expected` matching and no version mismatch.
- `pandaStates.safetyParam` 164.
- Settings > gateway shows the hash and board id.
- Re-select WMI V12 and let `modeld_warmup` finish.
- Set `InitialCruiseSpeedKph` to 105.
- Check that ExperimentalMode is gone and selfdrived logged no exception.

**First drive:**
1. **plannerd runs.** `longitudinalPlan` at 20 Hz, no crash-loop; `customReserved10` close follow in a queue
   (`mode` 2, tightening; `notE2e` now always 0).
2. **Engage.** Below 40 km/h the set speed is 105, then SLA prompts "−" as today.
3. **Set-speed drops.**
   - On a 110→100 or an 80→60, the plan goes below -0.3 within about 0.3 s of the drop.
   - Braking back to the set speed after a gas lift-off is **not** harsher than before (compare 14c/10f-style
     overtakes).
   - There is no brake jab entering an SCC-V curve.
4. **AccelBoost.** `longitudinalPlan.accelBoost` stays 0 if left off.
5. **pandad.**
   - CAN 100.00 Hz; `spiErrorCount` about 0 with simple SPI.
   - No "timed out waiting for ACK" or "transfer failed".
   - `nmiReset` and `hardfaultReset` false.
   - Panda lines appear in `logMessage` (`0xb6`), and there is no "NO HANDLER" junk.
   - No "Harness Relay Malfunction".
   - Core 3 about 45-50 %.
6. **card.** The new never-reset `cumLagMs` slope is about 0 at 100 Hz, and check16 reads the card residual as
   before.
7. **Lateral and lane change.**
   - A nudge into a detected edge at 52 km/h or above is refused with the chime and tile (`laneChangeNudgeRefused` @10
     and event @32).
   - Below 52 nothing starts.
   - The first seconds after a gateway pause resume show no step in `0x0E4` (C10).
8. **Maps.** `liveMapDataSP` is present from the start, the NSW zone is matched, and the OSM limit is shown. Measure
   the time from start to the first `gpsLocationExternal` fix.
9. **UI.**
   - The HUD rail, radar dots, the confirm/armed/approach cards and the lane-block tile are all intact.
   - No lead bar on empty road (held leads).
   - The LongIndicator is hidden.
   - UI and core-5 load are not up.
   - No modeld "frames out of sync" after many wide switches.
10. **DM.** No false sleep alerts at night or with sunglasses. The warning sounds are louder; confirm they are
    acceptable.
11. **modeld.** `frameDropPerc` and frame time on core 7; FIFO 54 is set after load.
12. **Board update.** Run one gateway-board update through Settings > gateway on the new Python SPI layer, and check
    for the "eps-lkas flash trace".
13. **BLR telemetry** (`carStateSP.brakeLampRelay`) is present.

**Once per merge:**
- One stock-ACC drive (README Step 7.11), plus the FCW counts (the Autospeed MPC seeding).
- One install of the rollback snapshot, parked: an AGNOS downgrade, and it must boot with ExperimentalMode on.

---

## Corrections made during the review

The skeptic passes changed these claims from the shortlist or the first evaluations:

- **C1:** the returning SPI errors are NACKs before execution, not duplicated sendcan blocks; the fallback must shorten
  both waits; `spiErrorCount` alone is the wrong first-drive check.
- **C2:** a native crash already leaves its name and exit signal in `managerState`; the crash restart is not faster
  (crashed processes are not restarted); the one-line gate also revives up-to-100 MB CoreDump copies that upload
  before qlogs. A 5-line resolution is better. It is not a COMM-ISSUE item.
- **C3:** "unwrap on qlogs" hides starvation. The fix must be a never-reset counter in card.
- **C4:** the `2ab952d5e` gain is about 40 % (median 81 → 49 m), not about 85 %. -1.2 with `2ab952d5e` is harsher on
  gas-return braking (an untested combination). `reentry_ramp` does not cap the cruise path. A trailing-keyword port
  will still conflict at the next sync.
- **C5:** "take upstream" for the mici renderers would drop the HUD rail and radar dots. The UI is not unchanged
  (LongIndicator). The initial set speed is worse than "engage at my speed". There is a rollback trap. Stock-ACC FCW
  changes. A plannerd conflict was missing from the list.
- **C6:** the boost does change the plan for the rest of an engagement (43 % of foot-off time held). It needs an
  explicit yes. Bend ease is in shadow, so it caps nothing.
- **C7:** the corrected counts are 10 below 52 and 7 at or above. The floor first ran on route 157, not 15d. "Skip"
  still needs a merge resolution (TypeError). The proposed `blocked` variable had an ordering trap.
- **C8:** ubloxd's write is already non-blocking. Cold boots do not get the new aid.
- **C12:** the register-dump prints never run (`DEBUG_FAULTS` is off). `comms_healthy` is sticky, so CAN is gone after
  a mid-drive fault reboot. Brown-outs are not flagged.
- **C15:** the LongIndicator sits left, not top-right.
- **C18:** it is available to this owner (WMI V12 on modeld_v2). Old routes decode the refused bit as
  `blendfulGoingAround`.
- **C19:** the July coincidence at the 14th switch has not recurred since September.

## Not verified

- Whether the bit-27 phantom `relayMalfunction` has ever fired on this car.
- Whether `apport-retrace` symbolises stacks on the comma 4's AGNOS.
- Whether the msgq reader-slot leak still bites on current builds (C19).
- C9 and C10 were taken from the shortlist and the code, without route simulation.
- The downstream-fork reports about #2049.
- What sunnypilot's next commaai sync will contain, and when.
- The current device AGNOS version (presumed 19.7).
