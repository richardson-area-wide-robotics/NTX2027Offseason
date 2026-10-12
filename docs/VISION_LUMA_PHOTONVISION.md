# Vision: a Luma P1 or P2 with PhotonVision

Neither robot has a camera fitted yet. This is how to add one so the swerve tools, and the
robot's own pose estimate, can use it. The Luma P1 and P2 run PhotonVision, so everything below is
PhotonVision; the swerve library itself never talks to a camera library (see `VisionSource`),
which is what lets it carry on unchanged through 2027.

## 1. The camera

1. Give it a static IP on the robot network (team convention, e.g. `10.TE.AM.11`) and open its
   PhotonVision page on port 5800.
2. **Name the camera** on that page. The robot code must use exactly the same name: a mismatch
   fails silently, with no error and no poses.
3. **Calibrate it** (Cameras, Calibration) at the resolution the pipeline will use, with a
   ChArUco board, until the reprojection error is low. Pose estimation is only as good as this.
   The Luma image ships uncalibrated.
4. AprilTag pipeline: family **36h11**, **3D mode** on, **Do Multi-Target Estimation** on, tag
   size **0.1651 m** (6.5 in across the black square), and the field layout the event uses
   (2026 welded or AndyMark; they differ by up to 3.6 cm).

## 2. PhotonLib in the robot project

1. WPILib's Vendor Dependencies panel: install **PhotonLib**.
2. **Pin it to the 2026 release your camera runs** (v2026.3.3 at the time of writing): edit the
   `version` in the project's `vendordeps/photonlib.json` to match the PhotonVision version on
   the camera. Keep the two the same, and don't take a 2027 alpha.
3. Add the adapter to the build, next to the existing line in `build.gradle`:

   ```gradle
   sourceSets {
       main { java { srcDir '../common/swervetune/java'; srcDir '../common/swervetune-photonvision/java' } }
       ...
   }
   ```

## 3. The robot code

After the `SwerveTune` is built:

```java
AprilTagFieldLayout field = FieldLayouts.load(
    AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField)).layout();
tune.setVisionSource(new PhotonVisionSource(
    "front", field, tune.cameraMount("front").orElse(ROUGH_ROBOT_TO_CAMERA)));
```

- `ROUGH_ROBOT_TO_CAMERA` is a tape-measured guess (meters from the robot's center at the floor;
  roll, pitch, yaw in radians; pitch negative when the camera looks up). It keeps the robot running
  until the mount is measured.
- `tune.cameraMount("front")` reads the measured mount from `swervetune.json`'s `"cameras"`.
- `FieldLayouts.load` puts in any tag positions a field survey measured.

The same `VisionGate` the tools use can guard the match pose estimate too, before
`swerveDrive.addVisionMeasurement(...)`. It rejects frames older than 0.5 s, single tags beyond
4 m or with ambiguity over 0.2, multi-tag solves beyond 6 m, poses off the floor or off the field,
and a single tag claiming a jump of more than 1.5 m. Each rejection says why, and the Live tab
shows the count and the last reason.

## 4. Measure where the camera sits

Calibrate tab, **Camera positions**: tape one tag flat on a wall, put the robot square to it at
three or more measured spots, take a sighting at each, and **Work it out**. The spread between the
spots says how far to trust the answer. Save, redeploy.

## 5. At an event: survey the field

Calibrate tab, **Field tags**: drive slowly around the field with the camera seeing two or more
tags at once, then **Work it out**. Tags that really moved are put where they are; the rest keep
their official place. Save, redeploy. The Driver Station prints which tags were moved.

## Checking it works

- The top bar's AprilTags chip says "on" once a source is set and the environment has tags.
- The Live tab shows vision poses next to odometry, with accepted and rejected counts.
- The straight-line test uses vision as ground truth when AprilTags are on.
