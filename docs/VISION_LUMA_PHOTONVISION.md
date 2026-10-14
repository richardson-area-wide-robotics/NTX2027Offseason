# Vision: a Luma P1 or P2 with PhotonVision

Neither robot has a camera fitted yet. This is how to add one so Sloth Tune, and the
robot's own pose estimate, can use it. The Luma P1 and P2 run PhotonVision, so everything below is
PhotonVision; the swerve library itself never talks to a camera library (see `VisionSource`):
only the small adapter in `common/slothtune-photonvision` does, which is what lets the library
carry on unchanged through 2027.

## 1. The camera

1. Give it a static IP on the robot network (team convention, e.g. `10.TE.AM.11`) and open its
   PhotonVision page on port 5800.
2. **Name the camera** on that page. The robot code must use exactly the same name: a mismatch
   fails silently, with no error and no poses.
3. **Calibrate it** (Cameras, Calibration) at the resolution the pipeline will use, with the
   team's ChArUco board: 9 x 11 in, 8 x 8 squares of 1 in, 0.75 in markers. In PhotonVision:
   board type ChArUco, tag family 4x4, pattern spacing 1.00 in, marker size 0.75 in, board 8 x 8,
   old OpenCV pattern off (check a square with a ruler; type what it measures). Take 12 or more
   snapshots, the board flat, near and far and tilted every way, covering the whole picture,
   never square-on. Keep going until the mean reprojection error is low (under about a pixel).
   Pose estimation is only as good as this, and the Luma image ships uncalibrated.

   **From the tool (easier):** Calibrate tab, **6. Camera lens**: type the camera's address and
   **Connect to the camera** (it shows PhotonVision's version against the robot code's PhotonLib:
   they must match). Check a square and a marker with calipers and type what they measure, pick
   the resolution, then **Calibrate, the tool leading**. After five checks (the board printed at
   100% and taped flat to something stiff, measured, the lens focused and left alone, even light,
   the robot disabled and still), the tool tells the person holding the board where to put it,
   pose by pose in large letters: each part of the picture, near and far, turned and tipped,
   never square-on. It counts down, takes the snapshot, and repeats a pose PhotonVision didn't see
   the whole board in. About 20 poses; 12 are the least PhotonVision accepts. **Work it out** has
   PhotonVision solve it (it uses its own solver, as its page does), then shows the mean error
   (under 1 px is good) and the field of view against the Luma P1's 80° × 56°, and records it for
   the checklist. Refocusing the lens makes the calibration wrong: calibrate again after.
4. AprilTag pipeline: family **36h11**, **3D mode** on, **Do Multi-Target Estimation** on, tag
   size 6.5 in across the black square (PhotonVision takes it in meters: type **0.1651**), and
   the field layout the event uses (2026 welded or AndyMark; they differ by up to 1.4 in).

## 2. Turn it on: a config change

Both robots already build with PhotonLib (`vendordeps/photonlib.json`, pinned to **v2026.3.4**,
the 2026 release; keep it the same version as the camera's PhotonVision, and don't take a 2027
alpha) and call `PhotonVisionSetup.install(tune)` in `Robot`. With no camera listed, that does
nothing. To fit one, list it in `src/main/deploy/swerve/slothtune.json` and redeploy:

```json
"vision": {"cameras": ["front"], "feedPoseEstimator": false}
```

The name must be exactly the one on the camera's PhotonVision page.

- **Before its mount is measured**, the camera gives tag sightings only: exactly what the Calibrate
  tab needs to measure where it sits (step 3).
- **Once `"cameras"` has its mount** (the Calibrate tab writes it), it gives robot poses: the Live
  tab shows them next to odometry, with accepted and rejected counts, and the straight-line test
  measures with them.
- **`"feedPoseEstimator": true`** sends the accepted poses into the drivetrain's own pose
  estimator, which every auto and field-relative drive uses. Turn it on only once the poses look
  right on the Live tab: a wrong mount pulls the robot's idea of where it is off by the same
  mistake. Each pose is trusted by distance and tag count (`VisionTrust`), and a single tag never
  moves the heading.

