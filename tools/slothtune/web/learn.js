// Learn: every control-theory word in the tool explains itself. Hover (or focus) anything with a
// dotted underline for a short answer; click it, or "Lessons" in the header, for the full lesson.
// Written for high school students who have done the basic training. It follows WPILib's own
// teaching order - feedforward first, then feedback - and its words, so what a student learns
// here matches the docs they will read next.
"use strict";

const Learn = (() => {
  const W = "https://docs.wpilib.org/en/stable/docs/software/advanced-controls/";
  const LINK = {
    pid: [W + "introduction/introduction-to-pid.html", "WPILib: Introduction to PID"],
    ff: [W + "introduction/introduction-to-feedforward.html", "WPILib: Introduction to DC motor feedforward"],
    issues: [W + "introduction/common-control-issues.html", "WPILib: Common control loop tuning issues"],
    turret: [W + "introduction/tuning-turret.html", "WPILib: Tuning a turret position controller (interactive)"],
    flywheel: [W + "introduction/tuning-flywheel.html", "WPILib: Tuning a flywheel velocity controller (interactive)"],
    combine: [W + "controllers/combining-feedforward-feedback.html", "WPILib: Combining feedforward and feedback"],
    pidc: [W + "controllers/pidcontroller.html", "WPILib: PIDController"],
    trap: [W + "controllers/trapezoidal-profiles.html", "WPILib: Trapezoidal motion profiles"],
    profiled: [W + "controllers/profiled-pidcontroller.html", "WPILib: ProfiledPIDController"],
    mmpos: ["https://docs.revrobotics.com/revlib/spark/closed-loop/maxmotion-position-control", "REV: MAXMotion position control"],
    mmvel: ["https://docs.revrobotics.com/revlib/spark/closed-loop/maxmotion-velocity-control", "REV: MAXMotion velocity control"],
    revunits: ["https://docs.revrobotics.com/revlib/spark/closed-loop/units", "REV: closed-loop units"],
    revvel: ["https://docs.revrobotics.com/revlib/spark/closed-loop/velocity-control-mode", "REV: velocity control mode"],
    sysid: [W + "system-identification/introduction.html", "WPILib: Introduction to system identification"],
    statespace: [W + "state-space/state-space-intro.html", "WPILib: Introduction to state-space control (LQR)"],
    lqrwiki: ["https://en.wikipedia.org/wiki/Linear%E2%80%93quadratic_regulator", "Wikipedia: Linear-quadratic regulator"],
    olswiki: ["https://en.wikipedia.org/wiki/Ordinary_least_squares", "Wikipedia: Ordinary least squares"],
    simc: ["https://skoge.folk.ntnu.no/publications/2003/tuningPID/", "Skogestad: Simple analytic rules for PID tuning (SIMC)"],
    filterpsa: ["https://www.chiefdelphi.com/t/psa-rev-spark-default-velocity-filtering-is-still-really-bad-for-flywheels/514567",
      "Chief Delphi: REV SPARK default velocity filtering is still really bad for flywheels (2026)"],
    vcompstory: ["https://www.chiefdelphi.com/t/inconsistent-sparkmax-velocity-control/456497",
      "Chief Delphi: Inconsistent SPARK MAX velocity control (fixed by voltage compensation)"],
    canwiki: ["https://en.wikipedia.org/wiki/CAN_bus", "Wikipedia: CAN bus"],
    canaddr: ["https://docs.wpilib.org/en/stable/docs/software/can-devices/can-addressing.html", "WPILib: FRC CAN device specifications"],
    candevs: ["https://docs.wpilib.org/en/stable/docs/software/can-devices/index.html", "WPILib: CAN devices"],
    netbasics: ["https://docs.wpilib.org/en/stable/docs/networking/networking-introduction/networking-basics.html", "WPILib: Networking basics"],
    netip: ["https://docs.wpilib.org/en/stable/docs/networking/networking-introduction/ip-configurations.html", "WPILib: IP configurations"],
    ntintro: ["https://docs.wpilib.org/en/stable/docs/software/networktables/networktables-intro.html", "WPILib: What is NetworkTables"],
    nttopics: ["https://docs.wpilib.org/en/stable/docs/software/networktables/tables-and-topics.html", "WPILib: NetworkTables tables and topics"],
    ntpubsub: ["https://docs.wpilib.org/en/stable/docs/software/networktables/publish-and-subscribe.html", "WPILib: Publishing and subscribing to a topic"],
    ntnet: ["https://docs.wpilib.org/en/stable/docs/software/networktables/networktables-networking.html", "WPILib: NetworkTables networking"],
    ascope: ["https://docs.advantagescope.org/", "AdvantageScope documentation"],
    elastic: ["https://frc-elastic.gitbook.io/docs", "Elastic dashboard documentation"],
    frccan: ["https://frcelectrical.org/FRC-Control-System/#can-controller-area-network", "FRC Electrical: CAN"],
    frcterm: ["https://frcelectrical.org/FRC-Control-System/#terminating-resistors", "FRC Electrical: terminating resistors"],
    frcpower: ["https://frcelectrical.org/FRC-Control-System/#power-distribution", "FRC Electrical: power distribution"],
    frcradio: ["https://frcelectrical.org/FRC-Control-System/#robot-radio-20", "FRC Electrical: the robot radio"],
    frcconn: ["https://frcelectrical.org/Making-Connections/", "FRC Electrical: making connections (crimps, Wagos, Powerpoles)"],
    frcbatt: ["https://frcelectrical.org/Battery/", "FRC Electrical: the battery"],
    frcmanual: ["https://firstfrc.blob.core.windows.net/frc2026/Manual/2026GameManual.pdf", "2026 FRC game manual (robot rules R609, R621-R624)"],
    awgwiki: ["https://en.wikipedia.org/wiki/American_wire_gauge", "Wikipedia: American wire gauge"],
    wpiwiring: ["https://docs.wpilib.org/en/stable/docs/hardware/hardware-basics/wiring-best-practices.html", "WPILib: wiring best practices"],
    wpibatt: ["https://docs.wpilib.org/en/stable/docs/hardware/hardware-basics/robot-battery.html", "WPILib: the robot battery"],
    ctrecan: ["https://v6.docs.ctr-electronics.com/en/stable/docs/troubleshooting/canbus-troubleshooting.html", "CTRE: CAN bus troubleshooting"],
    molexcrimp: ["https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/2931/Quality%20Crimp%20Handbook.pdf", "Molex: Quality Crimp Handbook"],
    pptools: ["https://www.westmountainradio.com/pdf/PWRcrimpmanual.pdf", "West Mountain Radio: Powerpole crimping manual"],
    ppwiki: ["https://en.wikipedia.org/wiki/Anderson_Powerpole", "Wikipedia: Anderson Powerpole (red right, tongue top)"],
    sb50sheet: ["https://www.farnell.com/datasheets/3046067.pdf", "Anderson: SB50 data sheet (contacts and wire sizes)"],
    spectrum: ["https://docs.google.com/document/d/e/2PACX-1vQk_ghFBN7682QI_17lbBCx8V_RXNomQRR7er-UIzlllsbdpO4RWOQAVnGFZAEypeNm2grS2G9oxFMp/pub", "Spectrum 3847: FRC training curriculum"],
    spmotors: ["https://www.youtube.com/watch?v=vWKKIhUcTzw", "Spectrum 3847: Beginner Motors for FRC (video)"],
    spmotorslides: ["https://docs.google.com/presentation/d/1mY7ZgkHr2y7-nbhTbuT59DtMnN5ITxR3q-kx6YO6MyI/edit", "Spectrum 3847: Beginner Motors for FRC (slides)"],
    spencoders: ["https://www.youtube.com/watch?v=JDbronOFiq4", "Spectrum 3847: Encoders and SPARK MAX controls (video)"],
    spencslides: ["https://docs.google.com/presentation/d/10xCSBSIu5IWV512JZb0nliRcEJuR14BiA8ekJI2pXa4/edit", "Spectrum 3847: Encoders and SPARK MAX controls (slides)"],
    revneo: ["https://www.revrobotics.com/rev-21-1650/", "REV: NEO V1.1 (specs)"],
    revneo2: ["https://docs.revrobotics.com/brushless/neo/2.0", "REV: NEO 2.0"],
    revvortex: ["https://docs.revrobotics.com/brushless/neo/vortex", "REV: NEO Vortex"],
    revvortexspec: ["https://www.revrobotics.com/rev-21-1652/", "REV: NEO Vortex (specs, pole pairs)"],
    wikibrushed: ["https://en.wikipedia.org/wiki/Brushed_DC_electric_motor", "Wikipedia: brushed DC motor"],
    wikibldc: ["https://en.wikipedia.org/wiki/Brushless_DC_electric_motor", "Wikipedia: brushless DC motor"],
    wikioutrunner: ["https://en.wikipedia.org/wiki/Outrunner", "Wikipedia: outrunner"],
    wikisync: ["https://en.wikipedia.org/wiki/Synchronous_motor", "Wikipedia: synchronous motor (speed and pole pairs)"],
    cdneo42: ["https://www.chiefdelphi.com/t/neo-550-encoder-is-it-absolute/440419", "Chief Delphi: why a NEO counts 42 a turn"],
    wikihall: ["https://en.wikipedia.org/wiki/Hall_effect_sensor", "Wikipedia: Hall-effect sensor"],
    revmaglimit: ["https://docs.revrobotics.com/rev-crossover-products/sensors/magnetic-limit-switch", "REV: Magnetic Limit Switch"],
    wpienc: ["https://docs.wpilib.org/en/stable/docs/hardware/sensors/encoders-hardware.html", "WPILib: encoders (hardware)"],
    wpiencsw: ["https://docs.wpilib.org/en/stable/docs/software/hardware-apis/sensors/encoders-software.html", "WPILib: encoders (software)"],
    revtbe: ["https://docs.revrobotics.com/rev-crossover-products/sensors/tbe", "REV: Through Bore Encoder"],
    ctrecancoder: ["https://v5.docs.ctr-electronics.com/en/stable/ch12a_BringUpCANCoder.html", "CTRE: bringing up a CANcoder (magnet and offset)"],
    wikimems: ["https://en.wikipedia.org/wiki/Vibrating_structure_gyroscope", "Wikipedia: vibrating structure (MEMS) gyroscope"],
    wpigyro: ["https://docs.wpilib.org/en/stable/docs/hardware/sensors/gyros-hardware.html", "WPILib: gyroscopes"],
    reduxgyro: ["https://docs.reduxrobotics.com/canandgyro/", "Redux Robotics: Canandgyro"],
    wpiprox: ["https://docs.wpilib.org/en/stable/docs/hardware/sensors/proximity-switches.html", "WPILib: proximity switches (NO and NC)"],
    wpidio: ["https://docs.wpilib.org/en/latest/docs/hardware/sensors/digital-inputs-hardware.html", "WPILib: digital inputs (roboRIO and SystemCore)"],
    wikiphoto: ["https://en.wikipedia.org/wiki/Photoelectric_sensor", "Wikipedia: photoelectric (break-beam) sensors"],
    adabeam: ["https://learn.adafruit.com/ir-breakbeam-sensors", "Adafruit: IR break-beam sensors"],
    wikitof: ["https://en.wikipedia.org/wiki/Time-of-flight_camera", "Wikipedia: time of flight"],
    canrange: ["https://v6.docs.ctr-electronics.com/en/stable/docs/hardware-reference/canrange/index.html", "CTRE: CANrange"],
    revdist: ["https://docs.revrobotics.com/rev-crossover-products/sensors/2m-distance", "REV: 2m Distance Sensor"],
    revpdh: ["https://docs.revrobotics.com/ion-control/pdh/specs", "REV: PDH specs (current sensing)"],
    wikicurrent: ["https://en.wikipedia.org/wiki/Current_sensing", "Wikipedia: current sensing"],
    wpiapriltag: ["https://docs.wpilib.org/en/stable/docs/software/vision-processing/apriltag/apriltag-intro.html", "WPILib: what AprilTags are"],
    pv3d: ["https://docs.photonvision.org/en/latest/docs/apriltag-pipelines/3D-tracking.html", "PhotonVision: 3D tracking and ambiguity"],
    pvmultitag: ["https://docs.photonvision.org/en/latest/docs/apriltag-pipelines/multitag.html", "PhotonVision: MultiTag"],
    wikipull: ["https://en.wikipedia.org/wiki/Pull-up_resistor", "Wikipedia: pull-up resistor"],
    wpidebounce: ["https://docs.wpilib.org/en/stable/docs/software/advanced-controls/filters/debouncer.html", "WPILib: Debouncer"],
    wikibounce: ["https://en.wikipedia.org/wiki/Switch#Contact_bounce", "Wikipedia: contact bounce"],
    wikiaccel: ["https://en.wikipedia.org/wiki/Accelerometer", "Wikipedia: accelerometer"],
    wikidivider: ["https://en.wikipedia.org/wiki/Voltage_divider", "Wikipedia: voltage divider"],
    cefrc: ["https://file.tavsys.net/control/controls-engineering-in-frc.pdf", "Tyler Veness: Controls Engineering in FRC (free book, PDF)"],
    cefrcgh: ["https://github.com/calcmogul/controls-engineering-in-frc", "Controls Engineering in FRC on GitHub: the book's source and its Python examples"],
  };

  // The course, in teaching order. "units" in a lesson tie it to the numbers the tool shows.
  // The course, from the hardware up: what is on the robot and how it is wired, how it talks, driving
  // and testing it safely, calibrating it, then control - feedforward before feedback, as WPILib
  // teaches it - and tuning. Each lesson's Next follows this order within its unit.
  const UNITS = [
    { id: "motors", title: "1. Motors: how they work, and keeping them alive", lessons: ["motor_basics", "brushed_brushless", "inrunner_outrunner",
      "pole_pairs", "motor_inventory", "coast_mode", "current_limit", "heat_estimate", "stall", "derate", "thermal_override"] },
    { id: "sensors", title: "2. Sensors: how they work", lessons: ["pull_resistor", "limit_switch", "contact_bounce", "break_beam", "time_of_flight",
      "hall_effect", "encoder_quadrature", "encoder_magnetic", "motor_encoder", "absolute_encoder", "offset", "inversion", "gear_ratio",
      "encoder_sync", "quantization", "velocity_filter", "gyro_mems", "accelerometer", "gyro", "current_sensing"] },
    { id: "wiring", title: "3. Power, wiring and CAN", lessons: ["battery", "power_path", "wire_gauge", "wire_loss", "battery_current",
      "crimp_sb50", "crimp_powerpole", "can_bus", "crimp_molex_sl", "can_frame", "can_arbitration", "frc_can_id", "can_heartbeat",
      "can_load", "can_fd", "can_termination", "wiggle_test"] },
    { id: "network", title: "4. The robot's network and NetworkTables", lessons: ["robot_network", "networktables", "nt_topics", "nt_timing", "dashboards"] },
    { id: "controllers", title: "5. The drive team's joysticks", lessons: ["deadband", "stick_drift", "button_bounce"] },
    { id: "safety", title: "6. Running tests safely", lessons: ["robot_mode", "environment", "deadman", "simulator", "what_if"] },
    { id: "swerve", title: "7. Swerve drive", lessons: ["swerve_module", "carpet_scrub", "module_flip", "odometry", "field_relative"] },
    { id: "calibrate", title: "8. Calibrating: what each step does and why", lessons: ["hand_check", "bevel_gear", "straight_edge", "hold_still",
      "redeploy", "wheel_size", "slip_current", "moment_of_inertia", "pathplanner_model"] },
    { id: "vision", title: "9. Cameras and the field", lessons: ["apriltag_detect", "vision_pose", "camera_mount", "field_survey"] },
    { id: "basics", title: "10. What a control loop is", lessons: ["control_loop", "setpoint", "measurement", "error", "control_effort"] },
    { id: "ff", title: "11. Feedforward: answer before the question", lessons: ["feedforward", "kS", "kV", "kA", "kG", "r_squared"] },
    { id: "fb", title: "12. Feedback: fix what feedforward missed", lessons: ["feedback", "kP", "kD", "kI", "integral_windup", "iZone", "rev_units"] },
    { id: "read", title: "13. Reading a step response", lessons: ["step_response", "dead_time", "rise_time", "overshoot", "settling_time", "steady_state_error", "oscillation"] },
    { id: "limits", title: "14. When the motor can't do what it's told", lessons: ["saturation", "traction", "voltage_sag", "ramp_rate"] },
    { id: "model", title: "15. Measure, then compute: model-based tuning", lessons: ["model_tuning", "system_id", "hold_band", "least_squares",
      "lqr", "simc", "spark_modes", "maxmotion_limits", "voltage_compensation", "check_runs", "sim_vs_real"] },
    { id: "profile", title: "16. Second order: motion profiles (after first-order tuning works)", locked: true,
      lessons: ["motion_profile", "trapezoid_profile", "cruise_velocity", "max_acceleration", "ff_uses_setpoint", "maxmotion_position", "maxmotion_velocity", "allowed_profile_error", "profiled_pid"] },
  ];

  const L = {
    control_loop: { title: "A control loop", short: "Measure, compare with what you want, push to close the gap, repeat - a thousand times a second on a SPARK.",
      body: [
        "Every motor here is controlled the same way. You say what you want (the <b>setpoint</b>). A sensor says what is happening (the <b>measurement</b>). The difference is the <b>error</b>. The controller turns the error, plus what it already knows about the motor, into a voltage (the <b>control effort</b>).",
        "Then it measures again and does it all again. On a SPARK MAX the steering loop runs 1000 times a second inside the motor controller, which is why it can be quick and precise.",
        "Two halves do the work. <b>Feedforward</b> uses physics to guess the voltage before any error shows up. <b>Feedback</b> (PID) fixes whatever error is left. WPILib teaches feedforward first, and so does this tool."],
      links: ["pid", "ff", "cefrc"] },
    setpoint: { title: "Setpoint", short: "What you want: the angle a wheel should point, or the speed it should spin. WPILib also calls it the reference, r(t).",
      body: ["The target. On the graphs it is the dashed line. In a step test the tool jumps the setpoint suddenly, because a sudden jump shows everything about how a loop behaves in one picture."], links: ["pid"] },
    measurement: { title: "Measurement", short: "What the sensor says is really happening right now - WPILib's process variable, y(t). The controller only knows what its sensor tells it.",
      body: ["The solid line on the graphs. Every sensor is a little late and a little coarse (see quantization and the speed filter). The controller cannot react to anything faster than its sensor can see."], links: ["pid"] },
    error: { title: "Error", short: "Setpoint minus measurement: how far off it is, and which way. Everything feedback does starts here.",
      body: ["Error = setpoint - measurement. Positive means 'not there yet' in the positive direction.",
        "On the 'What the controller did' graph, every feedback term is built from the error: P from its size, D from how fast it changes, I from how long it has lasted."], links: ["pid"] },
    control_effort: { title: "Control effort", short: "What the controller sends to the motor - here, volts. More volts, more push. It can never be more than the battery has.",
      body: ["The output, u(t). A SPARK thinks in duty cycle (a fraction of the battery voltage); this tool shows volts so the parts add up and you can compare with the battery line.",
        "When the controller asks for more than the battery has, the motor is <b>saturated</b>: see that lesson."], links: ["pid", "issues"] },

    feedforward: { title: "Feedforward", short: "The voltage physics says you need, sent right away, before any error appears. Done well, it does most of the work.",
      body: [
        "A motor needs a predictable voltage to do a job: a little to get going (kS), more the faster it spins (kV), more again to speed up (kA). WPILib writes it as <code>V = kS·sgn(v) + kV·v + kA·a</code>.",
        "Feedforward uses the <b>setpoint</b>, not the measurement. It does not wait for something to go wrong; it answers before the question. That is why a drive wheel with a measured feedforward is within a few percent of its target before PID does anything.",
        "The drive_ff test measures kS, kV and kA for each module. Steering uses feedback only in YAGSL."],
      see: "On the drive graphs, the gray FF line carries most of the voltage while holding a speed.", links: ["ff", "combine", "flywheel", "cefrc"] },
    kS: { title: "kS - static friction", short: "Volts it takes just to get the mechanism moving. Below kS nothing happens.",
      body: ["Bearings, gears and carpet grip all resist the start of motion. kS is the voltage that just overcomes them, in volts. It points the way you want to go and does not depend on speed.",
        "A module needing much more kS than the others is binding: a rubbing wheel, debris, or a misaligned pinion."], links: ["ff"] },
    kV: { title: "kV - volts per speed", short: "Extra volts for each m/s of speed (the code's units), mostly the motor's back-EMF. kV x speed is what it takes to hold a speed.",
      body: ["A spinning motor is also a generator, pushing back against the battery (back-EMF). To hold a speed you must out-push it, and the push-back grows in a straight line with speed. kV is that slope, in volts per m/s: the code's units, so the number here is the number in the file.",
        "The speed in kV is the speed the code reports, worked out from the motor's own turns with the gear ratio and wheel size in the files. So kV follows those configured numbers: fix a wrong ratio in the files and the measured kV changes with it, while the real gearing never shows. With the files fixed, what moves kV is the motor itself (a different motor fitted, or magnets weakened by heat) or, on carpet, a wheel whose real size has changed."], links: ["ff"] },
    kA: { title: "kA - volts per acceleration", short: "Extra volts to speed up, for each m/s² of acceleration (the code's units). It reflects how heavy the robot is.",
      body: ["Speeding up a robot takes force, and force takes current, and current takes voltage. kA is in volts per m/s² (the code's units). On blocks it is tiny (just a wheel); on the floor it carries a quarter of the robot.",
        "YAGSL's module loop does not use kA today, but measuring it tells you how hard the robot can accelerate."], links: ["ff"] },
    kG: { title: "kG - gravity (kCos for an arm)", short: "Volts to hold the mechanism up against gravity. An elevator's is the same everywhere; an arm's is kG x cos(angle): most when level, none straight up.",
      body: ["Gravity pulls the same way all the time, so the volts to hold against it are added whatever else the loop does. For an elevator that is one number: kG. For an arm it depends on the angle: level, all of the weight hangs on the motor; straight up, none does.",
        "REV calls the arm's version <b>kCos</b>: the SPARK multiplies it by the cosine of the arm's angle, so the encoder must read 0 when the arm is level (and kCosRatio must turn its readings into turns of the arm). Use kG or kCos, never both: the tool sets the other one to 0.",
        "Before it applies kCos, the tool checks REV's angle (the SPARK's position x kCosRatio) against the angle the measuring run saw. More than 5 degrees apart and it leaves kCos alone and says what kCosRatio and zero it needs: kCos at the wrong angle pushes the arm the wrong amount everywhere.",
        "kG sits in the middle of the hold band: a little more and it rises, a little less and it sags."],
      links: ["ff", "cefrc"] },

    feedback: { title: "Feedback (PID)", short: "Measures the error and pushes to shrink it. It fixes what feedforward got wrong - bumps, friction, wear.",
      body: ["Feedback looks at the error and responds. Its three classic terms are P, I and D. WPILib's one-line summary: P drives the position error to zero, D drives the velocity error to zero, and I drives the accumulated error to zero.",
        "Feedback alone works, but it only pushes once something is already wrong. With good feedforward, feedback can stay gentle - which means less noise, less buzzing, less heat."], links: ["pid", "combine", "cefrc"] },
    kP: { title: "kP - the spring", short: "Push = kP x error. Like a spring: the further from the target, the harder it pulls. More kP is faster, until it overshoots or buzzes.",
      body: [
        "P is proportional: twice the error, twice the push. WPILib calls it a software spring - Hooke's law.",
        "Too little: slow, and on carpet the wheel stops a few degrees short because the small push near the target cannot beat friction. Too much: overshoot, ringing, and an angry buzz from a coarse sensor.",
        "In REV units kP is duty cycle per unit of error: steering kP 0.01 means 1% of the battery per degree, so 10° of error gives 0.1 x 12 V = 1.2 V."],
      see: "On 'What the controller did', the P line is big just after a step and fades as the error closes.", try: "Practice pod, Steering, floor: try kP 0.005, 0.01 and 0.03 and compare rise time and what is left over.",
      links: ["pid", "turret"] },
    kD: { title: "kD - the damper", short: "Push = kD x how fast the error changes. Like a shock absorber: it brakes the motion as the target gets close, so it does not overshoot.",
      body: [
        "D reacts to the error's rate of change. As the mechanism rushes toward the target the error shrinks quickly, and D pushes back - a damper.",
        "It lets you use more kP without overshoot. Too much D amplifies sensor noise into buzzing, because noise changes quickly.",
        "REV's kD acts on the change in error over one 1 ms controller step, not per second, so a REV kD is 1000 times WPILib's per-second number for the same damping. Change it by factors of two and watch the result."],
      see: "On 'What the controller did', the D line points opposite the P line as the target nears: that is braking.", links: ["pid", "pidc"] },
    kI: { title: "kI - the grudge", short: "Push = kI x error added up over time. It keeps growing while any error remains. Powerful, risky, and usually not needed.",
      body: [
        "I adds up the error over time, so a small error that never goes away eventually gets a big push. That can close the last degree on carpet.",
        "WPILib's advice: integral gain is generally not recommended for FRC, and steady error usually means the feedforward is wrong. If you use it, keep it tiny and use an IZone.",
        "The danger is <b>integral windup</b>: during a big move the sum grows huge and makes it overshoot."], links: ["pid", "issues"] },
    integral_windup: { title: "Integral windup", short: "During a big move the I term piles up error it doesn't need, then overshoots while it 'unwinds'.",
      body: ["After a big setpoint change the error is large for a while, and I keeps adding it up - more than any useful output. When the target is reached, all that stored push carries it past.",
        "WPILib's fixes: reduce kI (ideally to zero), limit the integrator, or use an IZone so I only acts close to the target."], links: ["issues"] },
    iZone: { title: "IZone", short: "I only works when the error is smaller than this. Far from the target, the integrator is cleared, so it can't wind up.",
      body: ["A guard for kI. With an IZone of 3°, the integrator only adds up error within 3° of the target; anything bigger resets it to zero. That keeps I for the last little bit, where friction stops P."], links: ["issues", "pidc"] },
    rev_units: { title: "REV's units", short: "A SPARK's output is a fraction of the battery; its kD and kI act per 1 ms step. That's why REV gains look different from WPILib's.",
      body: ["kP: duty cycle per unit of error (degrees for steering, m/s for drive: the code's units). Multiply by battery volts to get volts.",
        "kD: duty per unit of error change over one 1 ms step - so a REV kD equals 1000 times WPILib's per-second kD. kI: duty per unit of error, added once per 1 ms step - 1/1000 of WPILib's per-second kI.",
        "The tool converts everything to volts on its graphs so the terms can be compared."], links: ["pidc"] },

    step_response: { title: "A step response", short: "Jump the setpoint and watch: delay, speed, overshoot, settling and what's left over tell you almost everything about a loop.",
      body: ["Each number has a usual cause:",
        "<b>Dead time</b> - communication and friction, not gains. <b>Rise time</b> - mostly kP and how hard the motor can push. <b>Overshoot</b> - too much kP for the damping. <b>Settling</b> - overshoot plus ringing. <b>Left over</b> - friction beating a small P, or a wrong feedforward.",
        "Hover the shaded areas on the graph: each is one of these, measured on your robot."], links: ["turret"] },
    dead_time: { title: "Dead time", short: "The gap between the command and the first movement. Gains can't remove it, and it limits how aggressive any gain can be.",
      body: ["The setpoint has to reach the controller, current has to build in the windings, and friction has to let go. Until then nothing moves.",
        "A loop with more delay must be gentler, or it reacts to old news and oscillates. That is why the tool measures it first."], links: ["issues"] },
    rise_time: { title: "Rise time", short: "Time from 10% to 90% of the way to the target. Quicker = more kP, or the motor is giving all it has.",
      body: ["Measured between 10% and 90% so the delay and the slow finish don't hide the speed of the move. If the motor is saturated during the rise, more kP won't make it faster - only more voltage, current or less load can."] },
    overshoot: { title: "Overshoot", short: "How far it goes past the target, as a percent of the step. Steering overshoot sends the robot sideways for a moment.",
      body: ["The spring (kP) stored too much energy for the damper (kD) to absorb. Add kD, lower kP, or, on drive, measure the feedforward so P can be gentler."] },
    settling_time: { title: "Settling time", short: "How long until it stays inside the band (shaded) around the target. Ringing and slow finishes both make it long.",
      body: ["The band is 2% of the step, or a fixed small amount for tiny steps. 'Never settles' means it either keeps swinging or stops outside the band."] },
    steady_state_error: { title: "Steady-state error", short: "What's left when it stops moving. On carpet: a small P near the target can't beat the wheel's grip.",
      body: ["Near the target P is small, because the error is small. If friction needs more than P provides, the motion stops short and stays there.",
        "Fixes, in order: a little more kP; on drive, measure the feedforward; last, a tiny kI with an IZone. Each degree of steering error is about 2 in of drift per 10 ft."], links: ["issues"] },
    oscillation: { title: "Oscillation", short: "Swinging back and forth past the target. Too much spring for the damping and the delay.",
      body: ["Each correction is so strong, or so late, that it overshoots the other way. Lower kP, add kD, or reduce delay (a faster sensor filter on drive). A fast buzz rather than a slow swing is usually sensor coarseness times a high gain."] },

    saturation: { title: "Saturation", short: "Asking for more than the motor can give. While flat out, the gains don't matter - the loop behaves as if they were smaller.",
      body: ["The battery has about 12 V, and the current limit caps the current. When P+D+FF asks for more, the motor gives all it can and no more.",
        "WPILib: a saturated mechanism behaves as if the control gains were smaller. So raising kP during a saturated stretch changes nothing. To be faster there, change the hardware - gearing, current limit, a bigger motor - or ask for less."],
      see: "Red shading on 'What the controller did': the asked line is above the battery line.", links: ["issues"] },
    current_limit: { title: "Current limit", short: "The most current the SPARK lets the motor draw. It protects the motor and the wheels' grip, and caps acceleration.",
      body: ["Current makes torque, torque makes acceleration - and heat. The smart current limit holds current to a set value by turning the voltage down. The team policy: NEO 550 20 A, NEO V1.1 60 A, NEO 2.0 and Vortex 80 A.",
        "On a drive motor, a limit above what the carpet can hold just spins the wheel."] },
    traction: { title: "Traction", short: "The most push the carpet can pass from a wheel to the robot: grip times the weight on that wheel. Past it, the wheel spins.",
      body: ["A wheel pushes the robot through friction with the carpet. The most it can pass on is the grip (the coefficient of friction) times the weight pressing that wheel down. Push harder and the wheel breaks loose and spins.",
        "A spinning wheel pushes less, not more - sliding friction is lower than gripping friction. It also wears the tread, and the encoder counts distance the robot never traveled, so odometry drifts.",
        "Each corner carries a different share of the weight, so each slips at a different push. The lightest corner slips first."] },
    voltage_sag: { title: "Voltage sag", short: "The battery voltage drops while current flows. The SPARKs make up for it until there aren't enough volts left; then the robot is slower than asked.",
      body: ["A tired battery or a robot drawing hard (all four drive motors accelerating) can sag below 10 V. Below about 6.8 V the roboRIO browns out and cuts the motors.",
        "YAGSL turns on the SPARKs' voltage compensation at 12 V: a duty of 0.5 means 6 V on a full battery or a tired one, so the same gains do the same thing. That holds until the battery sags below what is asked - full stick needs about 10 V at these motors - and then nothing can push harder. Tests refuse to start on a low battery because every number would change."],
      links: ["issues", "combine", "frcbatt"] },
    deadband: { title: "Deadband", short: "Stick readings this close to center count as zero, so a stick that doesn't quite center can't drive the robot by itself.",
      body: ["Every stick rests a little off center, and worn ones more. The robot code ignores anything inside the deadband: Peashooter ignores 0.1, Black team 0.08.",
        "Too small and a drifting stick creeps the robot; too big and the stick has a wide dead spot, so the driver must push further before anything happens. Both robots use WPILib's applyDeadband, which rescales what is outside the deadband, so the speed starts from zero at its edge instead of jumping (a hand-written \"if under 0.1, make it 0\" would jump). The joystick check measures each controller and recommends the smallest safe deadband.",
        "Both robots apply it to the driving stick's distance from center: a round deadband. Applied to each axis on its own it makes a cross-shaped dead zone instead, and a gentle diagonal push can leave one axis at zero, so the robot snaps to straight lines near center. The turning stick has one axis, so it is deadbanded on its own."] },
    stick_drift: { title: "Stick drift", short: "A stick that reads a little pushed when nobody touches it. Wear and dirt make it worse over a season.",
      body: ["Check every joystick at the start of an event and after it's dropped. If a stick rests outside the deadband, the robot creeps on its own - in a precise line-up, that's a miss.",
        "A stick can rest fine and still come back off center after a hard flick, which is why the check flicks each stick and watches where the spring leaves it.",
        "Xbox joysticks have no gyro, and the Driver Station doesn't read the gyro in a PlayStation joystick, so the drift that matters to the robot is the sticks'."] },
    button_bounce: { title: "Button bounce", short: "A worn button can make and break contact more than once in one press: the robot sees a double-tap.",
      body: ["A toggle - intake on, intake off - flips twice and ends where it started. The check counts each press and flags any two that come closer together than 30 ms, faster than a person can press.",
        "The laptop sees the joystick every few milliseconds, so the shortest bounces can slip between readings; a joystick that bounces at all is worth replacing. What bounce is, and how code debounces it: see contact bounce."] },
    battery: { title: "The battery", short: "A \"12 V\" battery reads about 12.7 to 13 V charged and at rest, and less under load. How far it drops per amp - its sag, in milliohms - tells a healthy battery from a tired one.",
      body: ["The team's batteries are MK ES17-12s (REV sells them): 12 V nominal, 18 Ah when drained slowly over 20 hours but only about 6 Ah at 54 A, and about 12 mΩ inside when new (its datasheet). A match pulls 100 to 200 A in bursts.",
        "The voltage drops by resistance times current: 20 mΩ at 150 A is 3 V gone, so 12.7 V at rest becomes 9.7 V. The robot measures the battery together with everything between it and the PDH - the Anderson connector, the leads, the main breaker - so a healthy battery reads a few milliohms more here than on a battery tester.",
        "So each battery gets a number written on it, and after every swap the drive team picks that number: the Battery chip here, or the Battery drop-down on the Driver Station dashboard. Every test and match log then measures that battery, and over a season the tired ones show: good up to 20 mΩ, practice up to 28, retire above. A loose Anderson connector or breaker bolt looks exactly like a tired battery, so check those first.",
        "Charge: at rest (an hour off the charger, motors off) about 12.7 V or more is charged, 12.3 to 12.7 partly, under 12.3 charge it."], links: ["frcbatt"] },
    ramp_rate: { title: "Ramp rate", short: "Limits how quickly the output can change. In YAGSL it also slows every correction the closed loop makes.",
      body: ["A ramp of 0.25 s means 0 to full output takes a quarter second. For drive it can smooth starts; for steering it adds pure lag to every correction, which hurts. Usually 0 for steering."] },

    quantization: { title: "Quantization", short: "A sensor counts in steps. A NEO's built-in sensor has 42 counts per turn, so speeds and small moves look jumpy.",
      body: ["The steering motor's hall sensor gives 42 counts per motor turn; through a 46.42:1 gearbox that is about 0.18° of module angle per count. Fine for position. For speed it is coarse, so the SPARK averages - which adds delay (see the speed filter).",
        "A high kP times a jumpy measurement makes a buzz."] },
    velocity_filter: { title: "Speed filter", short: "The SPARK works out speed from encoder counts over a window of time and averages several windows. Smoother means later: about half the time it averages over.",
      body: ["Speed is counts per time, so the SPARK counts over a window (REVLib's <b>measurement period</b>, in ms) and averages several windows (its <b>average depth</b>). An average is late by about half the time it spans, and a loop that reads a late speed must push gently, or it reacts to old news.",
        "The two kinds work differently (REV doesn't document it; a 2026 Chief Delphi PSA measured it). A <b>quadrature</b> encoder - the Vortex's own, on a SPARK Flex - takes a fresh window every millisecond and averages depth of them, overlapping: about (period + depth) / 2 ms late. The device default, 100 ms and depth 64, is 82 ms late. A NEO's <b>hall sensors</b> on a SPARK MAX take windows end to end: about period x depth / 2. The default, 32 ms and depth 8, is 128 ms late.",
        "A flywheel loop then reacts to a speed from a tenth of a second ago, so it can only use a much weaker kP. The PSA's advice: about a 10 ms window (10 ms, depth 2 on a Flex: 6 ms late). A NEO counts only 42 times a turn, so one count in a 16 ms window is about 90 RPM: its reading jumps in 90 RPM steps, and a shorter window jumps more. The tool suggests 16 ms, depth 1 (8 ms late).",
        "A position loop on the SPARK never reads this speed, so the filter matters for flywheels and rollers, not arms and elevators. REVLib's own docs give different defaults, so the tool never trusts one: the measuring run reads each SPARK's settings and times its speed reading against its position (SysId calls this the measurement delay)."],
      links: ["filterpsa", "revvel"] },
    hall_effect: { title: "The Hall effect", short: "A magnet pushes the moving charges in a chip sideways, making a small voltage. Motors use it to find their rotor; switches use it to see a magnet.",
      figure: { src: "img/sensor/hall-effect.svg", alt: "Current through a thin plate; a magnet comes near and pushes the moving charges to one side, and a meter across the plate reads a voltage", caption: "The closer the magnet, the bigger the sideways voltage." },
      body: ["Send a current through a thin plate and bring a magnet near: its field pushes the moving charges toward one edge, and a small voltage appears across the plate, growing with the field. That is the Hall effect.",
        "A Hall sensor either reports that voltage (how strong the field is) or switches on and off with it (a magnet is near, or not). Some switches answer one pole, some either pole, some latch until the other pole comes by.",
        "A NEO has three, set 120 electrical degrees apart, so its controller knows where the rotor is and when to switch the coils. They are also its built-in encoder: 42 counts a turn, counted from wherever it was at power-on.",
        "REV's Magnetic Limit Switch is one too: it sees either pole of its magnet about 0.4 in (10 mm) from its top, 0.2 in (5 mm) from its side. And a magnetic absolute encoder is a grid of them reading a spinning magnet."],
      links: ["wikihall", "revmaglimit"] },
    encoder_quadrature: { title: "How an encoder counts (quadrature)", short: "Two sensors read a striped disk a quarter stripe apart. Which one changes first says the direction; counting every change says how far.",
      figure: { src: "img/sensor/encoder-quadrature.svg", alt: "A striped disk turning past two sensors, A and B, a quarter cycle apart, and their two square waves; which leads says the direction", caption: "A leads B one way, B leads A the other." },
      body: ["An encoder counts turns, and parts of turns, of a shaft. The simplest is a striped disk and a light sensor that reads 1 on a dark stripe and 0 on a light one (a NEO uses magnets instead of light). Each change is an <b>edge</b>: 0 to 1 is rising, 1 to 0 falling.",
        "More stripes means finer steps, like more pixels on a screen: 12 stripes is 12 ticks a turn.",
        "One sensor can't tell direction: forward and backward show the same pattern. Two sensors, a quarter stripe apart, can: together they step through four states (quad is four), in one order going forward and the other going back.",
        "Counting every edge of both (4X) is finest: REV's Through Bore makes 2048 cycles a turn, 8192 counts. WPILib warns that counting every edge makes a speed reading jumpier.",
        "Speed is distance over time: time a set number of ticks, or count the ticks in a set time. A SPARK counts over a window and averages - see the speed filter. And an encoder like this only counts from where it started: it doesn't know where it is at power-on."],
      links: ["spencoders", "spencslides", "wpienc", "wpiencsw"], credit: "Adapted in part from Spectrum 3847's training curriculum: Encoders and SPARK MAX Controls (C2.4)." },
    encoder_magnetic: { title: "How a magnetic absolute encoder works", short: "A magnet magnetized across its face spins over a chip of Hall sensors that reads which way its field points: the angle, even right after power-on.",
      figure: { src: "img/sensor/encoder-magnetic.svg", alt: "A disc magnet, north on one half and south on the other, spinning over a sensor chip; the angle readout follows it, and a pulse's width grows with the angle", caption: "The chip reads the field's direction; the pulse width carries the angle." },
      body: ["A small disc magnet, magnetized across its diameter (north on one half, south on the other), sits on the end of the shaft, just above a chip with a grid of Hall sensors. As the shaft turns, the field over the chip turns with it, and the chip works out the angle from which way it points.",
        "It reads the angle itself, not a count of changes, so it knows where it is the moment it powers on: an <b>absolute</b> encoder. REV's Through Bore (V2 uses an MA600 chip, 12-bit), CTRE's CANcoder (12-bit, 4096 counts a turn) and Thrifty's encoders all work this way.",
        "Many send the angle as a <b>duty cycle</b>: a pulse every period, high for a share of it that says the angle (the Through Bore V1: about 976 Hz, 10-bit; V2: 1 kHz, 12-bit). WPILib's DutyCycleEncoder knows the angle at boot, and can tell when it is unplugged: the pulses stop. Into a SPARK's data port it is the absolute encoder input.",
        "The magnet must be centered and close. A CANcoder's light shows it: green when the field is right, red when the magnet is too far or too strong.",
        "Its zero is wherever the magnet happened to sit when it was mounted, so the code needs an <b>offset</b>. Set it so the jump from 360 back to 0 falls outside the mechanism's travel."],
      links: ["revtbe", "ctrecancoder", "wpienc"] },
    motor_encoder: { title: "Motor encoder", short: "The sensor inside the steering motor. Quick and fine, but it only knows how far it turned since power-on.",
      body: ["YAGSL's steering loop uses it by default and sets it from the absolute encoder at boot. If the gear ratio is wrong or a pinion slips, it drifts from the truth; encoder auto-sync re-aligns it when the module is still."] },
    absolute_encoder: { title: "Absolute encoder", short: "The sensor on the module itself: knows the real angle at power-on, every time. Slower and coarser than the motor encoder.",
      body: ["On MAXSwerve it is the through-bore encoder on the steering axle. It is what offsets are measured against, and the truth the motor encoder is checked against."] },
    offset: { title: "Offset", short: "The absolute encoder reading when the wheel points straight ahead. One degree wrong is about 2 in of drift per 10 ft.",
      body: ["Each encoder is mounted at a random angle, so the code needs to know where 'straight' is for each module. Capture them with every wheel squared to a straight-edge, all bevel gears facing the same way. Copied or rounded offsets are the most common swerve fault."] },
    inversion: { title: "Inversion", short: "Whether positive means forward (or counter-clockwise) for a motor or sensor. One wrong sign and a module runs away or fights the others.",
      body: ["Every motor and encoder has a direction. The hand check turns things by hand, with nothing powered, and checks each sign agrees with the code."] },
    gear_ratio: { title: "Gear ratio", short: "Motor turns per wheel (or module) turn. If the code's number is wrong, every distance and speed is wrong by the same factor.",
      body: ["MAXSwerve drive is 3 x spur / pinion: 12T 5.50:1, 13T 5.08:1, 14T 4.71:1. A module built with a different pinion reports a different distance from its neighbors while driving straight - the tool watches for that."] },
    encoder_sync: { title: "Encoder auto-sync", short: "Re-aligns the steering motor's encoder to the absolute encoder whenever the module is still.",
      body: ["Fixes slow drift of the motor encoder during a match. The deadband stops it from fighting tiny disagreements."] },

    hand_check: { title: "The hand check", short: "Turn things by hand with nothing powered, and check every sensor counts the way the code expects.",
      body: ["Every later test assumes it knows which way is positive. Turning a wheel or a module by hand, with the robot disabled, tests each direction safely - nothing can run away.",
        "It also compares the steering motor's encoder with the absolute encoder: they should agree 1.00 to 1. A different number means the gear ratio in the code is not the module's real one."] },
    coast_mode: { title: "Coast mode", short: "Motors spin freely instead of braking, so you can turn wheels by hand. Used only while disabled, and always put back.",
      body: ["In brake mode the controller shorts the motor's windings, which makes it resist being turned. For a hand check or an offset capture you need to turn things freely, so the tool sets coast for the capture and restores brake after - even if the capture is stopped early. Coast is never left on while enabled."] },
    bevel_gear: { title: "Bevel gear direction", short: "A MAXSwerve wheel looks straight two ways, 180° apart. Which way the bevel gear faces decides which is 'forward'.",
      body: ["Straight ahead and straight backwards look identical from above. The difference is the bevel gear's side. Capture every module with its bevel gear facing the robot's LEFT.",
        "If one module is captured the other way, its offset is 180° off: it drives backwards whenever the others drive forwards - the 'one wheel drives backwards' symptom in disguise."] },
    straight_edge: { title: "Why a straight-edge", short: "Eyes are good to 2-3°, which is 4-6 in of drift per 10 ft. A straight-edge across a pair of wheels gets well under a degree.",
      body: ["One degree of offset error is about 2 in of sideways drift for every 10 ft the robot drives. A level or a piece of extrusion held against both wheels of the front pair, then the back pair, lines them up far better than eyes can.",
        "Square the edge to the frame first: measure from the frame rail to the edge at both ends and make the two the same. An edge that is skewed lines the two wheels up with each other, but not with the robot, and both get the same wrong offset."] },
    hold_still: { title: "Why hold still", short: "The capture averages a few seconds of readings and checks they agree. A wheel that moved gives a blurred average, so it asks again.",
      body: ["Averaging removes the encoder's last-bit flicker. Checking the spread catches a bumped wheel. Both make the offset the real position, not a moment's guess."] },
    redeploy: { title: "Why redeploy", short: "Offsets and gains live in JSON files the robot reads once, at startup. Changing the files does nothing until the code is deployed and restarted.",
      body: ["The tool writes the robot project's files on the laptop. Deploying copies them to the robot; the robot reads them when its code starts. That is also why 'Apply live' changes vanish at the next restart: only the files are permanent - and the commit makes them the team's."] },

    slip_current: { title: "Slip current", short: "The drive current at which a wheel breaks loose. The drive current limit belongs just below it - measured on your carpet, not guessed.",
      body: ["Motor current makes torque, torque makes the wheel push. So 'the push where the wheel slips' is a current, and the drive current limit can be set right under it.",
        "The test: a bumper flat against a wall so the robot cannot move, then a slowly rising push. While the wheels grip, they stay still and the current climbs. The moment a wheel slips, its encoder speed jumps. The highest current before that is its breakaway current, and that wheel is cut at once to spare the tread.",
        "The limit is set to 90% of the weakest corner: carpets differ between venues and tread wears. It never goes above the team's policy for the motor. A datasheet estimate for our Vortexes on a 121 lb robot is about 69 A, under the 80 A policy: current above the slip point only spins the wheels."] },

    swerve_module: { title: "Swerve module", short: "Two loops per corner: steering (an angle) and drive (a speed). Eight loops for the robot.",
      body: ["The steering loop is a position loop, like WPILib's turret tutorial. The drive loop is a velocity loop, like its flywheel tutorial. Tune steering first: a drive loop can't be judged while the wheel points the wrong way."], links: ["turret", "flywheel"] },
    carpet_scrub: { title: "Carpet scrub", short: "On carpet a standing wheel grips while it turns, so steering needs far more push near the target than on blocks.",
      body: ["Turning a wheel in place twists its tread against the carpet. That friction is much larger than in the air, so gains tuned on blocks usually stop a few degrees short on the floor. Always finish steering on the floor."] },
    module_flip: { title: "Module optimization", short: "A wheel never turns more than 90°; past that it turns the short way and drives backwards instead.",
      body: ["Pointing 170° the other way is the same as pointing 10° and driving in reverse. YAGSL does this automatically, so steering never needs to move far."] },
    environment: { title: "Where the robot is", short: "On blocks: the wheels spin and the robot stays put. On the floor: it really drives. Simulator: the computer. The tool's safety rules change with it.",
      body: ["On blocks the gyro and cameras must NOT see motion, and no wheel may work like it carries weight - if either happens, the robot is not on blocks and the test stops. On the field a space budget is enforced and an impact stops everything. Both need a deadman held: \"on blocks\" is only what someone told the tool."] },
    deadman: { title: "Deadman", short: "Hold it and the robot may move; let go and it stops. Held by someone watching the robot: the tester's joystick bumper is best.",
      body: ["Every test that moves a motor needs it held, on blocks and on the floor: the tester's joystick right bumper (Driver Station port 1), or the Hold to run button on screen, pressed with the mouse or a finger.",
        "No keyboard key does it: in the Driver Station the space bar is E-STOP, even when its window isn't in front, so a key on that laptop would stop the robot instead of running it.",
        "Prefer the bumper: the person holding it can stand where they see every wheel. Hold to run is for when the laptop sits beside the robot and whoever holds it can see the wheels too; the tool runs only on this laptop, not on a phone."] },
    r_squared: { title: "R² (how well a fit fits)", short: "How well a straight line through the measured points fits them: 1.00 is perfect; under 0.95 something else pushed on the wheel.",
      body: ["The feedforward test fits volts = kS + kV × speed + kA × acceleration to every sample. R² says how much of what was measured that line explains.",
        "A slipping wheel, a bump in the carpet, a cable catching or someone touching the robot all add volts the line can't explain, and R² drops. Re-run it on clear carpet."], links: ["ff"] },
    robot_mode: { title: "Robot modes", short: "Disabled: nothing can move. Enabled: motors follow the code. E-stopped: off until the robot restarts. Only the Driver Station changes the mode.",
      body: ["The Driver Station decides the mode, never this tool. Disabled is the safe state: the robot controller (roboRIO or SystemCore) sends no motor commands, which is why the hand check and the offsets are done disabled. Enabled lets the code drive the motors, which every tuning test needs.",
        "E-stop is final: the robot stays off until it is rebooted. In the Driver Station, Enter disables and the space bar e-stops. This tool's ABORT button and Esc stop a test without e-stopping the robot."] },
    odometry: { title: "Odometry", short: "Where the robot thinks it is, worked out from how far each wheel rolled and which way the gyro says it faces.",
      body: ["Every 20 ms the code adds up each module's wheel turns (times the wheel size) and angle, plus the gyro's heading, and moves its estimate of the robot's position. WPILib's directions: x is forward, y is left, and counter-clockwise turns are positive.",
        "Errors add up. A wheel 2% smaller than the code thinks makes every distance 2% short, and a slipping wheel counts ground it never covered. AprilTags can correct the estimate whenever a camera sees one."] },
    field_relative: { title: "Field-relative driving", short: "Push the stick away from you and the robot goes away from you, whichever way it faces.",
      body: ["The code turns the stick's direction, as the driver sees it, into the robot's own directions using the gyro heading. That only works if the heading is right: a gyro that counts backwards, or a heading zeroed while the robot faced sideways, sends every push the wrong way.",
        "Robot-relative driving skips the gyro: forward is wherever the robot's front points. Trying both is a quick way to tell a gyro problem from a module problem."] },
    vision_pose: { title: "Vision pose", short: "A camera that sees an AprilTag works out where the robot is, and the code blends that into odometry.",
      body: ["Every tag's place on the field is known, so seeing one tells the camera where it is and, from the camera's mount, where the robot is. The code accepts a sighting only when it is believable: close enough, clear enough, and not far from where odometry already puts the robot. The Live tab counts the ones it rejects.",
        "A camera mount measured wrong moves every sighting by the same mistake, which is why the Calibrate tab measures it."] },
    simulator: { title: "The simulator", short: "Your robot code running on this laptop with pretend physics. Safe for learning the tool; its numbers are never the real robot's.",
      body: ["The simulator runs the same robot code against a physics model of the drivetrain. Nothing real moves, so it is a good place to learn what each test does and to check code changes.",
        "Its sensors are perfect: no noise, no backlash, no carpet, no battery sag. Gains that pass in the simulator still have to be tuned on the robot, so simulator runs never tick a Guide step."] },
    wheel_size: { title: "Wheel size", short: "The code turns wheel turns into distance with the wheel's diameter, and worn tread is smaller than the 3 inches on the drawing.",
      body: ["One wheel turn moves the robot π times the diameter, so a wheel 2% smaller than the code thinks makes every distance, speed and auto 2% off. Tread wears through a season, so the real diameter shrinks.",
        "The Calibrate tab measures it with a push over a taped distance, and the Straight line test checks it: if the tape says 117.6 in where odometry says 120.0 in, the wheels are 2% smaller than the code thinks."] },
    what_if: { title: "The 'what if' prediction", short: "A small model learned from your own run, re-run with new gains. Good for direction and rough size; the robot has the final word.",
      body: ["The tool fits kS, kV and kA to the step you ran, then replays that run on the model with the same gains. How closely the replay matches tells you how far to trust the prediction.",
        "Then it runs the same setpoints with your new gains, using the SPARK's own controller rules. It leaves out backlash, battery sag and grip changes, so treat a big change as a hint and run it for real."] },

    motor_basics: { title: "What a motor's numbers mean", short: "Volts set how fast it can spin; amps make its torque, and its heat. Every motor has a free speed, a stall torque, and its most power halfway between.",
      body: ["Spin a motor with no load at 12 V and it reaches its <b>free speed</b>. Hold it still and it pulls its <b>stall current</b> and makes its <b>stall torque</b>. In between, speed and torque trade off along a straight line: the harder it pushes, the slower it turns.",
        "It makes the most power at half its free speed and half its stall torque. Volts decide how fast it can go; current makes the torque - and the heat, as current squared. A stalled motor does no work and makes the most heat.",
        "<b>Kv</b> says how many rpm each volt buys: a NEO's 473 rpm a volt times 12 V is its 5676 rpm free speed.",
        "REV's numbers at 12 V: NEO V1.1 5676 rpm, 105 A and 1.92 ft·lb (2.6 N·m) at stall as REV measured it, 406 W peak. NEO 2.0 5676 rpm, 150 A, 2.77 ft·lb (3.75 N·m), 540 W. NEO 550 11000 rpm, 100 A, 0.72 ft·lb (0.97 N·m), 279 W. NEO Vortex 6784 rpm, 211 A, 2.66 ft·lb (3.6 N·m), 640 W.",
        "Idle, a controller can short the windings (<b>brake</b>: the motor resists being turned) or leave them open (<b>coast</b>: it spins freely). Ramping and current limits trade a little quickness for less heat and fewer brownouts."],
      links: ["spmotors", "spmotorslides", "revneo", "revvortex"], credit: "Adapted in part from Spectrum 3847's training curriculum: Beginner Motors for FRC (C2.3)." },
    brushed_brushless: { title: "Brushed and brushless motors", short: "Both push a magnet around with electromagnets. A brushed motor switches its coils with brushes rubbing a commutator; a brushless one lets its controller switch them, from sensors that say where the rotor is.",
      figures: [
        { src: "img/motor/motor-brushed.svg", alt: "A brushed motor turning: magnets outside, the rotor coil inside, the commutator flipping its current every half turn under the brushes", caption: "Brushed: the brushes and commutator flip the coil's current every half turn." },
        { src: "img/motor/motor-brushless.svg", alt: "A brushless motor turning: three phases of stator coils switched in turn while three Hall sensors report the rotor's position", caption: "Brushless: the controller switches the three phases from where the Hall sensors say the rotor is." }],
      body: ["A <b>brushed</b> motor's coils are on the part that spins. Brushes press on a segmented ring (the commutator) that flips the current in each coil as it turns, so it keeps turning the same way. Easy to drive - give it volts - but the brushes wear and spark, and the commutator heats.",
        "A <b>brushless</b> motor turns that inside out: the coils sit still on the outside part (the stator), the magnets spin. Nothing rubs, so its controller must switch the coils itself, in turn, at the right moment. To do that it must know where the rotor is.",
        "Sensored motors tell it: a NEO has three Hall sensors. Sensorless controllers guess from the voltage the spinning magnets make, which a motor standing still doesn't make - so they struggle to start. That is why REV says a NEO will not spin without its sensor cable.",
        "Why FRC went brushless: more power for the weight, more efficient, nothing to wear but the bearings, coils on the case where they cool, and the built-in sensor that counts how far and how fast it turned. The 2026 rules still allow brushed motors such as the CIM, Mini-CIM, BAG and 775pro (R501); a SPARK MAX drives either kind."],
      links: ["spmotors", "wikibrushed", "wikibldc"], credit: "Adapted in part from Spectrum 3847's training curriculum: Beginner Motors for FRC (C2.3)." },
    inrunner_outrunner: { title: "Inrunners and outrunners", short: "Which part spins: an inrunner's magnets turn inside its coils; an outrunner's magnets are on an outer can that turns around them.",
      figure: { src: "img/motor/motor-in-out-runner.svg", alt: "An inrunner beside an outrunner: the inrunner's rotor turns inside its coils, the outrunner's outer can turns around them", caption: "Only the magnets turn: inside the coils, or on a can around them." },
      body: ["An <b>inrunner</b> has its magnet rotor inside the coils: it spins fast, with little torque, so it needs gearing.",
        "An <b>outrunner</b> has its magnets on a can that turns around the coils. It usually has more magnet poles, so it turns slower and makes more torque.",
        "REV calls the NEO V1.1, NEO 2.0 and NEO 550 out-runners; WCP calls the Kraken X60 and X44 outrunners. REV doesn't say which the Vortex is (it has a through-bore rotor, so its shaft swaps out).",
        "The NEO 2.0's outer can is exposed and turning: keep wires and zip-tie tails clear of it."],
      links: ["wikioutrunner", "revneo2", "revvortex"] },
    pole_pairs: { title: "Pole pairs", short: "A rotor's magnets come in north-south pairs. Each pair needs one full electrical cycle from the controller, so a 7-pair motor goes through 7 cycles a turn.",
      figure: { src: "img/motor/motor-pole-pairs.svg", alt: "A rotor of seven north-south magnet pairs turning once while the controller's electrical wave goes through seven cycles", caption: "One mechanical turn, seven electrical cycles: 6 Hall states each, 42 counts." },
      body: ["The rotor's magnets alternate north, south, north... One north-south pair is a <b>pole pair</b>. To carry the rotor past one pair, the controller goes through one electrical cycle: all three phases, in turn.",
        "So the switching frequency is rpm x pole pairs / 60. REV lists the Vortex at 7 pole pairs: at its 6784 rpm free speed the SPARK Flex switches about 791 cycles a second.",
        "Three Hall sensors give 6 states in each electrical cycle. Six states times 7 pole pairs is 42: the NEO's built-in encoder counts 42 a turn. (REV publishes the 42; the 7 pole pairs come from a Chief Delphi explanation.)",
        "On a SPARK Flex the Vortex's own encoder reads 7168 counts a turn, far finer. More poles generally mean more torque and less top speed for the same volts - one reason outrunners have more."],
      links: ["wikisync", "revvortexspec", "cdneo42"] },
    heat_estimate: { title: "Heat estimate", short: "The guard's estimate of how hot the windings are, from the current. The only warning fast enough for a NEO 550.",
      body: ["Heat in a motor comes from current squared. The guard integrates it with a model fitted to REV's own burn-out tests. The temperature sensor on a NEO 550 sits outside the windings and lags them by tens of seconds - REV saw one die at 40 A while reading about 40 °C."] },
    derate: { title: "Derate", short: "The guard halves a hot motor's current limit so it can cool while still working.",
      body: ["Half the current is a quarter of the heat. The motor keeps working, slower, until it cools 10 degrees (or 10 points) below the line. Nothing is saved to the controller's flash."] },
    stall: { title: "Stall", short: "At the current limit but not turning: a jam, or pushing into a hard stop. All heat, no work.",
      body: ["A stalled motor turns all its power into heat. The stall timer warns at 3 s, derates, and cuts it after its limit. Drive motors are exempt: they stall in every pushing match, and the heat estimate guards them."] },
    thermal_override: { title: "Thermal override", short: "For the end of a match: hold a heat shutoff at half current for up to 20 s. Never lifts a stall cut.",
      body: ["Sometimes losing the motor costs more than the motor. The override holds a heat SHUTOFF at DERATE instead, for at most 20 s, and never past a sensor 10 °C over shutoff or a 95% heat estimate."] },

    can_bus: { title: "The CAN bus", short: "One pair of twisted wires (CAN-H in the bus's own color, yellow on the first; CAN-L always green) daisy-chained through every controller. Every device hears every message.",
      body: ["Each controller has a CAN ID and two CAN connections joined inside it, so the cable passes straight through - even when the controller has no power. The chain runs from the robot controller (roboRIO or SystemCore) to the far end, usually the PDH.",
        "That pass-through is the key to finding faults. One device missing while its neighbors are heard means that device (its power, or the controller). Everything past one point missing together means the cable or a plug at that point.",
        "CAN has no idea of position, so the order along the cable can't be read from the robot: someone checks it by eye once, and the map remembers it."], links: ["frccan"] },
    can_termination: { title: "CAN termination", short: "A 120 ohm resistor at each end of the CAN chain stops signals echoing back. Exactly two: about 60 ohms measured across the bus, power off.",
      body: ["A fast signal reaching the open end of a wire bounces back and garbles the next bits. A 120 ohm terminator at each end soaks it up. A roboRIO has one built in (SystemCore has one on each of its buses); the PDH has one you switch on.",
        "With every device powered off, a multimeter across CAN-H and CAN-L reads both in parallel: about 60 ohms. 120 means one end is missing (or the cable is broken between you and it); 40 means one too many; near zero is a short.",
        "To tell a missing terminator from one that is fitted but not working, measure at the far end twice: with its terminator in, then out. 60 then 120: both work. 120 then 120: the far one does nothing (a switch not fully across, a terminator not seated). 120 then OL: the far one works and the cable back to the robot controller is broken.",
        "Bad termination shows up as CAN errors and, at worst, the bus shutting itself down (bus-off)."], links: ["frcterm"] },
    power_path: { title: "The power path", short: "Battery, main breaker, PDH, a breaker per port, then the leads to each controller. Every joint adds a little resistance; a bad one adds a lot.",
      body: ["Current flows from the battery through the main breaker to the PDH, out through a port's breaker and along two leads to the controller, and back. Every crimp, Wago and screw terminal on the way is a small resistor.",
        "Resistance turns current into lost voltage (V = I x R). A good feed loses about 0.6 V at 40 A. A loose joint can lose several volts: the controller sees a low supply, warns, and if it drops too far it reboots - vanishing from the CAN bus while it restarts.",
        "The tool compares the voltage each controller sees with the PDH's, at the current the PDH measured on that port, to estimate each feed's resistance. One controller rebooting points at its own feed; many at once points upstream, at the battery or main breaker."], links: ["frcpower", "frcconn"] },
    wire_gauge: { title: "Wire gauge (AWG)", short: "A wire's gauge says how thick its copper is: a smaller number is thicker. FRC's rules set the thinnest wire each circuit may use.",
      figure: { src: "img/wire/wire-gauge.svg", alt: "FRC's wire gauges from 4 to 22 AWG, copper drawn to scale, each with its resistance a foot, the rule it meets, and the volts and heat lost on a typical run",
        caption: "Copper to scale. The loss is worked out and back, as the Wiring tab's wire calculator does." },
      body: ["AWG (American Wire Gauge) counts backward: 4 AWG is thick, 22 AWG thin. Every 3 gauges thicker doubles the copper and halves the resistance; every 6 doubles the diameter.",
        "FRC's rules (2026 game manual) set the thinnest wire each circuit may use: the battery, its SB connector, the main breaker and the power distribution board are joined with 6 AWG or larger (R609); a 31-40 A breaker's circuit needs 12 AWG, 21-30 A 14 AWG, 6-20 A 18 AWG, and signal wire, CAN included, 28 AWG (R622, Table 8-4). Thicker is always allowed.",
        "Positive wire is red, yellow, white, brown, or black with a stripe; negative is black or blue (R624).",
        "This team's battery leads are 4 AWG: thicker than R609 asks, so they lose less. The tight spot is the SB50's contact, made for 6 AWG: the SB50 lesson has the checks that matter.",
        "FRC teams use silicone-insulated wire: many fine strands (CTRE's 12 AWG has 600), very flexible, rated to 200 °C (392 °F). More strands bend tighter and survive vibration longer. Silicone is soft, so keep it off sharp edges: it rubs through."],
      links: ["frcmanual", "awgwiki", "wpiwiring"] },
    crimp_molex_sl: { title: "Crimping a Molex SL (CAN)", short: "The CAN bus's 2-pin plug. A good crimp grips bare copper in one place and the insulation in another; CAN-H (the wire that isn't green) goes on pin 1, the one the triangle marks.",
      figures: [
        { src: "img/crimp/molex-sl-crimp.svg", alt: "A Molex SL terminal crimped well, labeled front to back, and four bad crimps", caption: "Good, front to back; then the four bad crimps teams make most." },
        { src: "img/crimp/molex-sl-polarity.svg", alt: "The Molex SL housing's face: the triangle marks pin 1, CAN-H (the bus's color) on pin 1, green CAN-L on pin 2, and a mated pair", caption: "Pin 1, CAN-H (the bus's color, never green), is the one the triangle on the housing marks. The same on every plug on the robot." }],
      body: ["The terminal (Molex 16-02-0103) takes 22-24 AWG wire, crimped with Molex's 63811-8700 tool. Strip 0.100-0.125 in (2.5-3.2 mm).",
        "Front to back, a good crimp has: the contact, with nothing in it; the conductor crimp, wrapped round bare strands only, its seam closed; the strands poking 0-1.0 mm past it, never into the contact; a small flare at its back (the bellmouth); a window where both bare copper and the end of the insulation show; and the insulation crimp, holding the insulation.",
        "Bad crimps are the most common cause of intermittent connection issues (CTRE): insulation under the conductor crimp, strands outside the barrel, the wire pushed into the contact, or a terminal that isn't latched and backs out when the plug goes in. On the robot that is a device that drops off the CAN bus when the robot moves: the wiggle test finds it.",
        "Tug each wire, one at a time. A good 24 AWG crimp holds 6.5 lb.",
        "Pin 1 is marked by a small triangle on the housing. CAN-H goes there: it is the bus's own color (yellow, white, light blue or purple on this team's buses), never green. CAN-L, green on every bus, goes on pin 2. The same on every plug on the robot: swapped CAN-H and CAN-L is a common failure. With the robot off, about 60 Ω between CAN-H and CAN-L says both terminators are there (the termination check)."],
      links: ["frcconn", "ctrecan", "molexcrimp"] },
    crimp_powerpole: { title: "Crimping an Anderson Powerpole", short: "The red and black plugs on motor controllers and the PDH. Crimp bare copper only, click the contact in with its hook against the spring, and red right, tongue top.",
      figures: [
        { src: "img/crimp/powerpole-crimp.svg", alt: "A Powerpole contact crimped well, and the bad crimps teams make", caption: "Good: bare copper in the barrel, insulation just short of it. Then the bad ones." },
        { src: "img/crimp/powerpole-polarity.svg", alt: "A red and black Powerpole pair seen from the mating face: red on the right, tongues on top, and a mated pair", caption: "Red right, tongue top: built that way, every pair on the robot mates with every other." }],
      body: ["Contacts: 30 A for 16-12 AWG, 45 A for 14-10 AWG; FRC motor leads are usually 12 AWG. Strip 5/16 in (7.9 mm) and crimp with a Powerpole tool: Anderson warns that other tools give high-resistance joints or bent contacts that won't seat.",
        "A good crimp grips bare strands only, with the insulation stopping just short of the barrel and the wire not past the wire stop. Bad ones: insulation under the crimp, a long bare gap, strands poking toward the mating end, a spread tab, or solder (it is brittle and cracks under vibration).",
        "The contact goes in one way only, its hooked edge toward the flat spring in the housing. Push it until it clicks; it should then float a little. Push it back from the front: a seated contact holds 20 lb.",
        "Red is +, black is -. Looking at the mating face: red on the right, tongues on top (red right, tongue top). Built that way, every pair on the robot mates with every other. Slide the two housings' dovetails together; snapping them on sideways breaks them.",
        "A bad Powerpole crimp is a small resistor carrying a motor's current: it heats, and the motor controller browns out or the motor cuts out under load."],
      links: ["frcconn", "pptools", "ppwiki"] },
    crimp_sb50: { title: "The battery's SB50 (with 4 AWG)", short: "The big red battery connector. Every strand in the barrel, each contact snapped over its spring, red wire to +.",
      figures: [
        { src: "img/crimp/sb50-crimp.svg", alt: "An SB50 contact crimped on 4 AWG wire, and the four ways that goes wrong", caption: "This team's 4 AWG in the 6 AWG contact: the checks that matter." },
        { src: "img/crimp/sb50-polarity.svg", alt: "Two red SB50 housings about to mate: red wire to red, black to black, each contact's notched tongue against its spring", caption: "Genderless: two identical halves mate. Polarity is the wire color: red to +." }],
      body: ["FRC batteries carry a red (or pink) SB50, and only red and pink mate with red (R609). The housing is genderless: two identical halves mate. It has no + or - mark, so polarity is the wire color: red to the battery's +, black to -. Wire every SB50 on the team the same way, and check a charger's polarity with a multimeter.",
        "Strip 9/16 in (14 mm). Anderson's contact for 6 AWG has a 0.22 in (5.59 mm) barrel; there is no SB50 contact for 4 AWG (Anderson's 4 AWG connector is the SB120). This team runs 4 AWG in its SB50s: legal, since R609 asks for 6 AWG or larger, and the thicker copper loses less. The barrel is the tight spot, so every crimp gets checked.",
        "What goes wrong with 4 AWG in that barrel: strands trimmed to make it fit (less copper), strands left outside (a hot spot, or a short), a barrel split or flared by forcing it or the wrong die (frcelectrical.org lists the 25 die for 4 AWG), or a contact that won't snap over its spring and pushes back out when the plugs mate.",
        "Seat each contact with the notched side of its tongue against the spring, pushing on the contact, not the insulation, until it snaps over the end of the spring; then tug. A seated contact holds 50 lb.",
        "Check each one: a pull test, push the contact back from the front, and feel the connector after a match: warm means resistance. A loose battery connection makes the robot reboot or drop off the field for 30 seconds or more (WPILib). Hold the connector with clips or zip ties so the lugs can't move."],
      links: ["wpibatt", "frcbatt", "sb50sheet"] },
    wire_loss: { title: "Resistance, length and lost power", short: "Every wire is a small resistor. Longer or thinner means more resistance; more current through it means volts lost on the way and heat in the wire.",
      body: ["A wire's resistance grows with its length and shrinks with its thickness: R = resistivity x length / area. A foot of 12 AWG copper is about 1.6 milliohms (mΩ); a foot of 4 AWG, about 0.25 mΩ.",
        "Current goes out along one wire and comes back along the other, so a lead 3 ft long is 6 ft of wire. That 12 AWG pair: 6 x 1.6 = 9.5 mΩ.",
        "<b>Volts lost</b> = current x resistance (Ohm's law, V = I x R). At 40 A that pair loses 0.38 V: the motor controller sees 11.6 V when the PDH has 12. At a stalled NEO's 105 A it loses 1 V.",
        "<b>Power lost</b> = current squared x resistance (P = I² x R), and it all becomes heat in the wire: 40 A through 9.5 mΩ is 15 W, spread along it. Double the current and the heat goes up four times. That is why a stalled motor's leads get hot fast.",
        "What changes it: <b>twice the length</b>, twice the volts lost and twice the heat. <b>Three gauges thicker</b> (every 3 gauges doubles the copper), half of both. A warm wire also has a little more resistance: copper adds about 0.4% for every degree C.",
        "The battery leads carry the whole robot's current, so they matter most. At 200 A, 2 ft of 6 AWG each way (1.6 mΩ) loses 0.32 V and makes 63 W of heat; 4 AWG (1.0 mΩ) loses 0.2 V and makes 40 W.",
        "A bad crimp or a loose bolt can add more resistance than all the wire put together: the same V = I x R and I² x R, at one small spot that gets hot."],
      try: "On the Wiring tab's wire calculator, put in your longest motor lead at a stalled NEO's current, then try one gauge thinner and twice the length.",
      links: ["frcpower", "frcconn"] },
    motor_inventory: { title: "Motors and controllers", short: "A SPARK MAX and a SPARK Flex, or a NEO and a Vortex, look alike in code but aren't. The code must create the controller that's really there, and know which motor it drives.",
      body: ["The controller is the box on the CAN bus: a SPARK MAX or a SPARK Flex. Each one reports which it is, so the robot can check the code created the right one.",
        "The motor is what the controller drives: a NEO, a NEO 2.0, a Vortex, a NEO 550. A controller can't tell which, so someone has to say - and it matters: free speed, torque per amp, the current limit and how fast it heats all differ.",
        "One measurement can tell: how fast a motor spins per volt. A NEO turns about 473 rpm per volt, a Vortex 565, a NEO 550 917. The feedforward test measures exactly that for the drive motors. A NEO V1.1 and a NEO 2.0 spin alike, so those only a person can tell apart."] },
    gyro: { title: "The gyro", short: "Measures how fast the robot turns and adds it up into a heading. Field-relative driving, odometry and every auto depend on that heading.",
      body: ["A gyro measures turning rate and integrates it: heading is the sum of every little turn since it was zeroed. Small errors add up. A gyro that reads 1% short is 3.6 degrees off after one full turn, and 36 degrees after ten.",
        "Where it sits doesn't matter for the heading: every part of a rigid robot turns by the same angle. What matters is that it calibrates while the robot is completely still after power-on, sits level and firm, and is checked: a minute standing still shows drift; full turns back to a line show scale.",
        "AprilTags fix heading whenever they are seen, so a camera hides a small gyro error. Without one, the gyro is all the robot has."] },
    gyro_mems: { title: "How a gyro works", short: "A tiny mass in the chip vibrates; when the robot turns, the Coriolis effect pushes it sideways in step with its vibration, and the size of that wiggle is the turn rate.",
      figure: { src: "img/sensor/gyro-mems.svg", alt: "A vibrating mass on springs in a chip; when the chip turns, the mass also wiggles sideways in step with its vibration, and the heading changes only while it turns", caption: "The sideways wiggle's size is the turn rate; heading is that rate added up." },
      body: ["Inside a MEMS gyro a tiny mass is kept vibrating back and forth on springs. When the chip turns, the Coriolis effect pushes the moving mass sideways - one way as it swings out, the other way as it swings back, because the push follows its motion. So turning adds a small sideways wiggle in step with the vibration.",
        "The push is the mass's speed times the turn rate, so the size of that wiggle says how fast the chip is turning, and which way it goes compared with the vibration says which direction. The chip measures it the way it measures everything in there: comb-like fingers on the mass move closer to or farther from fixed ones, and the change in capacitance between them is read as motion.",
        "So a gyro measures turn rate. Heading is that rate added up over time - and every tiny error adds up with it, so a gyro <b>drifts</b>. Temperature changes it too, which is why it calibrates sitting still.",
        "Its partner, the accelerometer, feels gravity and so corrects tilt - but gravity says nothing about which way the robot faces, so heading drift is the gyro's alone. AprilTag sightings are what correct heading.",
        "The Redux Canandgyro is both in one (an IMU). It calibrates when it powers up still (its light yellow); Redux says to leave it still at least 7 s. It drifts about 0.2 degrees an hour standing still and 0.25 degrees a minute moving, and reads up to 2000 degrees a second over CAN."],
      links: ["wikimems", "wpigyro", "reduxgyro"] },
    accelerometer: { title: "How an accelerometer works", short: "A tiny mass on springs inside the chip lags when it speeds up and sags toward gravity; the chip measures how far it moved.",
      body: ["Inside a MEMS accelerometer a tiny mass (the proof mass) hangs on springs. Speed the chip up and the mass lags behind, stretching the springs; slow it down and the mass swings ahead. Comb-like fingers on the mass sit between fixed ones, and the chip reads how the gaps change (the capacitance) as how far the mass moved: that is the acceleration.",
        "Gravity pulls on the mass too, so standing still it reads 1 g, pointing up - the support holding it against gravity. In free fall it would read zero. Tip the chip and part of gravity points sideways: that is how it measures tilt (pitch and roll).",
        "Gravity says nothing about which way the robot faces, so an accelerometer can't correct a gyro's heading. Together they make an IMU (inertial measurement unit); the Redux Canandgyro is one, reading up to 16 g.",
        "On the robot: a sudden spike is a hit - the tool's impact stop watches for one - and a steady sideways reading while still means the robot is tipping. It measures acceleration, not speed: adding it up into a speed drifts even faster than a gyro's heading."],
      links: ["wikiaccel", "reduxgyro"] },
    pull_resistor: { title: "Pull-up and pull-down resistors", short: "A resistor that gently holds an input high (pull-up) or low (pull-down) when nothing else drives it, so a switch has something to switch against.",
      figure: { src: "img/sensor/pull-resistor.svg", alt: "A floating input reading at random; a pull-up circuit and a pull-down circuit, each with a switch closing and opening and the reading changing", caption: "Same switch, opposite readings: a roboRIO pulls up, SystemCore pulls down." },
      body: ["An input pin connected to nothing - <b>floating</b> - picks up stray electrical noise and reads high or low at random. A resistor from the pin to the supply (a <b>pull-up</b>) or to ground (a <b>pull-down</b>) gives it a steady reading when nothing else is connected.",
        "A switch then overrides it: with a pull-up, closing a switch to ground pulls the pin low; with a pull-down, closing a switch to the supply pulls it high. The resistor is large, so only a tiny current flows while the switch is closed.",
        "The two robot controllers differ. A roboRIO's digital inputs have pull-ups inside: wire a switch between signal and ground, and it reads true when open, false when closed. SystemCore's Smart I/O ports (3.3 V) have pull-downs instead: wire a switch between signal and 3.3 V, and it reads false when open, true when closed (WPILib).",
        "So the same switch reads the opposite way on the two, and code written for one reads backwards on the other. WPILib warns that sensors made for the roboRIO's ports may not work on SystemCore's without different wiring.",
        "Some sensors can only pull a line low (an open-collector or open-drain output, like a common break-beam receiver): they need a pull-up to read high. A roboRIO has one; on SystemCore's pull-down ports such a sensor needs its own - check its docs."],
      links: ["wpidio", "wikipull"] },
    limit_switch: { title: "Touch and magnetic limit switches", short: "A switch the mechanism presses, or a magnet sensor it passes. Which way it reads depends on the controller: see pull-up and pull-down resistors.",
      figure: { src: "img/sensor/limit-switch.svg", alt: "A lever switch wired to a roboRIO input with its pull-up resistor: normally open and normally closed, what each reads pressed and not, and a magnetic limit switch seeing a magnet", caption: "Drawn on a roboRIO (pull-up). Wire it normally closed and a broken wire reads as pressed: the safe way to fail." },
      body: ["A limit switch tells the robot a mechanism has reached the end of its travel. A touch switch is pressed by the mechanism; a magnetic one sees a magnet on it go by.",
        "A <b>normally open</b> switch closes when pressed; a <b>normally closed</b> one opens when pressed. On a roboRIO (pull-ups) a normally open switch reads true when free and false when pressed; on SystemCore (pull-downs, the switch wired to 3.3 V) it reads the other way.",
        "WPILib calls normally closed safer: a broken or unplugged wire looks exactly like the switch being pressed, on either controller, so the mechanism stops instead of driving through its limit.",
        "Metal contacts bounce when they close - see contact bounce - so code that counts presses should debounce.",
        "A magnetic limit switch has no contacts to wear or bounce: REV's uses Hall sensors that see either pole of its magnet about 0.4 in (10 mm) away, and pulls its output low when it does."],
      links: ["wpiprox", "wpidio", "revmaglimit"] },
    contact_bounce: { title: "Contact bounce, and debouncing", short: "Metal contacts are springy: one press hits, bounces apart and hits again a few times in a few thousandths of a second, so the input sees several changes.",
      figure: { src: "img/sensor/contact-bounce.svg", alt: "A springy contact blade hitting a fixed contact and bouncing apart three times; beside it, the raw reading flipping seven times and the debounced reading changing once", caption: "One press, seven raw changes; the debounced reading changes once, after it holds steady." },
      body: ["When two metal contacts snap together they don't just stop. They are springy, so they hit, spring apart and hit again, smaller each time, like a dropped ball. It is all over in a few thousandths of a second - far too quick to see or feel.",
        "A person presses once, but the input reads closed, open, closed, open... Code that toggles something on every change - intake on, intake off - may flip it several times and end wherever the bounce stops. Code that counts presses counts too many.",
        "A robot loop reads its inputs once every 20 ms, so it usually misses most of a bounce, but it can still catch one reading mid-bounce. Anything that counts every edge (a counter, or an interrupt) sees all of it.",
        "<b>Debouncing</b> fixes it: only believe a new reading once it has stayed the same for a moment. WPILib's Debouncer does that (for example, a change must last 0.05 s), and a command Trigger can debounce too.",
        "Magnetic (Hall) and optical sensors have no metal contacts, so they don't bounce this way. A Hall switch held right at its trigger distance could flicker instead; built-in hysteresis prevents that (REV's magnetic limit switch: about 0.2 in, 5 mm)."],
      links: ["wpidebounce", "wikibounce"] },
    break_beam: { title: "Break-beam sensors", short: "A beam of light across a gap; a game piece breaking it says the piece is there.",
      figure: { src: "img/sensor/break-beam.svg", alt: "An infrared emitter and receiver across a gap; a ball rolls through and breaks the beam, and the output changes", caption: "Beam clear: high. Beam broken: low." },
      body: ["A <b>through-beam</b> sensor has an emitter on one side and a receiver on the other; a piece between them blocks the beam. A <b>retroreflective</b> one has both on one side and a reflector across the gap; a <b>diffuse</b> one sees light bounced off the piece itself.",
        "A common one (Adafruit's 3 mm infrared pair) sees about 10 in (25 cm). Its receiver can only pull its line low (open collector), which it does when the beam is broken: on a roboRIO input (with its pull-up) it reads false when blocked. On SystemCore's pull-down ports it needs its own pull-up - see pull-up and pull-down resistors.",
        "Sunlight can blind an infrared receiver, and shiny or dark pieces change what the reflective kinds see. Aim through-beams across the piece's path where nothing else crosses."],
      links: ["wikiphoto", "adabeam", "wpidio"] },
    time_of_flight: { title: "Time-of-flight distance sensors", short: "It fires a pulse of invisible light and times the echo: distance = speed of light x time / 2.",
      figure: { src: "img/sensor/time-of-flight.svg", alt: "A light pulse leaving the sensor, reaching a target and coming back while a timer counts; distance is the speed of light times the time, halved", caption: "Light is fast: 3.3 ft (1 m) away is a round trip of under 7 billionths of a second." },
      body: ["The sensor sends a short pulse of infrared laser light and measures how long until it comes back. The light went there and back, so the distance is the speed of light times the time, divided by 2.",
        "The light is fast, so the chip times it to billionths of a second. Bright light and dark targets shorten the range: ST's VL53L1X chip reaches 360 cm on a white target in the dark but 73 cm in strong light.",
        "In FRC: Grapple's LaserCAN (up to 4 m, CAN, 10-50 Hz), CTRE's CANrange (1-300 cm, CAN, up to 100 Hz; it can stand in for a beam break or limit switch), Playing With Fusion's (up to 4 m, CAN, 50 Hz) and REV's 2m Distance Sensor (5-200 cm, I2C).",
        "Its beam spreads into a cone (a field of view), so mount it where the cone sees only the target, not the floor or the robot's own frame."],
      links: ["wikitof", "canrange", "revdist"] },
    current_sensing: { title: "How current and voltage are sensed", short: "Current: the tiny voltage across a very small resistor in the path. Voltage: two resistors scale it down to what a converter chip can read. Both end as numbers from an ADC.",
      figure: { src: "img/power/sense-current.svg", alt: "Current through a tiny shunt resistor makes a small voltage, an amplifier makes it bigger, and an ADC turns it into a number of amps", caption: "Current: V = I x R across a very small resistor, amplified, then counted." },
      body: ["Chips can only measure voltages, and only small ones, with an <b>ADC</b> (analog-to-digital converter) that turns a voltage into a number in steps - more bits, finer steps. Everything else is about turning what you want to know into a small voltage.",
        "<b>Current:</b> put a tiny resistor (a shunt, thousandths of an ohm) in the path. By Ohm's law the voltage across it is the current times its resistance: 40 A through 0.001 ohm is just 0.04 V. A current-sense amplifier makes that bigger, and the ADC reads it. The other way is a Hall-effect sensor that feels the current's magnetic field, with nothing in the path. REV doesn't say which its parts use.",
        "The PDH reads its channels with current-sense amplifiers, one per group of four: its big channels 0-127.9 A in 0.125 A steps, its small ones 0-31.94 A in 0.0625 A steps. A SPARK senses the current in its motor's phases, so its current limit limits the motor's current - not what the PDH sees, which below full output is less (see battery-side current).",
        "<b>Voltage:</b> a battery's 13 V is too much for an ADC's input, so two resistors in series - a voltage divider - scale it down first (the output is the input times R2 / (R1 + R2)), and the code multiplies the reading back up.",
        "That is how the robot controller (roboRIO or SystemCore), the PDH and each SPARK report the battery voltage they see. Each sees it after its own wires and joints, so under load they read a little differently - the gaps are the power path's losses."],
      links: ["revpdh", "wikicurrent", "wikidivider"] },
    apriltag_detect: { title: "How a camera finds a tag", short: "It finds the tag's black square, reads its pattern of squares, and from where the four corners land in the picture works out where the camera must be.",
      body: ["The camera's picture goes to gray, gets smaller to save time, and is split into black and white; the processor looks for four-sided shapes, then reads the grid of squares inside each (6 by 6 in FRC's tag family) to get the tag's number.",
        "Knowing the tag's real size and the camera's lens (its calibration), the four corners' places in the picture say where the camera is relative to the tag. Two different poses can put the corners in almost the same spots - <b>ambiguity</b>: PhotonVision suggests ignoring single tags with ambiguity over 0.2.",
        "Seeing several tags at once (MultiTag) removes it, using where every tag is on the field - so the field layout must be accurate (see Surveying the field's tags).",
        "Keep exposure as low as the picture allows: a blurred tag is a wrong tag. Global-shutter cameras take the whole picture at one instant; rolling-shutter ones scan it row by row, which skews a moving tag."],
      links: ["wpiapriltag", "pv3d", "pvmultitag"] },
    pathplanner_model: { title: "PathPlanner's copy of the robot", short: "PathPlanner plans every auto from its own description of the robot. If it describes a different robot, the paths ask for things this one can't do.",
      body: ["To plan a path, PathPlanner works out how fast each wheel can speed up and how fast the robot can turn: from the motor, the gearing, the wheel size, the module positions, the current limit, the mass and the moment of inertia. It keeps all of that in its own file, not in the code.",
        "Nothing keeps the two in step. Change the gearing in YAGSL and forget PathPlanner, and every auto is planned for the old robot: the robot falls behind the path, and the path controller chases the error.",
        "The same goes for names: an auto that calls a named command the code never registered just skips that step, with only a console warning."] },
    moment_of_inertia: { title: "Moment of inertia", short: "Mass says how hard a robot is to push; moment of inertia says how hard it is to turn. Weight far from the center (bumpers, battery) counts much more than weight near it.",
      body: ["Turning, every bit of the robot moves in a circle. A pound at the bumper moves fast and takes a lot to speed up; a pound at the center barely moves. Moment of inertia adds that up: mass times distance squared, in lb·in² here (PathPlanner and the files keep kg·m²).",
        "PathPlanner needs it to know how quickly the robot can start and stop rotating. Too small and autos ask for turns the robot can't make; too big and they turn timidly.",
        "It can't be weighed, so the tool measures it: spinning in place with every wheel along its circle, the voltage needed to speed up the spin (angular kA) against the voltage needed to speed up a straight push (linear kA) gives it, with the mass and the module radius: MOI = mass x radius x kA(turning) / kA(straight)."] },
    camera_mount: { title: "Where the camera sits", short: "Vision turns a tag in the picture into a robot pose through one fixed transform: robot center to camera lens. If that is wrong, every vision pose is wrong by the same amount, or worse.",
      body: ["The camera knows where the tag is relative to itself. The field layout knows where the tag is on the field. Chaining them gives where the camera is on the field, and the mount takes that back to the robot's center.",
        "A position error moves every pose by the same distance. An angle error is worse: it grows with distance, about 2 in per 10 ft for each degree, so a tag 13 ft away puts the pose nearly 3 in off for one degree of tilt the code doesn't know about.",
        "Measuring the mount with a tape is hard - where exactly is the center of a lens, and how much is it tilted? A tag on a wall at a measured spot gives the answer from the camera itself, and doing it from several spots shows how well the tape measurements agree."] },
    field_survey: { title: "Surveying the field's tags", short: "Localization trusts every AprilTag to be exactly where the official layout says. People hang them, so measure where they really are.",
      body: ["Two tags in the same camera frame fix where they sit relative to each other, whatever the robot's own position. Many frames tie whole groups of tags together; each group is then fitted onto the official layout, and what is left over is how far each tag really is from its place.",
        "Every measurement has noise, so a tag is only changed when it moved by clearly more than its own uncertainty - three times it, and at least 0.4 in. Noise must never move a tag.",
        "Anything more than about 12 in off is refused: that is a misread or a tag on the wrong bracket, not something to copy into the robot. And a whole structure moved as one piece looks right this way: its tags still agree with each other."] },
    battery_current: { title: "Battery-side current", short: "The PDH measures the current a controller takes from the battery. Below full speed that is much less than the current in the motor.",
      body: ["A motor controller is a fast switch. At 25% output it connects the motor to the battery a quarter of the time; the rest of the time the motor's current keeps circulating through the controller, not the battery.",
        "Power in equals power out (minus a little heat), so battery current = motor current x output fraction. A drive motor pulling 20 A at 25% output takes only about 5 A from its PDH port.",
        "That is why the PDH port finder looks for which channel <i>rises</i>, not for the motor's own number, and why a motor stalled at low output can be hot while its breaker never notices."] },
    wiggle_test: { title: "The wiggle test", short: "With the robot on and disabled, gently move each cable and plug in turn while a tool watches for errors. The step that makes something happen is where the bad connection is.",
      body: ["Loose plugs and cracked wires usually work fine when nothing moves, and fail when the robot hits something. Wiggling recreates that one place at a time.",
        "The tool watches every controller (did it drop off the bus, reboot, or see its supply dip?) and the CAN bus's error counters. Because the counters recover within milliseconds, the robot counts every loop that saw an error, so a glitch too short for a person to notice still shows.",
        "Go in order along the CAN chain, then each controller's power leads, then the main power. Keep hands out while the robot is enabled."], links: ["frcconn"] },
    motion_profile: { title: "Motion profile", short: "Instead of jumping the setpoint, move it smoothly along a planned path of position, speed and acceleration.",
      body: ["A step asks for the impossible: be there now. A profile asks for something the mechanism can actually do: speed up at a set rate, cruise, slow down. Feedback then only has to follow, so it can be stiffer without overshoot, and current spikes vanish.",
        "This is 'second order' control: the plan limits both velocity and acceleration. Do it after the first-order loops (feedforward and PID) work - a profile on top of a badly tuned loop just hides the problem."], links: ["trap", "profiled"] },
    trapezoid_profile: { title: "Trapezoidal profile", short: "Speed up at max acceleration, cruise at max velocity, slow down at max acceleration. On a speed-time graph it's a trapezoid.",
      body: ["WPILib's TrapezoidProfile takes Constraints (max velocity, max acceleration) and gives the setpoint state at each time step. Short moves never reach cruise speed and make a triangle instead.",
        "WPILib's caveat: calculate each step from the previous setpoint, not the measurement, so the plan stays smooth."], links: ["trap"] },
    cruise_velocity: { title: "Cruise velocity", short: "The top speed of the profile's flat middle. Set it a little below what the mechanism can really do.",
      body: ["If the cruise velocity is above what the motor can reach, the profile asks for the impossible and the loop saturates again. 80-90% of measured free speed is a safe start. In MAXMotion it is in RPM, scaled by the velocity conversion factor."], links: ["mmpos"] },
    max_acceleration: { title: "Max acceleration", short: "How fast the profile speeds up and slows down. Too high and you are back to saturation and current spikes.",
      body: ["The current limit sets how hard the motor can push, so it sets the real maximum acceleration. Measure it (kA tells you), then use a margin. In MAXMotion it is in RPM per second, scaled by the conversion factor."], links: ["mmpos"] },
    ff_uses_setpoint: { title: "Feedforward uses the setpoint", short: "Feed the profile's planned speed and acceleration to the feedforward - not the measured ones.",
      body: ["WPILib: add feedforward and feedback, and compute feedforward from the setpoint. Measured values are noisy and late; the plan is exact and on time."], links: ["combine"] },
    maxmotion_position: { title: "MAXMotion position", short: "REV's profile, run inside the SPARK: a trapezoid toward the target, re-planned every 10 ms, followed by a 1 kHz PID.",
      body: ["Set cruise velocity, max acceleration and an allowed profile error, then command kMAXMotionPositionControl. The SPARK can add kS, kV, kA (and kG/kCos for arms) itself. REV warns: retune PID from scratch when switching. In REVLib 2026 the only profile shape is trapezoidal."], links: ["mmpos"] },
    maxmotion_velocity: { title: "MAXMotion velocity", short: "REV's acceleration-limited speed control inside the SPARK: it ramps to a new speed at your max acceleration.",
      body: ["For flywheels and rollers: smoother spin-up, less current, more consistent shots. It runs continuously, so never use it on something with hard stops. For a drivetrain, limiting each wheel separately can bend the robot's path while accelerating; a chassis-level limiter keeps the wheels in step."], links: ["mmvel"] },
    allowed_profile_error: { title: "Allowed profile error", short: "If the mechanism falls this far behind the plan, MAXMotion re-plans from where it really is.",
      body: ["Small: re-plans often, consistent motion, harder to see a bad tune. Large: shows the tune honestly but can lurch when it finally re-plans."], links: ["mmpos"] },
    profiled_pid: { title: "ProfiledPIDController", short: "WPILib's PID with a built-in trapezoid: you give a goal, it follows the moving setpoint.",
      body: ["The goal is where you want to end up; getSetpoint() is where the plan says to be now - feed its velocity to the feedforward. It runs on the robot controller (roboRIO or SystemCore) once every 20 ms loop, so it suits slower mechanisms better than a 1 kHz steering loop."], links: ["profiled"] },

    // ---------------------------------------------------------------- CAN in depth
    can_frame: { title: "A CAN message", short: "An ID that says who sent it and what it is, up to 8 bytes of data, and a checksum. Every device hears every message and keeps the ones it wants.",
      body: ["CAN sends bits as a voltage <i>difference</i> between two wires: CAN-H up and CAN-L down for a 0, both resting for a 1. Twisting the two wires together makes motor noise push both the same way, so the difference doesn't change - that is why CAN survives a robot full of motors.",
        "A message (a <b>frame</b>) is: the ID, the length, up to 8 bytes of data, a 15-bit checksum (CRC) so a garbled message is thrown away and sent again automatically, and an acknowledge bit that any listener sets to say it heard a good message. FRC's bus runs at 1 megabit a second: a full message takes about 0.13 ms.",
        "Nobody addresses a message to anyone. A SPARK's status message goes to the whole bus; the robot controller keeps it because REVLib told it to listen for that ID. That is a <i>broadcast</i> network, like a group chat, not a phone call."],
      links: ["canwiki", "candevs", "frccan"] },
    can_arbitration: { title: "Who talks first (arbitration)", short: "When two devices start at once, the lower ID wins and its message arrives undamaged: a 0 bit on the wire always beats a 1.",
      body: ["A 0 is <b>dominant</b>: one device driving the wires apart beats any number leaving them at rest. Each sender listens to the wire as it sends its ID; the moment it sends a 1 but hears a 0, it knows someone with a lower ID is talking, stops, and tries again after.",
        "So nothing is lost and no time is wasted: the most important (lowest) ID always gets through first. FRC puts the device type at the front of the ID, so the robot controller's heartbeat (type 1) beats every motor controller (type 2) to the wire.",
        "The catch: when the bus is busy, the high IDs wait. A bus near full makes some devices' messages late - see <span class=\"term\" tabindex=\"0\" data-learn=\"can_load\">CAN bus load</span>."],
      links: ["canwiki"] },
    frc_can_id: { title: "FRC's CAN ID", short: "FRC splits the 29-bit ID into device type, manufacturer, which message, and device number. The \"CAN ID\" you set on a SPARK is just the device number.",
      body: ["From the front (most important) end: <b>device type</b>, 5 bits (2 is a motor controller, 4 a gyro, 8 power distribution, 9 pneumatics); <b>manufacturer</b>, 8 bits (1 NI, 4 CTRE, 5 REV, 11 Playing With Fusion, 14 Redux); which message it is, 10 bits (FRC calls this the API; here it just means the message's number: a SPARK's status 0, a setpoint); and <b>device number</b>, 6 bits (0 to 63).",
        "That is why a REV motor controller and a CTRE motor controller can both be number 5, and why a SPARK and the PDH can share a number: their types or makers differ. Two SPARKs at the same number collide - both answer to the same messages, and the robot sees one device behaving strangely.",
        "Most devices ship as number 0 (the REV PH and PDH as 1). Give every device its own number before it goes on the robot. Number 63 is usually kept for messages to every device of that kind."],
      links: ["canaddr", "canwiki"] },
    can_heartbeat: { title: "The robot's heartbeat", short: "Every 20 ms the robot controller broadcasts a heartbeat that says enabled or not. A motor controller that misses it for 100 ms stops itself.",
      body: ["The universal heartbeat carries the match time and number, the alliance color, autonomous or teleop, and the one bit that matters most: whether motors may run.",
        "If it stops arriving - the robot program froze, the robot controller rebooted, or a CAN cable broke - each motor controller that stops hearing it acts as if the robot was disabled within a tenth of a second. A broken cable stops only the controllers past the break. That is a safety rule, and also why a cable fault looks like a motor that randomly stops.",
        "The tool's wiring map uses the same idea: a controller it stops hearing is drawn missing, and everything past one break in the chain goes missing together."],
      links: ["canaddr"] },
    can_load: { title: "CAN bus load", short: "1 Mbit/s carries about 7,000 full-size messages a second. Every controller's status messages add up; past about 80% busy, messages start arriving late.",
      body: ["Each SPARK sends its applied output every 10 ms, always, and its position and speed every 20 ms by default once the code has asked for them: roughly 150 messages a second, about 2% of the bus. Twenty SPARKs is about 40%. The Driver Station shows the bus's use as CAN utilization.",
        "When the bus is nearly full, arbitration makes the higher IDs wait: their data arrives late and jittery. Waiting is not an error. Errors come from the wires: a loose plug, a bad terminator, noise. A controller that sees too many goes <b>bus-off</b>: it stops talking for a moment, then rejoins. A busy bus makes a weak spot show sooner, which is why the load test runs it busy.",
        "The CAN load test runs the bus busy on purpose and counts errors. A measuring run speeds up just the motors it measures (to every 10 ms) and puts them back after."],
      links: ["candevs", "frccan"] },
    can_fd: { title: "CAN FD and more buses", short: "CAN FD sends the data part of a message faster and up to 64 bytes at a time. FD needs every device on that bus to speak FD.",
      body: ["CAN FD (flexible data rate) keeps the same arbitration as classic CAN, then switches to a faster bit rate for the data, and allows up to 64 bytes instead of 8. Every device on an FD bus must support FD.",
        "SystemCore, the 2027 robot controller, has five CAN buses of its own, each able to run FD, each with a terminator built in. For 2027, FIRST also allows CTRE's CANivore (an FD bus over USB) while SystemCore's FD support is tested. More buses split the load: the drivetrain on one, mechanisms on another.",
        "The wiring map supports several buses: each has a name, a cable color and its own two terminators."],
      links: ["canwiki", "candevs"] },

    // ---------------------------------------------------------------- the network and NetworkTables
    robot_network: { title: "The robot's network", short: "The radio makes a small network: the robot controller at 10.TE.AM.2 and the Driver Station, dashboards, coprocessors and this laptop on it.",
      body: ["Your team number sets the addresses: team 1745 is 10.17.45.x. The robot controller is at .2 (a roboRIO also answers to roboRIO-1745-FRC.local), the radio at .1, and the laptops get addresses from the radio.",
        "A laptop on the robot's network and the internet at once (Wi-Fi plus a cable, or a VPN) has to choose which network each message goes to. Get that wrong and the tool can't reach the robot, or the internet stops. Check the networks reads it all and says what to fix.",
        "Everything on this network talks with IP: the Driver Station's control packets, NetworkTables, camera streams and this tool."],
      links: ["netbasics", "netip", "frcradio"] },
    networktables: { title: "NetworkTables", short: "The robot's shared bulletin board: the robot code publishes named values, and every dashboard on the Driver Station laptop, a coprocessor, and this tool can read them.",
      body: ["It is <b>publish and subscribe</b>: a program that has something to say publishes it to a named <b>topic</b>; anything that wants it subscribes. Neither needs to know the other exists.",
        "The robot program is the <b>server</b>; everything else is a <b>client</b> that connects to it by team number: dashboards on the Driver Station laptop, programs on a coprocessor, this tool. (The Driver Station window itself doesn't show them.) Since 2023 it is version 4 (NT4), which runs over a WebSocket on port 5810.",
        "This tool is a NetworkTables client: the robot's Sloth Tune code publishes under /SlothTune (live readings, test results, gains) and the tool subscribes; the tool publishes its requests (start a test, the deadman, a gain change) and the robot subscribes to those."],
      links: ["ntintro", "ntpubsub", "ntnet"] },
    nt_topics: { title: "Topics and tables", short: "A topic is one named value with a fixed type, named like a file path: /SlothTune/Systems/Names. Tables are just the folders.",
      body: ["A topic's type never changes: boolean, integer, float or double, string, raw bytes, or an array of one of those. The name's slashes make a tree, the way folders hold files: /SlothTune holds Systems, which holds Names.",
        "An <b>entry</b> is a subscriber and a publisher on one topic together. Every value is stamped with the time it was published, in microseconds, so a reader can tell old news from new.",
        "Some topics are <i>persistent</i> (the server saves them to a file and restores them after a restart). Sloth Tune's gains are not: a live gain is lost at restart until it is saved into slothtune.json."],
      links: ["nttopics", "ntintro"] },
    nt_timing: { title: "How fresh a value is", short: "Values are batched and sent about every 100 ms unless the sender or the reader asks for faster; each carries the time it was published.",
      body: ["Sending every change instantly would flood the network, so NetworkTables collects changes and sends them in batches. A subscriber (a dashboard, this tool) can ask the robot to send faster, or to send every value rather than only the latest (sendAll).",
        "That is why the tool's tests record on the robot itself, a row every robot loop, and send the whole run afterwards: a 100 ms dashboard rate would miss everything a step response shows. The live graphs get the newest half second of rows each time, so none is missed.",
        "When something on a dashboard looks a little behind, that is usually why. AdvantageKit logs record every loop on the robot for the same reason."],
      links: ["ntpubsub", "ntnet"] },
    dashboards: { title: "Dashboards", short: "Elastic and AdvantageScope are NetworkTables clients: they draw whatever topics the robot publishes. (Shuffleboard, the older one, leaves WPILib in 2027.)",
      body: ["Elastic is the drive team's dashboard: big, simple widgets during a match. Sloth Tune's alerts and the battery line appear there.",
        "AdvantageScope is for engineers: graphs and 3D field views, live or from a log file afterwards (a WPILib or AdvantageKit log).",
        "This tool is a dashboard too, but it also reads the robot's code and files on this laptop, which is how it can say not only what a number is but what it should be."],
      links: ["elastic", "ascope", "ntintro"] },

    // ---------------------------------------------------------------- model-based tuning
    model_tuning: { title: "Measure, then compute", short: "Instead of guessing gains and trying again, measure how the mechanism answers known volts, fit its physics, and work the gains out from them.",
      body: ["Round-by-round tuning changes one gain, runs, looks, changes again: slow, and it can wander. Model-based tuning measures once: the robot drives the motor by voltage and records how the mechanism moves. From that it fits four numbers - friction (kS), back-EMF (kV), inertia (kA) and gravity (kG) - and every gain follows from them by math.",
        "Then it checks: a step test with the computed gains, compared with the step test it ran first on the gains it already had. It trims one setting (how hard to push), keeps the best, and puts the old gains back if the model can't beat them.",
        "This is what WPILib's SysId does, and what top teams publish; the tool runs it end to end and says at each step what it found."],
      links: ["sysid", "ff", "cefrc", "cefrcgh"] },
    system_id: { title: "The measuring run", short: "The mechanism's own control code is set aside (the robot program keeps running) and the tool drives the motor by voltage, recording how it moves: slow sweeps show friction and back-EMF, quick steps show inertia.",
      body: ["System identification means learning a system's equation from data. The mechanism's equation is <b>V = kS x direction + kV x speed + kA x acceleration + kG</b> (for an arm, kG x cos(angle)): give it known volts, record the speed and acceleration, and the numbers can be found.",
        "A slow sweep keeps acceleration near zero, so the volts show friction and back-EMF; a quick step makes acceleration large, so the volts show inertia. SysId calls these the quasistatic (slow) and dynamic (quick) tests. Gravity shows in both: going up an elevator needs kG extra volts; going down it gets kG for free.",
        "It runs on blocks with the deadman held, stays inside the mechanism's limits, slows it before each end, and stops on its own if the motor turns the wrong way, jams or goes too fast."],
      links: ["sysid", "ff", "cefrc"] },
    hold_band: { title: "The hold band", short: "Between the volts where it starts to move up and where it starts to move down, friction holds it still. The middle is gravity (kG); half the width is friction (kS).",
      body: ["The measuring run first finds this band with a seesaw: still, it raises the volts slowly; moving, it turns them back against the motion. Where motion starts from rest is an edge of the band. (Getting something moving can take a little more than keeping it moving, so this band can be a bit wider than the fitted kS says.)",
        "An arm's gravity changes with its angle (strongest level, none straight up), so its band moves as it turns. The first two sweeps, one each way at the same slow speed, map it everywhere: at each angle the average of the two is gravity, because friction and back-EMF push equally the opposite way each time.",
        "When the measuring run slows the arm before a limit, it uses that map. Past straight up an arm's gravity pulls the other way, and a run that didn't know would carry it into its stop."],
      links: ["ff"] },
    least_squares: { title: "Fitting the model (least squares)", short: "Hundreds of samples, a few unknowns: least squares finds the numbers that make the model's predictions closest to what was measured.",
      body: ["Each robot loop gives one equation: the speed next loop depends on the speed now, the volts, friction's direction and gravity. Least squares finds the one set of numbers that misses all of them by the least, adding up each miss squared - squared so misses above and below don't cancel, and big misses count most.",
        "R² of 99% means the model's guess of each next speed is very close to what was measured. The next speed is always close to this one, so R² runs high, and the bar is high too: below 98%, something the model leaves out (a spring, slack, a cable pulling) is in there; below 90%, the tool throws the run out.",
        "The robot changes the volts only once a loop (every 20 ms). So the tool takes speed from how far the mechanism moved during each loop, and lets the fit use the loop before's volts too. Taking speed across two loops would blur in the next loop's volts and make kA come out too big."],
      links: ["olswiki", "sysid", "cefrc"] },
    lqr: { title: "LQR: position gains from the model", short: "The linear-quadratic regulator picks the kP and kD that best balance two costs: how far off you'll accept being, and how many volts you'll spend fixing it.",
      body: ["Think of braking for a stop sign: too soft and you miss the line, too hard and you jolt everyone. You say what a miss costs and what effort costs, and LQR finds the gains that make the total least, using the model's own physics. 'Quadratic' means each miss is squared, so big misses count far more.",
        "Bryson's rule (SysId uses it too) turns two limits into those costs: the biggest miss you'd accept, and the most volts you'd spend. The tool says missing by 2% of the move is as bad as using 7 volts, and a speed error of a quarter of cruise counts too.",
        "It plans for the SPARK's own loop: 1000 times a second, seeing the mechanism about 2 ms late. Before trusting the gains, the tool runs the model with them (the delay and the SPARK's mode included); if that rings, it softens them a step at a time until it doesn't.",
        "One catch: the SPARK's D term acts on each encoder count at once. A NEO's sensor counts only 42 times a turn, so the full kD would pulse the motor hard at every count - a buzz you can hear. The tool measures the count from the measuring run, holds kD so one count kicks the output by at most a quarter, and softens kP to suit."],
      links: ["statespace", "lqrwiki", "cefrc", "cefrcgh"] },
    simc: { title: "SIMC: speed-loop gains", short: "Skogestad's rule for a speed loop: as quick as the speed reading's delay allows, and no quicker.",
      body: ["A speed loop can only react to what it reads, and a SPARK's speed reading is late (its filter). Skogestad's SIMC rule sets the loop's response time equal to that delay: kP = kA / (2 x delay). The integral time is the shorter of two: the mechanism's time constant (kA / kV, about how long it takes to get two-thirds of the way to a new speed) or 8 x the delay; kI is kP divided by it.",
        "Skogestad shows this is firm but safe: the gain could roughly triple before the loop would swing on its own. LQR, which SysId uses, gives a speed loop almost no gain once a real filter's delay is counted, so the tool uses SIMC for flywheels and rollers.",
        "An integral that strong would wind up over a whole spin-up and shoot far past the speed, so the tool also sets REV's <b>iZone</b>: the integral counts only within a tenth of the speed. And match code sets a shooter's speed at once, so it checks a jump straight to speed too, softening the gains until that overshoots by no more than 15%.",
        "The shorter the delay, the higher the gains it can use: that is why the <span class=\"term\" tabindex=\"0\" data-learn=\"velocity_filter\">speed filter</span> matters so much for a flywheel."],
      links: ["simc", "flywheel"] },
    spark_modes: { title: "Which gains a SPARK uses", short: "Each mode uses only some gains. Position: kP, kD, kS and gravity. Velocity: kP, kI, kS and kV. MAXMotion: kS, kV and kA (plus gravity for position) and its profile, on top of PID.",
      body: ["REV applies kV only where it knows a target speed (Velocity and MAXMotion), and kA only in MAXMotion, the one mode that plans an acceleration. In plain Position mode the SPARK gets only a position, so a measured kV does nothing there: kP has to carry the mechanism along. (Code that sends its own feedforward with each position can still use kV, but in the code, not the SPARK.)",
        "The robot tells the tool which mode the code last ran each SPARK in, and the tool computes only the gains that mode uses. A shooter that idles at zero output between shots still counts as Velocity once it has shot.",
        "One exception: in plain Position the SPARK has no target speed to point kS with. It is reported to push kS by the error's sign, and a kS pushed that way makes a mechanism dither or hunt around its target (CTRE warns the same). WPILib's and CTRE's advice: sign kS by a motion profile's speed - MAXMotion, or a profile on the robot controller (roboRIO or SystemCore) sending its feedforward. So in plain Position the tool sets kS to 0, and kP carries it.",
        "kP, kI and kD are in REV's units (output fraction per unit of error; kD and kI per 1 ms step). kS and kG are in volts. kV is volts per unit of speed and kA volts per unit of acceleration; REV's speed unit is RPM unless the code's velocity conversion factor changes it."],
      links: ["revunits", "mmpos", "revvel"] },
    maxmotion_limits: { title: "MAXMotion's limits from the model", short: "Plan with 80% of the battery the robot really has, then take 80% of the top speed that gives: the cruise speed and acceleration the motor can deliver, with the rest kept for feedback.",
      body: ["Top speed is where the volts run out: (volts - kS - kG) / kV. The tool plans with 80% of the battery measured under load, then takes 80% of that speed as cruise.",
        "Acceleration is limited twice: by the volts left at cruise, and by the current limit (a motor at its limit can only push so hard). The smaller wins, less 20%.",
        "A short move speeds up then slows down at once - a triangle on a speed-time graph - so cruise is capped at the top speed a triangle reaches over a typical move."],
      links: ["mmpos", "trap"] },
    voltage_compensation: { title: "Voltage compensation", short: "The SPARK scales its output so the motor gets the same volts whether the battery is fresh or tired, as long as the battery stays above the compensation voltage (REV: nominal voltage).",
      body: ["Without it, the same output fraction gives fewer volts on a tired battery: a shooter tuned on a fresh battery shoots short at the end of a match. A team on Chief Delphi fixed exactly that by turning compensation on.",
        "The tool sets it 0.3 to 0.8 V under the lowest battery voltage the measuring run saw, rounded to a half volt, never above 12 V or below 9 V. A match pulls harder than one mechanism on blocks, so near full output late in a match it can still fall short.",
        "With it on, the gains mean the same thing on every battery, so a tune done on Saturday still holds on Sunday."],
      links: ["vcompstory", "revunits"] },
    check_runs: { title: "Check runs: how hard to push", short: "The model leaves one choice open: how hard to push. Check runs try softer and harder and keep whichever does best, never past half or double.",
      body: ["First a step test with the gains it already has: the baseline the model must beat. Then the model's gains, judged the same way (overshoot, settling, how far it was left behind). The panel's How hard column shows each: 1.00x is the model's own, 0.6x softer, 1.6x harder.",
        "If the check overshot or rang more than the model said, or buzzed while it held still (its output jumping about while the position didn't move), it goes softer; if it was clean, harder; then once between the two best. Four checks at most.",
        "It ends on the best. If that doesn't beat the baseline, or still rings, it puts back every gain it started with and says why: the model and the mechanism disagree, and a person should look."],
      links: ["sysid"] },
    sim_vs_real: { title: "Why the simulator's gains differ", short: "REVLib's simulated SPARK runs its loop once per 20 ms robot loop instead of every millisecond and applies kD far harder than a real one, so the simulator gets softer, kP-only gains.",
      body: ["On a real SPARK the position loop runs 1000 times a second. In the simulator it runs once per robot loop, so it sees the mechanism a whole 20 ms late, and gains built for 1 ms ring. The tool computes for the simulator's real period.",
        "Its simulated encoder also glitches when the output jumps, which makes the inertia it measures come out large, and any kD made the Examples elevator misbehave. So the simulator's gains use kP alone.",
        "Use the simulator to practice the steps; the numbers that count come from the robot."],
      links: ["sysid"] },
  };

  // Phrases in plain text that link to a lesson, longest first. Used for guide steps and advice.
  const TERMS = [
    ["AWG", "wire_gauge"], ["Powerpole", "crimp_powerpole"], ["SB50", "crimp_sb50"], ["Anderson connector", "crimp_sb50"], ["Molex", "crimp_molex_sl"],
    ["Hall sensor", "hall_effect"], ["quadrature", "encoder_quadrature"], ["Coriolis", "gyro_mems"], ["accelerometer", "accelerometer"], ["pull-up", "pull_resistor"],
    ["pull-down", "pull_resistor"], ["debounc", "contact_bounce"], ["bounce", "contact_bounce"], ["limit switch", "limit_switch"],
    ["break-beam", "break_beam"], ["beam break", "break_beam"], ["time-of-flight", "time_of_flight"], ["pole pair", "pole_pairs"],
    ["brushless", "brushed_brushless"], ["outrunner", "inrunner_outrunner"], ["free speed", "motor_basics"], ["stall torque", "motor_basics"],
    ["static friction", "kS"], ["feedforward", "feedforward"], ["dead time", "dead_time"], ["rise time", "rise_time"],
    ["overshoot", "overshoot"], ["settling", "settling_time"], ["left over", "steady_state_error"], ["stops short", "steady_state_error"],
    ["steady-state error", "steady_state_error"], ["oscillat", "oscillation"], ["ringing", "oscillation"], ["saturat", "saturation"], ["flat out", "saturation"],
    ["current limit", "current_limit"], ["ramp rate", "ramp_rate"], ["windup", "integral_windup"], ["wind up", "integral_windup"], ["IZone", "iZone"],
    ["absolute encoder", "absolute_encoder"], ["motor encoder", "motor_encoder"], ["offsets", "offset"], ["offset", "offset"], ["inverted", "inversion"],
    ["inversion", "inversion"], ["gear ratio", "gear_ratio"], ["gearing", "gear_ratio"], ["speed filter", "velocity_filter"], ["velocity filter", "velocity_filter"],
    ["auto-sync", "encoder_sync"], ["deadman", "deadman"], ["on blocks", "environment"], ["carpet", "carpet_scrub"], ["setpoint", "setpoint"],
    ["kP", "kP"], ["kD", "kD"], ["kI", "kI"], ["kS", "kS"], ["kV", "kV"], ["kA", "kA"], ["kG", "kG"], ["kCos", "kG"], ["PID", "feedback"], ["battery", "voltage_sag"],
    ["motion profile", "motion_profile"], ["trapezoid", "trapezoid_profile"], ["MAXMotion", "maxmotion_position"], ["heat estimate", "heat_estimate"],
    ["derate", "derate"], ["stall", "stall"], ["bevel gear", "bevel_gear"], ["straight-edge", "straight_edge"],
    ["coast", "coast_mode"], ["redeploy", "redeploy"], ["slip current", "slip_current"], ["traction", "traction"], ["slip", "traction"], ["CAN bus", "can_bus"],
    ["terminator", "can_termination"], ["termination", "can_termination"], ["power leads", "power_path"], ["PDH port", "power_path"], ["battery side", "battery_current"], ["camera mount", "camera_mount"], ["moment of inertia", "moment_of_inertia"], ["field survey", "field_survey"], ["wiggle test", "wiggle_test"], ["keep the wheels still", "hold_still"], ["hand check", "hand_check"],
    ["system identification", "system_id"], ["measuring run", "system_id"], ["least squares", "least_squares"], ["LQR", "lqr"], ["SIMC", "simc"],
    ["voltage compensation", "voltage_compensation"], ["hold band", "hold_band"], ["NetworkTables", "networktables"], ["arbitration", "can_arbitration"],
    ["CAN FD", "can_fd"], ["bus load", "can_load"], ["dashboard", "dashboards"],
  ];

  // ---------------------------------------------------------------- the hover card
  const tip = document.createElement("div");
  tip.className = "learn-tip";
  tip.setAttribute("role", "tooltip");
  tip.id = "learn-tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  let hideTimer = null, anchor = null;

  // A lesson's figures (drawings, each {src, alt, caption}): full size in the lesson; the first, small,
  // on a hover card, so a tip about a crimp shows the crimp.
  const figuresOf = l => (l && (l.figures || (l.figure ? [l.figure] : []))) || [];
  // The motor and sensor drawings animate; each holds still on its own when the computer is set to
  // reduce motion (Chromium passes the system setting into an SVG shown with <img>).
  const figEl = (f, cls) => `<img class="${cls}" src="${esc(f.src)}" alt="${esc(f.alt)}" loading="lazy">`;
  const thumb = l => {
    const f = figuresOf(l)[0];
    return f ? figEl(f, "learn-thumb") : "";
  };
  function card(key, extra) {
    const l = L[key];
    if (!l) return extra ? `<div>${esc(extra)}</div>` : "";
    return `${extra ? `<div class="learn-extra">${esc(extra)}</div>` : ""}
      <div class="learn-title">${esc(l.title)}</div><div>${esc(l.short)}</div>${thumb(l)}
      <button class="learn-more" data-lesson="${esc(key)}">Lesson →</button>`;
  }

  // A control's tip: what it does, how it works, and its lesson when there is one. "now" is a
  // live line some controls add (data-tip-now), such as the battery's last measurement.
  function tipCard(t, now) {
    const [what, how, key] = t;
    return `${now ? `<div class="learn-extra">${esc(now)}</div>` : ""}<div class="learn-what">${esc(what)}</div>
      ${how ? `<div class="learn-how">${esc(how)}</div>` : ""}${key && L[key] ? thumb(L[key]) : ""}
      ${key && L[key] ? `<button class="learn-more" data-lesson="${esc(key)}">Lesson: ${esc(L[key].title)} →</button>` : ""}`;
  }
  const TIP_SEL = "[data-learn], [data-tip]";
  const tipOf = el => (typeof TIPS !== "undefined" && el.dataset.tip && TIPS[el.dataset.tip]) || null;

  // Below the thing it describes, or above it when there's no room below: never over it, or the
  // card would take the click meant for the control (it flipped above the control's bottom edge).
  function place(x, below, above = below) {
    tip.style.left = "0px"; tip.style.top = "0px";
    const r = tip.getBoundingClientRect();
    const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    let left = Math.min(Math.max(8, x - r.width / 2), vw - r.width - 8);
    let top = below + 14;
    if (top + r.height > vh - 8) top = Math.max(8, above - r.height - 14);
    tip.style.left = left + window.scrollX + "px";
    tip.style.top = top + window.scrollY + "px";
  }

  function showFor(el) {
    const t = tipOf(el), key = el.dataset.learn;
    if (!t && !L[key]) return;
    clearTimeout(hideTimer);
    anchor = el;
    tip.innerHTML = t ? tipCard(t, el.dataset.tipNow) : card(key, el.dataset.learnText);
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    place(r.left + r.width / 2, r.bottom, r.top);
    el.setAttribute("aria-describedby", "learn-tip");
  }

  // For things drawn on a canvas: a lesson key plus the specific sentence about this moment.
  function showAt(key, clientX, clientY, extra) {
    clearTimeout(hideTimer);
    anchor = null;
    tip.innerHTML = card(key, extra);
    tip.hidden = false;
    place(clientX, clientY);
  }

  function hideSoon() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      tip.hidden = true;
      if (anchor) anchor.removeAttribute("aria-describedby");
      anchor = null;
    }, 220);
  }
  function hide() { clearTimeout(hideTimer); tip.hidden = true; anchor = null; }

  const touch = () => window.matchMedia && matchMedia("(hover: none)").matches;
  // With a mouse, the card lets clicks through to the control beneath it (style.css), so a card that
  // sits over the next control never takes its click. While the pointer is inside the card, though,
  // the card stays: it doesn't switch to the control beneath, so its lesson link can be reached.
  const inCard = (x, y) => {
    if (tip.hidden) return false;
    const r = tip.getBoundingClientRect();
    return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  };
  document.addEventListener("mouseover", e => {
    if (!touch() && inCard(e.clientX, e.clientY)) { clearTimeout(hideTimer); return; }
    const el = e.target.closest && e.target.closest(TIP_SEL);
    if (el) { if (el !== anchor) showFor(el); else clearTimeout(hideTimer); }
    else if (!e.target.closest || !e.target.closest(".learn-tip")) { if (anchor) hideSoon(); }
  });
  // Keyboard focus shows the card; a mouse click on a button or tab does not (it would sit over
  // the page until something else took focus). Text fields always count: you are about to type.
  document.addEventListener("focusin", e => {
    const el = e.target.closest && e.target.closest(TIP_SEL);
    if (el && (e.target.matches(":focus-visible") || e.target.matches("input:not([type=checkbox]), textarea"))) showFor(el);
  });
  document.addEventListener("mousedown", e => {
    if (anchor && e.target.closest && e.target.closest(TIP_SEL) === anchor) hide();
    // A click through the card, onto the control beneath, is done with the card.
    else if (!touch() && inCard(e.clientX, e.clientY) && !(e.target.closest && e.target.closest(".learn-tip"))) hide();
  });
  document.addEventListener("focusout", e => { if (e.target.closest && e.target.closest(TIP_SEL)) hideSoon(); });
  tip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  tip.addEventListener("mouseleave", hideSoon);
  // Esc also aborts any running test (app.js); that is deliberate, since stopping is always safe.
  document.addEventListener("keydown", e => { if (e.key === "Escape") { hide(); closeDrawer(); } });
  document.addEventListener("click", e => {
    const more = e.target.closest && e.target.closest("[data-lesson]");
    if (more) { e.preventDefault(); hide(); open(more.dataset.lesson); return; }
    const el = e.target.closest && e.target.closest(TIP_SEL);
    if (!el) { if (!e.target.closest || !e.target.closest(".learn-tip")) hide(); return; }
    // Inputs and buttons keep their job; their tip shows on hover, on focus, and in Explain mode.
    if (el.matches("input, select, button, textarea") || el.closest("button, label")) return;
    // A tap on a touch screen shows the card (it has the lesson link); a click on a term opens the lesson.
    if (touch() || !L[el.dataset.learn]) { showFor(el); return; }
    hide(); open(el.dataset.learn);
  });

  // ---------------------------------------------------------------- the lesson drawer
  const drawer = document.createElement("aside");
  drawer.className = "learn-drawer";
  drawer.setAttribute("aria-label", "Control theory lessons");
  drawer.hidden = true;
  document.body.appendChild(drawer);
  // Expand: the lesson takes most of the screen (its drawings at full size); Shrink puts it back at
  // the side. Remembered for this viewer; Esc or the close button hides it either way.
  try { drawer.classList.toggle("wide", localStorage.getItem("slothtune.learn.wide") === "on"); } catch (e) { /* storage blocked */ }
  const wideBtn = () => {
    const on = drawer.classList.contains("wide");
    return `<button class="btn small" data-lwide="1" aria-pressed="${on}">${on ? "Shrink" : "Expand"}</button>`;
  };

  function lessonHtml(key) {
    const l = L[key];
    const unit = UNITS.find(u => u.lessons.includes(key));
    const idx = unit ? unit.lessons.indexOf(key) : -1;
    const next = unit && unit.lessons[idx + 1];
    return `<div class="row" style="justify-content:space-between">
        <button class="btn small" data-lindex="1">← All lessons</button>
        <span class="row">${wideBtn()}<button class="btn small" data-lclose="1" aria-label="Close lessons">✕</button></span></div>
      ${unit ? `<div class="muted small">${esc(unit.title)}</div>` : ""}
      <h2>${esc(l.title)}</h2>
      <p class="learn-short">${esc(l.short)}</p>
      ${figuresOf(l).map(f => `<figure class="learn-fig"><a href="${esc(f.src)}" target="_blank" rel="noopener">${figEl(f, "learn-fig-art")}</a>
        ${f.caption ? `<figcaption class="small muted">${esc(f.caption)}</figcaption>` : ""}</figure>`).join("")}
      ${(l.body || []).map(p => `<p>${p}</p>`).join("")}
      ${l.see ? `<div class="callout"><b>On the graphs:</b> ${esc(l.see)}</div>` : ""}
      ${l.try ? `<div class="callout"><b>Try it:</b> ${esc(l.try)}</div>` : ""}
      ${(l.links || []).length ? `<div class="small"><b>Read more</b><ul>${l.links.map(k => `<li><a href="${LINK[k][0]}" target="_blank" rel="noopener">${esc(LINK[k][1])}</a></li>`).join("")}</ul></div>` : ""}
      ${l.credit ? `<p class="small muted">${esc(l.credit)}</p>` : ""}
      ${next ? `<button class="btn" data-lesson="${esc(next)}">Next: ${esc(L[next].title)} →</button>` : ""}
      <p class="small muted">Esc closes this, and also stops any running test.</p>`;
  }

  function indexHtml() {
    return `<div class="row" style="justify-content:space-between"><h2>Lessons</h2>
        <span class="row">${wideBtn()}<button class="btn small" data-lclose="1" aria-label="Close lessons">✕</button></span></div>
      <p class="small muted">From the hardware up: motors, sensors and wiring first, then the network, driving and testing safely, calibrating, and then control - feedforward before feedback, as WPILib teaches it. Every underlined word in the tool opens one of these.</p>
      ${UNITS.map(u => `<div class="learn-unit ${u.locked && !secondOrderReady() ? "locked" : ""}"><h3>${esc(u.title)}</h3>
        ${u.locked && !secondOrderReady() ? `<p class="small muted">Unlocks once steering and drive pass their first-order targets in the Guide. You can still read ahead.</p>` : ""}
        <div class="learn-list">${u.lessons.map(k => `<button class="btn small" data-lesson="${k}">${esc(L[k].title)}</button>`).join("")}</div></div>`).join("")}`;
  }

  function secondOrderReady() { return typeof Guide !== "undefined" && !!Guide.firstOrderDone && Guide.firstOrderDone(); }

  let opener = null;
  function open(key) {
    if (drawer.hidden) opener = document.activeElement;
    drawer.innerHTML = key && L[key] ? lessonHtml(key) : indexHtml();
    drawer.hidden = false;
    drawer.scrollTop = 0;
    const first = drawer.querySelector("h2");
    if (first) { first.tabIndex = -1; first.focus(); }
  }
  function closeDrawer() {
    if (drawer.hidden) return;
    drawer.hidden = true;
    if (opener && document.contains(opener)) opener.focus();
    opener = null;
  }
  drawer.addEventListener("click", e => {
    if (e.target.closest("[data-lclose]")) closeDrawer();
    else if (e.target.closest("[data-lindex]")) open(null);
    else if (e.target.closest("[data-lwide]")) {
      const on = !drawer.classList.contains("wide");
      drawer.classList.toggle("wide", on);
      try { localStorage.setItem("slothtune.learn.wide", on ? "on" : "off"); } catch (err) { /* storage blocked */ }
      $$("[data-lwide]", drawer).forEach(b => { b.textContent = on ? "Shrink" : "Expand"; b.setAttribute("aria-pressed", String(on)); });
    }
  });

  // ---------------------------------------------------------------- helpers for other tabs
  // Escapes plain text and underlines the first mention of each known term.
  function link(text, max = 4) {
    let html = esc(text);
    const used = new Set();
    let count = 0;
    for (const [phrase, key] of TERMS) {
      if (count >= max || used.has(key) || !L[key]) continue;
      const re = new RegExp(`(^|[^\\w>])(${phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\w*)`, phrase.length <= 3 ? "" : "i");
      const m = re.exec(html);
      if (!m) continue;
      // Not inside a tag we already inserted.
      const before = html.slice(0, m.index);
      if ((before.match(/<span/g) || []).length !== (before.match(/<\/span>/g) || []).length) continue;
      const at = m.index + m[1].length;
      html = html.slice(0, at) + `<span class="term" tabindex="0" data-learn="${key}">${m[2]}</span>` + html.slice(at + m[2].length);
      used.add(key); count++;
    }
    return html;
  }
  const term = (key, text) => `<span class="term" tabindex="0" data-learn="${key}">${esc(text || (L[key] && L[key].title) || key)}</span>`;
  // A lesson chip shows the lesson's one-line answer on hover and opens the lesson on a click.
  const chips = keys => keys.filter(k => L[k]).map(k => `<button class="chip learn-chip" data-lesson="${k}" data-learn="${k}">${esc(L[k].title)}</button>`).join("");

  // ---------------------------------------------------------------- Explain mode
  // Prints the first sentence of each control's tip under it, so a new student can read the whole
  // screen without hovering. Off by default, so every section fits one laptop screen; the tips
  // still show on hover, focus and tap. The header stays compact either way.
  const main = document.querySelector("main");
  const OBS = { childList: true, subtree: true };
  const INSIDE = new Set(["TH", "H2", "H3", "LABEL", "SUMMARY", "LEGEND"]);
  let explainOn = false, seq = 0;
  try { explainOn = localStorage.getItem("slothtune.explain") === "on"; } catch (e) { /* storage blocked */ }

  function line(text) {
    const s = document.createElement("small");
    s.className = "tipline";
    s.id = "tl-" + (++seq);
    s.innerHTML = text;
    return s;
  }
  const isLine = n => !!(n && n.classList && n.classList.contains("tipline"));
  function annotate() {
    const scope = [main, document.getElementById("modal")].filter(Boolean);
    for (const el of scope.flatMap(r => [...r.querySelectorAll("[data-tip]")])) {
      // Drawings, segmented pickers and hover-only tips (data-quiet) get no printed line.
      if (el.hasAttribute("data-quiet") || el.closest("svg, .seg, .tipline")) continue;
      const t = tipOf(el);
      if (!t) continue;
      const inside = INSIDE.has(el.tagName) || (el.parentElement && el.parentElement.classList.contains("kv"));
      if (inside ? isLine(el.lastElementChild) : isLine(el.nextElementSibling)) continue;
      const s = line(esc(t[0]));
      if (inside) el.appendChild(s); else el.after(s);
      el.setAttribute("aria-describedby", [el.getAttribute("aria-describedby"), s.id].filter(Boolean).join(" "));
    }
    // A segmented picker gets one line listing every choice.
    for (const seg of main.querySelectorAll(".seg")) {
      if (isLine(seg.nextElementSibling)) continue;
      const items = $$("[data-tip]", seg).map(b => [b.textContent.trim(), tipOf(b)]).filter(([, t]) => t);
      if (items.length) seg.after(line(items.map(([n, t]) => `<b>${esc(n)}:</b> ${esc(t[0])}`).join("<br>")));
    }
  }
  // Explain covers dialogs too: "Where is the robot?" is a safety dialog.
  const modal = document.getElementById("modal");
  const observe = () => { mo.observe(main, OBS); if (modal) mo.observe(modal, OBS); };
  const mo = new MutationObserver(() => { mo.disconnect(); annotate(); observe(); });
  function setExplain(on) {
    explainOn = on;
    try { localStorage.setItem("slothtune.explain", on ? "on" : "off"); } catch (e) { /* storage blocked */ }
    document.body.classList.toggle("explain", on);
    const b = document.getElementById("explain");
    if (b) { b.setAttribute("aria-pressed", String(on)); b.textContent = on ? "Explain: on" : "Explain: off"; }
    mo.disconnect();
    if (on) { annotate(); observe(); }
    else {
      $$(".tipline", main).forEach(s => s.remove());
      $$("[aria-describedby*='tl-']", main).forEach(e => {
        const keep = e.getAttribute("aria-describedby").split(/\s+/).filter(x => !x.startsWith("tl-")).join(" ");
        if (keep) e.setAttribute("aria-describedby", keep); else e.removeAttribute("aria-describedby");
      });
    }
  }
  const explainBtn = document.getElementById("explain");
  if (explainBtn) explainBtn.onclick = () => setExplain(!explainOn);
  setExplain(explainOn);

  return { L, UNITS, open, showAt, hide, link, term, chips, setExplain };
})();
