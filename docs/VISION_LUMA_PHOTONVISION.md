# Vision: a Luma P1 or P2 with PhotonVision

Neither robot has a camera fitted yet. This is how to add one so the swerve tools, and the
robot's own pose estimate, can use it. The Luma P1 and P2 run PhotonVision, so everything below is
PhotonVision; the swerve library itself never talks to a camera library (see `VisionSource`):
only the small adapter in `common/swervetune-photonvision` does, which is what lets the library
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
   Pose estimation is only as good as this, and the Luma image ships uncalibrated. The Calibrate
   tab's **6. Camera lens** draws the board and records the result.
4. AprilTag pipeline: family **36h11**, **3D mode** on, **Do Multi-Target Estimation** on, tag
   size **0.1651 m** (6.5 in across the black square), and the field layout the event uses
   (2026 welded or AndyMark; they differ by up to 3.6 cm).

## 2. Turn it on: a config change

Both robots already build with PhotonLib (`vendordeps/photonlib.json`, pinned to **v2026.3.3**,
the 2026 release; keep it the same version as the camera's PhotonVision, and don't take a 2027
alpha) and call `PhotonVisionSetup.install(tune)` in `Robot`. With no camera listed, that does
nothing. To fit one, list it in `src/main/deploy/swerve/swervetune.json` and redeploy:

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
tags beyond 4 m or with ambiguity over 0.2, multi-tag solves beyond 6 m, poses off the floor or off
the field, and a single tag claiming a jump of more than 1.5 m. Each rejection says why.

## 3. Measure where the camera sits

Calibrate tab, **7. Camera positions**: tape one tag flat on a wall, put the robot square to it at
three or more measured spots, take a sighting at each, and **Work it out**. The spread between the
spots says how far to trust the answer. Save, redeploy.

To check the answer with a tape, measure to the middle of the lens. On a **Luma P1** (72.2 x 44.2 mm,
four 5 mm holes 64 x 36 mm apart) the lens is centered across the case, 4 mm off the middle of the
holes toward the edge away from the name, and its front is 3 mm out from the case, give or take
1.5 mm as it screws in and out to focus ([Luma's drawing](https://docs.luma.vision/p1/files/P1%20Assembly%20Public%20Drawing.pdf)).

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
  `"vision": {"field": "welded"}` or `"andymark"` in `swervetune.json`, then moves each tag the survey
  measured. Saving the survey in the Calibrate tab writes both.
- **Each camera** (the multi-tag poses, solved on the camera itself): PhotonVision uses the layout
  loaded in its own web page, not the robot's. Upload `src/main/deploy/apriltags/surveyed.json` to every
  camera (PhotonVision, Settings, AprilTag field layout), or the multi-tag poses keep the official tag
  positions and the survey only corrects the single-tag ones.

At an event, set `"field"` to how that field is built (the event's documentation says welded or
AndyMark) and redeploy; a survey made on the other kind is set aside, with a warning.
