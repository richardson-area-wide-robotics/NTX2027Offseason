"""The swerve troubleshooter: symptoms in a student's words, causes in order of likelihood.

Each symptom is a list of checks. Every check is a yes/no question where **yes means healthy**,
asked in the order a good mentor would ask them: cheapest and most likely first, nothing that
needs the robot moving until the motionless checks have passed. The first check that answers
"no" names the cause and the fix.

A check can carry automatic evidence the tool gathers itself:

* ``lint``    - config findings from :mod:`yagslcfg` (no robot needed)
* ``monitor`` - live telemetry rules from :mod:`monitor` (robot on, any mode)
* ``test``    - a test to run, judged by :mod:`advisor`

When evidence exists the tool pre-answers the question and shows why; the student confirms.
Where only eyes can tell - which way the top of a tire moves - the check says exactly what to
watch for.
"""

from __future__ import annotations

# Shorthand for the "where" of each check.
DISABLED = "DISABLED"   # robot on, disabled: safest, nothing can move
BLOCKS = "BLOCKS"       # wheels in the air
FIELD = "FIELD"         # on the floor, it moves


def check(q, how, where, if_no, fix, action=None, auto=None):
    c = {"q": q, "how": how, "where": where, "if_no": if_no, "fix": fix}
    if action:
        c["action"] = action
    if auto:
        c["auto"] = auto
    return c