Every pose passes the same `VisionGate` the tools use. It rejects frames older than 0.5 s, single
tags beyond 157 in (about 13 ft) or with ambiguity over 0.2, multi-tag solves beyond 236 in
(about 20 ft), poses off the floor or off the field, and a single tag claiming a jump of more than
59 in (about 5 ft). Each rejection says why.

## At a new field: Calibrate, 9. New field

The lens doesn't change between fields; the light and the tags do. With the field's match lighting
on:

1. **Light**: the robot still, facing two or more tags 80 to 160 in (7 to 13 ft) away, **Tune the
   camera to this light**. The exposure is set short enough that a fast turn (360°/s) smears a tag by no more
   than about 6 pixels, worked out from the lens calibration, as PhotonVision advises: exposure as
   low as it can go, gain to make up the light. Then it tries the gain from 0 to 100, watching how
   often each frame sees the tags, keeps the lowest gain that sees them about as well as the best,
   and adds a step of margin. The settings stay on the camera; **Put the old settings back** undoes
   it. (The Luma P1 is black and white: there is no color or white balance to set.)
2. **Tags**: the robot on the floor, bumpers on, 40 in clear, someone holding the deadman: **Sweep
   here** spins it slowly in place, a full turn each way, while the field survey records every tag.
   Sweep at two or three spots, then **Work out where the tags are** (step 8 saves the layout).
3. **Mount**: from the same sweeps. Spinning in place, the robot's center stays put, so its vision
   pose should too; one that swings round in a circle means the camera's mount is off by about the
   circle's radius. Over 1.2 in, or a heading 1.5° off the gyro's, measure the mount again (step 3
   below).

## 3. Measure where the camera sits

Calibrate tab, **7. Camera positions**: tape one tag flat on a wall, put the robot square to it at
three or more measured spots, take a sighting at each, and **Work it out**. The spread between the
spots says how far to trust the answer. Save, redeploy.

To check the answer with a tape, measure to the middle of the lens. On a **Luma P1** (2.84 x 1.74 in,
four 5 mm holes 2.52 x 1.42 in apart) the lens is centered across the case, 0.16 in off the middle
of the holes toward the edge away from the name, and its front is 0.12 in out from the case, give
or take 0.06 in as it screws in and out to focus. Luma's drawing is in millimeters: 72.2 x 44.2
case, holes 64 x 36 apart, lens 4 off center and 3 out, give or take 1.5
([Luma's drawing](https://docs.luma.vision/p1/files/P1%20Assembly%20Public%20Drawing.pdf)).

## 4. At an event: survey the field

Calibrate tab, **Field tags**: drive slowly around the field with the camera seeing two or more
tags at once, then **Work it out**. Tags that really moved are put where they are; the rest keep
their official place. Save, redeploy. The Driver Station prints which tags were moved.

## Checking it works

- The top bar's AprilTags chip says "on" once a source is set and the environment has tags.
- The Live tab shows vision poses next to odometry, with accepted and rejected counts.
- The straight-line test uses vision as ground truth when AprilTags are on.

## The field survey and PhotonVision

Two things use a field's tag layout, and the survey has to reach both:

- **The robot** (the single-tag poses, and the gates): it loads the official layout named by
  `"vision": {"field": "welded"}` or `"andymark"` in `slothtune.json`, then moves each tag the survey
  measured. Saving the survey in the Calibrate tab writes both.
- **Each camera** (the multi-tag poses, solved on the camera itself): PhotonVision uses the layout
  loaded in its own web page, not the robot's. Upload `src/main/deploy/apriltags/surveyed.json` to every
  camera (PhotonVision, Settings, AprilTag field layout), or the multi-tag poses keep the official tag
  positions and the survey only corrects the single-tag ones.

At an event, set `"field"` to how that field is built (the event's documentation says welded or
AndyMark) and redeploy; a survey made on the other kind is set aside, with a warning.