SYMPTOMS = [
    {
        "id": "pod_wrong_direction",
        "title": "A wheel points the wrong way",
        "looks_like": "While driving, one or more wheels point a different direction from the "
                      "others, sideways, or backwards.",
        "checks": [
            check("Were the absolute encoder offsets captured on this robot?",
                  "Guide, Set the wheel offsets. Copied, duplicated or round-number offsets are the "
                  "most common cause of a misaimed wheel.",
                  DISABLED,
                  "The offsets do not describe these modules.",
                  "Capture offsets: robot disabled, every wheel set straight ahead with a "
                  "straight-edge, every bevel gear facing the robot's LEFT. The tool writes the "
                  "numbers.",
                  {"type": "guide", "step": "offsets"},
                  {"lint": ["offsets_duplicate", "offsets_round"]}),
            check("With every wheel set straight by hand, does each pod read close to 0° in the "
                  "Live view?",
                  "Disable the robot, square each wheel to the frame, look at the four pods.",
                  DISABLED,
                  "A pod reading far from 0° (often 90° or 180°) has a wrong offset.",
                  "Recapture offsets for that module. A pod near 180° with its drive motor "
                  "inverted is the same mistake in disguise - see 'One wheel drives backwards'.",
                  {"type": "guide", "step": "offsets"}),
            check("Turning a module counter-clockwise by hand (seen from above), does its angle "
                  "go UP?",
                  "Guide, Hand check: the tool records it with the motors in coast.",
                  DISABLED,
                  "The absolute encoder counts backwards for that module.",
                  "Flip absoluteEncoderInverted in that module's JSON. On MAXSwerve every module "
                  "should have the same value.",
                  {"type": "guide", "step": "hand"},
                  {"lint": ["abs_inversion_mixed"]}),
            check("In the hand check, did the steering motor's encoder move about the same number "
                  "of degrees as the absolute encoder?",
                  "The hand check reports 'motor degrees per module degree'; it should be 1.00.",
                  DISABLED,
                  "If it is near -1, the steering motor inversion is wrong. If it is a different "
                  "positive number, the steering gear ratio in the config is wrong.",
                  "MAXSwerve steering is 46.42:1 (angle gearRatio in physicalproperties.json). "
                  "Fix the ratio or the angle inversion, redeploy, repeat the hand check.",
                  {"type": "guide", "step": "hand"},
                  {"lint": ["angle_inversion_mixed"]}),
            check("Does steer_step on blocks move the RIGHT module, and does it reach each target?",
                  "Tune tab, Steering, pick FL only, run on blocks. Watch which physical module "
                  "turns.",
                  BLOCKS,
                  "Another module turned (CAN IDs swapped between module files), or it ran away "
                  "(motor and encoder disagree on direction), or it barely moved.",
                  "Swapped: swap the drive/angle IDs between the two module JSON files. Ran away: "
                  "revisit the inversion checks above. Barely moved: see 'A module won't steer'.",
                  {"type": "run", "test": "steer_step", "env": BLOCKS}),
            check("After a few minutes of driving, does the motor encoder still agree with the "
                  "absolute encoder within 2°?",
                  "Live view: each pod shows both. Or run a Health capture after driving.",
                  DISABLED,
                  "The steering motor encoder has drifted from the truth since boot (a gear skip, "
                  "a bad boot read).",
                  "Turn on encoder auto-sync, or steer on the absolute encoder. See 'Lines up at "
                  "boot, worse later'.",
                  {"type": "troubleshoot", "symptom": "pod_drifts"},
                  {"monitor": ["motor_vs_absolute"], "lint": ["steer_feedback"]}),
        ],
    },
    {
        "id": "wheel_backwards",
        "title": "One wheel drives backwards or fights the others",
        "looks_like": "One wheel spins the opposite way to the rest, the robot scrubs or "
                      "shudders, or it pulls to one side.",
        "checks": [
            check("Do all four modules have the same drive inversion in their JSON files?",
                  "Config tab. Identical modules should be identical here.",
                  DISABLED,
                  "One module's drive was inverted to hide an offset that is 180° out.",
                  "Recapture that module's offset with its bevel gear facing LEFT like the others, "
                  "then set its drive inversion to match the rest.",
                  {"type": "guide", "step": "offsets"},
                  {"lint": ["drive_inversion_mixed"]}),
            check("On blocks, with all wheels pointed forward and driving slowly forward, does the "
                  "TOP of every tire roll toward the front of the robot?",
                  "Tune tab, Drive, run drive_step on blocks and watch the tops of the tires. That "
                  "is the direction the robot would go.",
                  BLOCKS,
                  "That wheel would push the robot backwards.",
                  "Look at its pod in the Live view: if it shows about 180° while the others show "
                  "0°, its offset is 180° out (recapture it). If it shows 0° like the others, its "
                  "drive motor inversion is wrong: flip inverted.drive in that module's JSON.",
                  {"type": "run", "test": "drive_step", "env": BLOCKS}),
            check("Does the Live view show every wheel's measured speed with the same sign as its "
                  "setpoint?",
                  "Live view while driving slowly on blocks: speed arrows should point the same "
                  "way as the setpoint arrows.",
                  BLOCKS,
                  "The drive motor and its encoder disagree with the command.",
                  "Flip that module's drive inversion.",
                  None, {"monitor": ["drive_backwards"]}),
        ],
    },
    {
        "id": "robot_wrong_direction",
        "title": "The robot goes the wrong way",
        "looks_like": "Forward on the stick drives backwards, left goes right, or it turns the "
                      "opposite way to the stick.",
        "checks": [
            check("Have the wheel and offset checks passed ('A wheel points the wrong way', 'One "
                  "wheel drives backwards')?",
                  "Each module has to be right on its own before the chassis can be.",
                  BLOCKS,
                  "A module-level problem is showing up as a chassis-level one.",
                  "Work through those two first.",
                  {"type": "troubleshoot", "symptom": "wheel_backwards"}),
            check("Pushing the left stick FORWARD, does the robot drive away from you AND does the "
                  "Live view's pose x go UP?",
                  "On the floor, slowly, field-relative, robot facing away from the driver "
                  "station. Watch both the robot and the Pose readout.",
                  FIELD,
                  "Robot goes backwards with x going down: the code asks for -x - the stick is "
                  "not negated (an Xbox stick pushed forward reads -1). Robot goes forward but x "
                  "goes DOWN: every module is 180° out (or every drive motor inverted), so "
                  "odometry runs backwards even though teleop looks fine.",
                  "Stick: negate getLeftY() (and getLeftX(), getRightX()) where they enter the "
                  "drive command. All modules flipped: recapture all offsets with bevels LEFT and "
                  "make every drive inversion the same. Autos and heading control depend on this "
                  "being right.",
                  None),
            check("Pushing the right stick LEFT, does the robot turn counter-clockwise (seen from "
                  "above) AND does the heading go UP?",
                  "On the floor, slowly. Watch the heading in the Live view.",
                  FIELD,
                  "Turns the wrong way: the rotation stick needs negating. Turns right way but "
                  "heading goes down: the gyro is inverted.",
                  "Negate getRightX() in the drive command, or flip invertedIMU in "
                  "swervedrive.json. Run the spin test to confirm.",
                  {"type": "run", "test": "spin", "env": FIELD}),
        ],
    },
    {
        "id": "field_relative_wrong",
        "title": "Field-relative driving is off",
        "looks_like": "Forward is not away from the driver station, or it drifts further off as "
                      "the robot turns.",
        "checks": [
            check("Turning the robot counter-clockwise by hand, does the heading go UP?",
                  "Robot disabled, on the floor, push it round by hand, watch the heading.",
                  DISABLED,
                  "The gyro is inverted, so field-relative rotates the wrong way as the robot "
                  "turns.",
                  "Flip invertedIMU in swervedrive.json.",
                  None),
            check("Was the robot facing straight away from the driver station when the heading "
                  "was zeroed?",
                  "Field-relative uses the heading at boot (or at the reset button) as forward.",
                  DISABLED,
                  "Forward is wherever the robot faced when the heading was zeroed.",
                  "Face the robot away from the driver station and press the zero-gyro button "
                  "(Peashooter: Y).", None),
            check("Sitting still for a minute, does the heading stay within 0.5°?",
                  "Health capture, or watch the heading in the Live view.",
                  DISABLED,
                  "The gyro is drifting.",
                  "Keep the robot completely still for the first few seconds after power-on while "
                  "the navX calibrates; check it is mounted solidly.",
                  {"type": "run", "test": "capture", "env": "ANY", "args": {"duration_s": 30}}),
            check("Does the spin test show gyro, wheels and command agreeing?",
                  "Tune tab, Spin, on the floor.",
                  FIELD,
                  "Module locations in the config do not match the robot, or the gyro scale is "
                  "off.",
                  "Measure axle center to axle center and fix the module location values.",
                  {"type": "run", "test": "spin", "env": FIELD}),
        ],
    },
    {
        "id": "pod_oscillates",
        "title": "A module shakes, buzzes or oscillates",
        "looks_like": "A wheel wobbles back and forth around its angle, or a drive motor buzzes "
                      "or whines while holding speed.",
        "checks": [
            check("Is the steering ramp rate 0?",
                  "A ramp rate in a position loop adds lag, and lag plus kP is how oscillation "
                  "starts.",
                  DISABLED,
                  "The steering loop is slew-limited.",
                  "Set Steer RampS to 0 live, run steer_step, compare.",
                  {"type": "tune", "loop": "steer"},
                  {"lint": ["steer_ramp"]}),
            check("Does steer_step show under 10% overshoot and no ringing?",
                  "Tune tab, Steering, on blocks then on the floor.",
                  BLOCKS,
                  "Steering gains are too aggressive for this module.",
                  "Follow the tuner's advice: add kD (about kP x 5 on a SPARK), or lower kP.",
                  {"type": "run", "test": "steer_step", "env": BLOCKS},
                  {"monitor": ["steer_oscillation"]}),
            check("Is the drive kP gentle (under about 0.3) with kD at 0?",
                  "Config tab. Drive buzz is almost always too much drive kP or any drive kD.",
                  DISABLED,
                  "The measured speed is a little late and a little noisy; big gains turn every "
                  "flicker into a voltage kick.",
                  "Measure the feedforward, then tune drive kP down from there.",
                  {"type": "tune", "loop": "drive"},
                  {"lint": ["drive_p_hot"]}),
            check("With the robot disabled, does the module wiggle freely by less than a degree?",
                  "Grab the wheel and rock it. Free play here becomes oscillation under a stiff "
                  "loop.",
                  DISABLED,
                  "Backlash or something loose: set screw, pinion, bearing, module bolts.",
                  "Fix the mechanism; then retune, since the gains were fighting the slop.",
                  None),
            check("Is the absolute encoder quiet at rest (no read issues, under 0.3° noise)?",
                  "Health capture.",
                  DISABLED,
                  "A noisy or flickering sensor feeds noise straight into the loop.",
                  "Reseat the encoder cable and check the magnet.",
                  {"type": "run", "test": "capture", "env": "ANY", "args": {"duration_s": 3}},
                  {"monitor": ["absolute_read_issue"]}),
        ],
    },
    {
        "id": "pod_slow",
        "title": "Steering is slow to line up",
        "looks_like": "Wheels take a visible moment to point where the stick says, the robot "
                      "skids on direction changes, or one module lags the others.",
        "checks": [
            check("Is the steering ramp rate 0?", "Config tab.", DISABLED,
                  "Every steering correction is slew-limited.", "Set it to 0.",
                  {"type": "tune", "loop": "steer"}, {"lint": ["steer_ramp"]}),
            check("Does steer_step ON THE FLOOR meet the rise-time target?",
                  "Tune tab, Steering, floor (the robot does not drive; wheels turn in place).",
                  FIELD,
                  "Steering kP is soft for carpet, or the current limit is the ceiling.",
                  "Follow the tuner: it says whether kP or the current limit is the lever.",
                  {"type": "run", "test": "steer_step", "env": FIELD},
                  {"lint": ["steer_p_soft"]}),
            check("Does steer_step show both directions equally fast?",
                  "The tuner reports direction asymmetry.", BLOCKS,
                  "Gains are symmetric, so asymmetry is mechanical: rubbing, a tight bearing, a "
                  "wire dragging.",
                  "Turn the module by hand in coast, both ways, and compare with the others.",
                  {"type": "run", "test": "steer_step", "env": BLOCKS}),
        ],
        # Not a check: its yes would have to mean "a fault", so it is said up front instead.
        "note": "Only at a crawl? Below about 1% of top speed YAGSL deliberately holds each wheel's "
                "last angle so the wheels don't jitter around a stick at rest. That is intended, "
                "not a fault; if it bothers the drivers, the stick deadband is the place to look.",
    },
    {
        "id": "pod_not_moving",
        "title": "A module won't steer at all",
        "looks_like": "One wheel never changes direction, or drifts freely.",
        "checks": [
            check("Does the Driver Station or the Live view show no faults on that module?",
                  "Live view lists SPARK faults per module.",
                  DISABLED,
                  "A CAN, sensor or motor-type fault on that controller.",
                  "Check its CAN wiring and ID with the REV Hardware Client; a motor-type fault "
                  "means it is set to brushed or the wrong motor.",
                  None, {"monitor": ["faults"]}),
            check("Turning it by hand, does its angle change in the Live view?",
                  "Robot disabled.", DISABLED,
                  "The absolute encoder is not reporting.",
                  "Reseat the encoder cable at the SPARK's data port.",
                  {"type": "guide", "step": "hand"}, {"monitor": ["absolute_read_issue"]}),
            check("Is the steering motor's breaker or PDH channel fine, and does the motor make a "
                  "sound when steer_step runs?",
                  "Run steer_step on blocks with only that module.", BLOCKS,
                  "No power to the motor, or the motor is not turning the gears.",
                  "Check the breaker/fuse and the pinion set screw.",
                  {"type": "run", "test": "steer_step", "env": BLOCKS}),
        ],
    },
    {
        "id": "wont_drive_straight",
        "title": "Won't drive straight, or spins out",
        "looks_like": "On a straight command the robot curves, crabs or turns; or it starts "
                      "spinning and will not stop, especially in auto.",
        "checks": [
            check("Does it spin out only when something controls heading (auto, heading lock)?",
                  "If it is fine in plain teleop but spins in auto: positive feedback on heading.",
                  FIELD,
                  "Heading control is pushing the wrong way: an inverted gyro, or every module "
                  "180° out (teleop looks fine, but commanded rotation goes the other way while "
                  "the gyro measures the truth).",
                  "Run 'The robot goes the wrong way' to find which, then the spin test to "
                  "confirm.",
                  {"type": "troubleshoot", "symptom": "robot_wrong_direction"}),
            check("Are the offsets right (wheels straight read 0° within a degree)?",
                  "A degree of offset is about 1.7 cm of sideways drift per meter.", DISABLED,
                  "An offset is out.", "Recapture offsets.", {"type": "guide", "step": "offsets"}),
            check("Does steer_step on the floor show small-step error under 0.75°?",
                  "Carpet holds a soft steering loop a few degrees short.", FIELD,
                  "Wheels settle a little off their target angle.",
                  "Raise steering kP following the tuner.",
                  {"type": "run", "test": "steer_step", "env": FIELD}),
            check("Do all four modules hold the same speed in drive_step (spread under 5%)?",
                  "One weak corner pulls the robot round.", FIELD,
                  "A corner is weaker or slower.",
                  "Measure the per-module feedforward (drive_ff); a big difference is mechanical.",
                  {"type": "run", "test": "drive_step", "env": FIELD}),
            check("Does the straight-line test hold heading within 1° with no correction?",
                  "Tune tab, Straight; tape-measure where it stops if there are no AprilTags.",
                  FIELD,
                  "The drivetrain itself is not straight.",
                  "Work back up this list. Turn on heading correction only once the cause is "
                  "fixed - it hides problems rather than solving them.",
                  {"type": "run", "test": "straight", "env": FIELD}),
        ],
    },
    {
        "id": "skew_when_rotating",
        "title": "Drifts sideways when turning while driving",
        "looks_like": "Driving one way while spinning, the robot's path curves instead of going "
                      "straight.",
        "checks": [
            check("Is steering fast (steer_step rise under 120 ms)?",
                  "Slow steering lags the rotating wheel directions.", FIELD,
                  "Steering lag skews the path.", "Tune steering first.",
                  {"type": "run", "test": "steer_step", "env": FIELD}),
            check("Have you tried YAGSL's angular velocity compensation?",
                  "Live gains, Chassis/AngVelCoeff: drive straight while spinning, adjust in 0.02 "
                  "steps until the path straightens; expected range -0.15 to 0.15.",
                  FIELD,
                  "Some skew remains from the loop's delay even when everything is tuned.",
                  "Find the coefficient live, then Save.",
                  {"type": "tune", "loop": "chassis"}),
        ],
    },
    {
        "id": "robot_slow",
        "title": "The robot is slow",
        "looks_like": "Full stick does not reach the speed it should, or it feels sluggish.",
        "checks": [
            check("Is the max speed handed to YAGSL close to the module's real top speed?",
                  "Config tab.", DISABLED,
                  "The code's speed scaling does not match the hardware.",
                  "Fix the createSwerveDrive max speed.", None,
                  {"lint": ["max_speed_unreal", "max_speed_low"]}),
            check("Does the measured kV match the motor physics (within 15%)?",
                  "Run drive_ff on the floor; the report compares kV with the theoretical value.",
                  FIELD,
                  "The configured gear ratio or wheel size is not what is on the robot.",
                  "Count the pinion teeth (MAXSwerve: 12T = 5.50, 13T = 5.08, 14T = 4.71) and "
                  "measure the wheel.",
                  {"type": "run", "test": "drive_ff", "env": FIELD}),
            check("On blocks, does every module need about the same voltage to start turning?",
                  "drive_ff on blocks compares kS per module.", BLOCKS,
                  "One module is binding.",
                  "Spin it by hand against the others; fix the drag.",
                  {"type": "run", "test": "drive_ff", "env": BLOCKS}),
            check("Is the battery above 12.3 V at rest?", "Live view.", DISABLED,
                  "A tired battery.", "Swap it.", None),
        ],
    },
    {
        "id": "wheel_slip",
        "title": "Wheels spin when accelerating",
        "looks_like": "Wheels break loose on hard acceleration, and autos end short.",
        "checks": [
            check("Is the drive current limit at or below where the wheels really slip?",
                  "Guide: 'Find where the wheels slip' measures it with a bumper against a wall. "
                  "Until then the Config tab gives an estimate from the robot's weight.", FIELD,
                  "The motors can push harder than the carpet holds, so they spin the wheels.",
                  "Run the slip test and use the limit it recommends: 90% of the weakest corner.",
                  {"type": "run", "test": "slip", "env": FIELD},
                  {"lint": ["drive_current_over_traction"]}),
            check("Is the tread in good shape?", "Look at it.", DISABLED,
                  "Worn tread grips less and changes the wheel diameter.", "Replace it.", None),
        ],
    },
    {
        "id": "brownout",
        "title": "Stutters or browns out",
        "looks_like": "Motors cut out briefly, the robot stutters, or the Driver Station shows "
                      "brownouts.",
        "checks": [
            check("Is four times the drive current limit sensible for a 120 A main breaker?",
                  "Config tab.", DISABLED,
                  "Four drive motors at a high limit draw far more than the breaker sustains.",
                  "Lower the drive current limit.", None,
                  {"lint": ["drive_current_over_traction"]}),
            check("Is the battery healthy?", "Live view at rest: above 12.3 V.", DISABLED,
                  "A tired battery sags under load.", "Swap it.", None),
            check("Are there no CAN faults in the Live view?", "Faults per module.", DISABLED,
                  "CAN errors look like stutters.", "Check CAN wiring and termination.", None,
                  {"monitor": ["faults"]}),
        ],
    },
    {
        "id": "auto_inaccurate",
        "title": "Autos end in the wrong place",
        "looks_like": "Paths run but finish off target, or drift through the path.",
        "checks": [
            check("Does PathPlanner's robot config match YAGSL's?", "Config tab.", DISABLED,
                  "PathPlanner is planning for a different robot.",
                  "Fix the listed values in the PathPlanner app.", None,
                  {"lint": ["pathplanner_mismatch", "pathplanner_defaults"]}),
            check("Does odometry go the right way (robot forward = pose x up)?",
                  "'The robot goes the wrong way', second check.", FIELD,
                  "Odometry runs backwards, so every path is mirrored.",
                  "See 'The robot goes the wrong way'.",
                  {"type": "troubleshoot", "symptom": "robot_wrong_direction"}),
            check("Does the straight-line test agree with a tape measure within 1%?",
                  "Straight test, then enter the tape distance.", FIELD,
                  "The wheel diameter in the config is not the real one.",
                  "Apply the measured wheel scale.", {"type": "run", "test": "straight", "env": FIELD}),
            check("Is the drive feedforward measured?", "drive_ff on the floor.", FIELD,
                  "PathPlanner's velocity requests are reached late or not at all.",
                  "Measure and save the feedforward.", {"type": "run", "test": "drive_ff", "env": FIELD}),
            check("Is the drive current limit below the traction limit?", "Config tab.", DISABLED,
                  "Slipping wheels lose distance odometry never sees.",
                  "Lower the drive current limit.", None, {"lint": ["drive_current_over_traction"]}),
        ],
    },
    {
        "id": "twitchy",
        "title": "Driving is twitchy, hard to control slowly",
        "looks_like": "Small stick movements give big speed changes; hard to line up precisely.",
        "checks": [
            check("Is the max speed handed to YAGSL realistic?", "Config tab.", DISABLED,
                  "The stick is scaled to a speed the robot cannot reach, so it saturates early.",
                  "Fix createSwerveDrive's max speed.", None, {"lint": ["max_speed_unreal"]}),
            check("Are stick inputs shaped (deadband plus squaring or cubing)?",
                  "Look at the drive command: applyDeadband, and squaring keeps the sign.",
                  DISABLED,
                  "A linear stick gives coarse control at low speed.",
                  "Square the stick magnitude (keeping its sign) after the deadband; YAGSL's "
                  "SwerveInputStream can do this for you.", None),
            check("Is the drive kP gentle?", "Config tab.", DISABLED,
                  "An aggressive velocity loop makes every stick change a lurch.",
                  "Tune drive following the tuner.", {"type": "tune", "loop": "drive"},
                  {"lint": ["drive_p_hot"]}),
        ],
    },
    {
        "id": "pod_jitter",
        "title": "Modules twitch while the robot sits still",
        "looks_like": "Enabled with the sticks centered, wheels twitch or buzz.",
        "checks": [
            check("With sticks centered, do the setpoints in the Live view stay still?",
                  "Stick drift below the deadband should command nothing.", BLOCKS,
                  "The sticks are drifting through the deadband.",
                  "Raise the deadband (0.08-0.1) or replace the controller.", None),
            check("Is the absolute encoder quiet at rest?", "Health capture.", DISABLED,
                  "Sensor noise is driving the loop.", "Reseat cable, check magnet.",
                  {"type": "run", "test": "capture", "env": "ANY", "args": {"duration_s": 3}},
                  {"monitor": ["absolute_read_issue"]}),
            check("Is steering kD modest (not more than about kP x 10)?", "Config tab.", DISABLED,
                  "Too much kD amplifies encoder noise into motion.",
                  "Halve steering kD and rerun steer_step.", {"type": "tune", "loop": "steer"}),
        ],
    },
    {
        "id": "gear_ratio",
        "title": "A module seems geared differently",
        "looks_like": "One corner scrubs or fights the others, the robot crabs, a module's angle "
                      "drifts away on every move, or the tool says a ratio looks wrong.",
        "checks": [
            check("In the hand check, did every module's steering motor move 1.00 times as far "
                  "as the module (within 3%)?",
                  "Guide, Hand check, Record steering. The motor encoder is converted with the "
                  "configured steering ratio and the absolute encoder sits on the module itself, "
                  "so their ratio is the real ratio over the configured one.",
                  DISABLED,
                  "The steering ratio in physicalproperties.json is not the module's real ratio, or "
                  "one module has a different gearbox.",
                  "MAXSwerve steering is 46.42:1. If every module is off by the same factor, fix the "
                  "config; if one module is, inspect that module.",
                  {"type": "guide", "step": "hand"}),
            check("Driving straight on the floor, do all four modules report the same distance "
                  "(within 3%)?",
                  "Live view while driving straight for a few meters, or the module comparison in "
                  "a floor drive_ff or spin run. On blocks this cannot be seen: the motor encoder "
                  "cannot see the gearbox, only the floor couples the wheels.",
                  FIELD,
                  "A module reporting more or less distance than the others has a different "
                  "reduction. On MAXSwerve the ratio is 3 x spur / pinion: 12T pinion 5.50, 13T "
                  "5.08, 14T 4.71.",
                  "Count that module's pinion and spur teeth. Fix the part, or give every module "
                  "the same gearing; YAGSL uses one drive ratio for all four.",
                  {"type": "run", "test": "drive_ff", "env": FIELD},
                  {"monitor": ["drive_ratio_mismatch"]}),
            check("Does the straight-line test agree with a tape measure within 3%?",
                  "Straight line, then enter the tape distance in Runs.",
                  FIELD,
                  "Every module is geared differently from the config (more than 4% off matches a "
                  "pinion step), or the wheel size is wrong (1-3% is tread wear).",
                  "The report names the likely gearing. Count a pinion before changing the wheel "
                  "diameter.",
                  {"type": "run", "test": "straight", "env": FIELD}),
        ],
    },
    {
        "id": "motor_hot",
        "title": "A motor gets hot, goes weak or cuts out",
        "looks_like": "A wheel or mechanism loses power partway through a match or a practice, "
                      "the Driver Station shows a [motors] warning, or the Motors panel shows "
                      "WARN, DERATE or SHUTOFF.",
        "checks": [
            check("Is every motor's current limit within the team policy: NEO 550 20 A, NEO V1.1 "
                  "60 A, NEO 2.0 80 A, NEO Vortex 80 A?",
                  "Config tab, and the startup report at the top of the Motors panel: the robot "
                  "lowers any limit over the policy at boot and says which.",
                  DISABLED,
                  "A limit over the policy lets a motor make heat faster than it can shed it. In "
                  "REV's tests a NEO 550 at 40 A burnt out in about 27 s.",
                  "Set the limit in the code (or physicalproperties.json for swerve) to the policy. "
                  "Tell swervetune.json what each NEO really is: a NEO 1.1 and a NEO 2.0 look "
                  "identical to the robot.",
                  {"type": "config", "file": "modules/physicalproperties.json"},
                  {"lint": ["drive_current_over_policy", "steer_current_over_policy"]}),
            check("Robot disabled and in coast, does the mechanism turn freely by hand?",
                  "Binding, a rubbing belt, a bent shaft or a tight bearing makes a motor work all "
                  "the time. On swerve, the tool compares each motor with the same motor on the "
                  "other modules.",
                  DISABLED,
                  "Drag: the motor is working against friction, not the job.",
                  "Find and free the binding. A swerve motor much hotter than its three siblings "
                  "is the giveaway.",
                  None,
                  {"monitor": ["motor_hotter_than_siblings"]}),
            check("Is the motor free of jams and hard stops (stall time stays at 0 in the Motors "
                  "panel)?",
                  "Motors panel, Stall column, while the mechanism is used.",
                  BLOCKS,
                  "A motor pushing into a hard stop draws its full limit and does nothing; the "
                  "stall timer derates it and then cuts it.",
                  "Add a soft limit or a limit switch, hold with less current, or end the command "
                  "at the target instead of pushing on.",
                  None,
                  {"monitor": ["motor_hot"]}),
            check("Does it stay cool through a full, hard practice match?",
                  "Watch the heat estimate across a practice match. A NEO 550 has very little "
                  "metal to soak up heat; its windings heat in seconds and its sensor lags by tens "
                  "of seconds, which is why the guard trusts its heat estimate first.",
                  FIELD,
                  "The motor is too small or geared too fast for the job.",
                  "Gear it down, add a fan (a NEO 550 benefits most), share the load between two "
                  "motors, or move up a motor size. The thermal override is for the last seconds of "
                  "a match only: it never lifts a stall cut."),
        ],
    },
    {
        "id": "motor_dead",
        "title": "A motor does nothing, or runs weak or rough",
        "looks_like": "A motor that should run does not, buzzes, cogs, or is clearly weaker than "
                      "its twin; or the Motors panel shows a flag next to it.",
        "checks": [
            check("Is its controller free of faults?",
                  "Motors panel, Flags column; the SPARK's LED blinks orange or red on a fault.",
                  DISABLED,
                  "The fault names the problem: 'sensor' is the encoder or hall cable, 'gate "
                  "driver' is a shorted phase or a burnt motor.",
                  "Reseat the encoder cable and check the power leads. A gate driver fault that "
                  "comes back after clearing means replacing the motor or the controller.",
                  None,
                  {"monitor": ["motor_failing"]}),
            check("When it is told to run, does current flow?",
                  "Motors panel, Amps column. Output with no current and no motion is flagged "
                  "automatically after half a second.",
                  BLOCKS,
                  "Output without current: an unplugged power lead, a broken phase wire, or a "
                  "burnt winding.",
                  "Check all three motor phase leads and the power connector. A burnt motor often "
                  "turns lumpy by hand and smells of varnish.",
                  None,
                  {"monitor": ["motor_failing"]}),
            check("Unplugged, does the motor turn smoothly by hand, with no grinding or cogging?",
                  "Disconnect the phase leads first: a shorted winding makes a motor feel lumpy "
                  "even unpowered.",
                  DISABLED,
                  "Damaged bearings or windings.",
                  "Replace the motor."),
            check("For a drive motor: does drive_ff measure the same kV as on the other modules "
                  "and in its own earlier runs?",
                  "Run drive_ff on blocks; the report compares each module's kV and kS with the "
                  "others and with earlier saved runs.",
                  BLOCKS,
                  "kV falling over weeks means magnets weakened by heat; kS rising means growing "
                  "drag in the bearings or gearbox.",
                  "Replace the motor, or clean and re-shim the module, before it fails in a match.",
                  {"type": "run", "test": "drive_ff", "env": BLOCKS}),
        ],
    },
    {
        "id": "pod_drifts",
        "title": "Lines up at boot, gets worse during a match",
        "looks_like": "Wheels are straight after a restart but slowly stop lining up as the "
                      "robot drives.",
        "checks": [
            check("Does the steering motor encoder stay within 2° of the absolute encoder while "
                  "driving?",
                  "Live view: each pod shows both.", FIELD,
                  "The loop runs on the motor encoder, which has drifted from the truth.",
                  "Turn on encoderAutoSync in swervetune.json (resyncs whenever the modules are "
                  "still), or steer on the absolute encoder (factor 360 + steerFeedback "
                  "absolute). Try on blocks first.",
                  {"type": "config", "file": "swervetune.json",
                   "path": ["encoderAutoSync", "enabled"], "value": True},
                  {"monitor": ["motor_vs_absolute"], "lint": ["steer_feedback"]}),
            check("Is the steering pinion tight and the belt/gears intact?",
                  "A slipping pinion is exactly this symptom.", DISABLED,
                  "The motor turns without the module following.",
                  "Tighten or replace the set screw / pinion.", None),
        ],
    },
]

BY_ID = {s["id"]: s for s in SYMPTOMS}


def evaluate(symptom_id, lint_findings=(), monitor_flags=()):
    """Pre-answers the checks the tool can judge on its own.

    Returns the symptom with each check marked ``auto_answer``: ``"no"`` when evidence shows the
    problem, ``"yes"`` when every piece of evidence is clean, absent when only a person can tell.
    ``first_failing`` is the index of the first check the evidence says fails.
    """
    sym = BY_ID[symptom_id]
    lint_ids = {f["id"] for f in lint_findings}
    flags = {f["rule"] for f in monitor_flags}
    out = {k: v for k, v in sym.items() if k != "checks"}
    checks, first = [], None
    for i, c in enumerate(sym["checks"]):
        c = dict(c)
        auto = c.get("auto") or {}
        hits = [x for x in auto.get("lint", []) if x in lint_ids]
        hits += [x for x in auto.get("monitor", []) if x in flags]
        if auto:
            if hits:
                c["auto_answer"] = "no"
                c["evidence"] = hits
                if first is None:
                    first = i
            elif "lint" in auto and "monitor" not in auto:
                c["auto_answer"] = "yes"
        checks.append(c)
    out["checks"] = checks
    out["first_failing"] = first
    return out
