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
  };

  // The course, in teaching order. "units" in a lesson tie it to the numbers the tool shows.
  const UNITS = [
    { id: "basics", title: "1. What a control loop is", lessons: ["control_loop", "setpoint", "measurement", "error", "control_effort"] },
    { id: "ff", title: "2. Feedforward: answer before the question", lessons: ["feedforward", "kS", "kV", "kA"] },
    { id: "fb", title: "3. Feedback: fix what feedforward missed", lessons: ["feedback", "kP", "kD", "kI", "integral_windup", "iZone", "rev_units"] },
    { id: "read", title: "4. Reading a step response", lessons: ["step_response", "dead_time", "rise_time", "overshoot", "settling_time", "steady_state_error", "oscillation"] },
    { id: "limits", title: "5. When the motor can't do what it's told", lessons: ["saturation", "current_limit", "traction", "voltage_sag", "ramp_rate"] },
    { id: "sensors", title: "6. Sensors: what the controller can see", lessons: ["quantization", "velocity_filter", "motor_encoder", "absolute_encoder", "offset", "inversion", "gear_ratio", "encoder_sync"] },
    { id: "calibrate", title: "7. Calibrating: what each step does and why", lessons: ["hand_check", "coast_mode", "bevel_gear", "straight_edge", "hold_still", "redeploy", "slip_current", "moment_of_inertia", "camera_mount", "field_survey"] },
    { id: "swerve", title: "8. Swerve-specific", lessons: ["swerve_module", "carpet_scrub", "module_flip", "environment", "deadman", "what_if"] },
    { id: "motors", title: "9. Keeping motors alive", lessons: ["heat_estimate", "derate", "stall", "thermal_override"] },
    { id: "wiring", title: "10. Wiring: CAN and power", lessons: ["can_bus", "can_termination", "power_path", "battery_current", "wiggle_test"] },
    { id: "profile", title: "11. Second order: motion profiles (after first-order tuning works)", locked: true,
      lessons: ["motion_profile", "trapezoid_profile", "cruise_velocity", "max_acceleration", "ff_uses_setpoint", "maxmotion_position", "maxmotion_velocity", "allowed_profile_error", "profiled_pid"] },
  ];

  const L = {
    control_loop: { title: "A control loop", short: "Measure, compare with what you want, push to close the gap, repeat - a thousand times a second on a SPARK.",
      body: [
        "Every motor here is controlled the same way. You say what you want (the <b>setpoint</b>). A sensor says what is happening (the <b>measurement</b>). The difference is the <b>error</b>. The controller turns the error, plus what it already knows about the motor, into a voltage (the <b>control effort</b>).",
        "Then it measures again and does it all again. On a SPARK MAX the steering loop runs 1000 times a second inside the motor controller, which is why it can be quick and precise.",
        "Two halves do the work. <b>Feedforward</b> uses physics to guess the voltage before any error shows up. <b>Feedback</b> (PID) fixes whatever error is left. WPILib teaches feedforward first, and so does this tool."],
      links: ["pid", "ff"] },
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
      see: "On the drive graphs, the gray FF line carries most of the voltage while holding a speed.", links: ["ff", "combine", "flywheel"] },
    kS: { title: "kS - static friction", short: "Volts it takes just to get the mechanism moving. Below kS nothing happens.",
      body: ["Bearings, gears and carpet grip all resist the start of motion. kS is the voltage that just overcomes them, in volts. It points the way you want to go and does not depend on speed.",
        "A module needing much more kS than the others is binding: a rubbing wheel, debris, or a misaligned pinion."], links: ["ff"] },
    kV: { title: "kV - volts per speed", short: "Extra volts for each m/s of speed, mostly the motor's back-EMF. kV x speed is what it takes to hold a speed.",
      body: ["A spinning motor is also a generator, pushing back against the battery (back-EMF). To hold a speed you must out-push it, and the push-back grows in a straight line with speed. kV is that slope, in volts per m/s.",
        "Because the measured speed comes from the motor's own encoder, a wrong gear ratio cancels out of kV. What changes kV is the motor itself - a different motor fitted, or one whose magnets were weakened by heat."], links: ["ff"] },
    kA: { title: "kA - volts per acceleration", short: "Extra volts to speed up, for each m/s² of acceleration. It reflects how heavy the robot is.",
      body: ["Speeding up a robot takes force, and force takes current, and current takes voltage. kA is in volts per m/s². On blocks it is tiny (just a wheel); on the floor it carries a quarter of the robot.",
        "YAGSL's module loop does not use kA today, but measuring it tells you how hard the robot can accelerate."], links: ["ff"] },

    feedback: { title: "Feedback (PID)", short: "Measures the error and pushes to shrink it. It fixes what feedforward got wrong - bumps, friction, wear.",
      body: ["Feedback looks at the error and responds. Its three classic terms are P, I and D. WPILib's one-line summary: P drives the position error to zero, D drives the velocity error to zero, and I drives the accumulated error to zero.",
        "Feedback alone works, but it only pushes once something is already wrong. With good feedforward, feedback can stay gentle - which means less noise, less buzzing, less heat."], links: ["pid", "combine"] },
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
      body: ["kP: duty cycle per unit of error (degrees for steering, m/s for drive). Multiply by battery volts to get volts.",
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
        "Fixes, in order: a little more kP; on drive, measure the feedforward; last, a tiny kI with an IZone. Each degree of steering error is about 1.7 cm of drift per meter."], links: ["issues"] },
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
    voltage_sag: { title: "Voltage sag", short: "The battery voltage drops when lots of current flows, so the same duty cycle gives fewer volts.",
      body: ["A tired battery or a robot drawing hard (all four drive motors accelerating) can sag below 10 V. Feedforward in volts compensates; WPILib recommends setVoltage() for that reason. Tests refuse to start on a low battery because every number would change."], links: ["issues", "combine"] },
    ramp_rate: { title: "Ramp rate", short: "Limits how quickly the output can change. In YAGSL it also slows every correction the closed loop makes.",
      body: ["A ramp of 0.25 s means 0 to full output takes a quarter second. For drive it can smooth starts; for steering it adds pure lag to every correction, which hurts. Usually 0 for steering."] },

    quantization: { title: "Quantization", short: "A sensor counts in steps. A NEO's built-in sensor has 42 counts per turn, so speeds and small moves look jumpy.",
      body: ["The steering motor's hall sensor gives 42 counts per motor turn; through a 46.42:1 gearbox that is about 0.18° of module angle per count. Fine for position. For speed it is coarse, so the SPARK averages - which adds delay (see the speed filter).",
        "A high kP times a jumpy measurement makes a buzz."] },
    velocity_filter: { title: "Speed filter", short: "The SPARK averages encoder counts over a time window to get a smooth speed. Smoother means later.",
      body: ["Speed is counts per time. Over 1 ms a NEO makes about one count, so the SPARK counts over a window (32 ms by default) and averages several readings. The result is smooth but up to tens of ms late, and a late measurement limits drive kP. A shorter window is quicker and noisier: the drive tests show the trade."] },
    motor_encoder: { title: "Motor encoder", short: "The sensor inside the steering motor. Quick and fine, but it only knows how far it turned since power-on.",
      body: ["YAGSL's steering loop uses it by default and sets it from the absolute encoder at boot. If the gear ratio is wrong or a pinion slips, it drifts from the truth; encoder auto-sync re-aligns it when the module is still."] },
    absolute_encoder: { title: "Absolute encoder", short: "The sensor on the module itself: knows the real angle at power-on, every time. Slower and coarser than the motor encoder.",
      body: ["On MAXSwerve it is the through-bore encoder on the steering axle. It is what offsets are measured against, and the truth the motor encoder is checked against."] },
    offset: { title: "Offset", short: "The absolute encoder reading when the wheel points straight ahead. One degree wrong is about 1.7 cm of drift per meter.",
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
    straight_edge: { title: "Why a straight-edge", short: "Eyes are good to 2-3°, which is 3-5 cm of drift per meter. A straight-edge across a pair of wheels gets well under a degree.",
      body: ["One degree of offset error is about 1.7 cm of sideways drift for every meter the robot drives. A level or a piece of extrusion held against both wheels of the front pair, then the back pair, lines them up far better than eyes can."] },
    hold_still: { title: "Why hold still", short: "The capture averages a few seconds of readings and checks they agree. A wheel that moved gives a blurred average, so it asks again.",
      body: ["Averaging removes the encoder's last-bit flicker. Checking the spread catches a bumped wheel. Both make the offset the real position, not a moment's guess."] },
    redeploy: { title: "Why redeploy", short: "Offsets and gains live in JSON files the robot reads once, at startup. Changing the files does nothing until the code is deployed and restarted.",
      body: ["The tool writes the robot project's files on the laptop. Deploying copies them to the robot; the robot reads them when its code starts. That is also why 'Apply live' changes vanish at the next restart: only the files are permanent - and the commit makes them the team's."] },

    slip_current: { title: "Slip current", short: "The drive current at which a wheel breaks loose. The drive current limit belongs just below it - measured on your carpet, not guessed.",
      body: ["Motor current makes torque, torque makes the wheel push. So 'the push where the wheel slips' is a current, and the drive current limit can be set right under it.",
        "The test: a bumper flat against a wall so the robot cannot move, then a slowly rising push. While the wheels grip, they stay still and the current climbs. The moment a wheel slips, its encoder speed jumps. The highest current before that is its breakaway current, and that wheel is cut at once to spare the tread.",
        "The limit is set to 90% of the weakest corner: carpets differ between venues and tread wears. It never goes above the team's policy for the motor. A datasheet-only limit like 80 A on a 55 kg robot is far above where its wheels slip - all that extra current only spins them."] },

    swerve_module: { title: "Swerve module", short: "Two loops per corner: steering (an angle) and drive (a speed). Eight loops for the robot.",
      body: ["The steering loop is a position loop, like WPILib's turret tutorial. The drive loop is a velocity loop, like its flywheel tutorial. Tune steering first: a drive loop can't be judged while the wheel points the wrong way."], links: ["turret", "flywheel"] },
    carpet_scrub: { title: "Carpet scrub", short: "On carpet a standing wheel grips while it turns, so steering needs far more push near the target than on blocks.",
      body: ["Turning a wheel in place twists its tread against the carpet. That friction is much larger than in the air, so gains tuned on blocks usually stop a few degrees short on the floor. Always finish steering on the floor."] },
    module_flip: { title: "Module optimization", short: "A wheel never turns more than 90°; past that it turns the short way and drives backwards instead.",
      body: ["Pointing 170° the other way is the same as pointing 10° and driving in reverse. YAGSL does this automatically, so steering never needs to move far."] },
    environment: { title: "Where the robot is", short: "Blocks: wheels spin, robot stays put. Field: it really drives. Sim: the computer. The tool's safety rules change with it.",
      body: ["On blocks the gyro and cameras must NOT see motion - if they do, the robot is not on blocks and the test stops. On the field, a deadman must be held, a space budget is enforced, and an impact stops everything."] },
    deadman: { title: "Deadman", short: "Hold it and the robot may move; let go and it stops. Held by whoever is watching the robot, never the laptop typist.",
      body: ["On the field every moving test needs it held: SPACE on the laptop, or the tester's controller bumper."] },
    what_if: { title: "The 'what if' prediction", short: "A small model learned from your own run, re-run with new gains. Good for direction and rough size; the robot has the final word.",
      body: ["The tool fits kS, kV and kA to the step you ran, then replays that run on the model with the same gains. How closely the replay matches tells you how far to trust the prediction.",
        "Then it runs the same setpoints with your new gains, using the SPARK's own controller rules. It leaves out backlash, battery sag and grip changes, so treat a big change as a hint and run it for real."] },

    heat_estimate: { title: "Heat estimate", short: "The guard's estimate of how hot the windings are, from the current. The only warning fast enough for a NEO 550.",
      body: ["Heat in a motor comes from current squared. The guard integrates it with a model fitted to REV's own burn-out tests. The temperature sensor on a NEO 550 sits outside the windings and lags them by tens of seconds - REV saw one die at 40 A while reading about 40 °C."] },
    derate: { title: "Derate", short: "The guard halves a hot motor's current limit so it can cool while still working.",
      body: ["Half the current is a quarter of the heat. The motor keeps working, slower, until it cools 10 degrees (or 10 points) below the line. Nothing is saved to the controller's flash."] },
    stall: { title: "Stall", short: "At the current limit but not turning: a jam, or pushing into a hard stop. All heat, no work.",
      body: ["A stalled motor turns all its power into heat. The stall timer warns at 3 s, derates, and cuts it after its limit. Drive motors are exempt: they stall in every pushing match, and the heat estimate guards them."] },
    thermal_override: { title: "Thermal override", short: "For the end of a match: hold a heat shutoff at half current for up to 20 s. Never lifts a stall cut.",
      body: ["Sometimes losing the motor costs more than the motor. The override holds a heat SHUTOFF at DERATE instead, for at most 20 s, and never past a sensor 10 °C over shutoff or a 95% heat estimate."] },

    can_bus: { title: "The CAN bus", short: "One pair of twisted wires (yellow CAN-H, green CAN-L) daisy-chained through every controller. Every device hears every message.",
      body: ["Each controller has a CAN ID and two CAN connections joined inside it, so the cable passes straight through - even when the controller has no power. The chain runs from the roboRIO to the far end, usually the PDH.",
        "That pass-through is the key to finding faults. One device missing while its neighbors are heard means that device (its power, or the controller). Everything past one point missing together means the cable or a plug at that point.",
        "CAN has no idea of position, so the order along the cable can't be read from the robot: someone checks it by eye once, and the map remembers it."] },
    can_termination: { title: "CAN termination", short: "A 120 ohm resistor at each end of the CAN chain stops signals echoing back. Exactly two: about 60 ohms measured across the bus, power off.",
      body: ["A fast signal reaching the open end of a wire bounces back and garbles the next bits. A 120 ohm terminator at each end soaks it up. The roboRIO has one built in; the PDH has one you switch on.",
        "With every device powered off, a multimeter across CAN-H and CAN-L reads both in parallel: about 60 ohms. 120 means one end is missing (or the cable is broken between you and it); 40 means one too many; near zero is a short.",
        "Bad termination shows up as CAN errors and, at worst, the bus shutting itself down (bus-off)."] },
    power_path: { title: "The power path", short: "Battery, main breaker, PDH, a breaker per port, then the leads to each controller. Every joint adds a little resistance; a bad one adds a lot.",
      body: ["Current flows from the battery through the main breaker to the PDH, out through a port's breaker and along two leads to the controller, and back. Every crimp, Wago and screw terminal on the way is a small resistor.",
        "Resistance turns current into lost voltage (V = I x R). A good feed loses about 0.6 V at 40 A. A loose joint can lose several volts: the controller sees a low supply, warns, and if it drops too far it reboots - vanishing from the CAN bus while it restarts.",
        "The tool compares the voltage each controller sees with the PDH's, at the current the PDH measured on that port, to estimate each feed's resistance. One controller rebooting points at its own feed; many at once points upstream, at the battery or main breaker."] },
    moment_of_inertia: { title: "Moment of inertia", short: "Mass says how hard a robot is to push; moment of inertia says how hard it is to turn. Weight far from the center (bumpers, battery) counts much more than weight near it.",
      body: ["Turning, every bit of the robot moves in a circle. A kilogram at the bumper moves fast and takes a lot to speed up; a kilogram at the center barely moves. Moment of inertia adds that up: mass times distance squared, in kg·m².",
        "PathPlanner needs it to know how quickly the robot can start and stop rotating. Too small and autos ask for turns the robot can't make; too big and they turn timidly.",
        "It can't be weighed, so the tool measures it: spinning in place with every wheel along its circle, the voltage needed to speed up the spin (angular kA) against the voltage needed to speed up a straight push (linear kA) gives it, with the mass and the module radius: MOI = mass x radius x kA(turning) / kA(straight)."] },
    camera_mount: { title: "Where the camera sits", short: "Vision turns a tag in the picture into a robot pose through one fixed transform: robot center to camera lens. If that is wrong, every vision pose is wrong by the same amount, or worse.",
      body: ["The camera knows where the tag is relative to itself. The field layout knows where the tag is on the field. Chaining them gives where the camera is on the field, and the mount takes that back to the robot's center.",
        "A position error moves every pose by the same distance. An angle error is worse: it grows with distance, about 1.7 cm per meter for each degree, so a tag 4 m away puts the pose 7 cm off for one degree of tilt the code doesn't know about.",
        "Measuring the mount with a tape is hard - where exactly is the center of a lens, and how much is it tilted? A tag on a wall at a measured spot gives the answer from the camera itself, and doing it from several spots shows how well the tape measurements agree."] },
    field_survey: { title: "Surveying the field's tags", short: "Localization trusts every AprilTag to be exactly where the official layout says. People hang them, so measure where they really are.",
      body: ["Two tags in the same camera frame fix where they sit relative to each other, whatever the robot's own position. Many frames tie whole groups of tags together; each group is then fitted onto the official layout, and what is left over is how far each tag really is from its place.",
        "Every measurement has noise, so a tag is only changed when it moved by clearly more than its own uncertainty - three times it, and at least a centimeter. Noise must never move a tag.",
        "Anything more than 30 cm off is refused: that is a misread or a tag on the wrong bracket, not something to copy into the robot. And a whole structure moved as one piece looks right this way: its tags still agree with each other."] },
    battery_current: { title: "Battery-side current", short: "The PDH measures the current a controller takes from the battery. Below full speed that is much less than the current in the motor.",
      body: ["A motor controller is a fast switch. At 25% output it connects the motor to the battery a quarter of the time; the rest of the time the motor's current keeps circulating through the controller, not the battery.",
        "Power in equals power out (minus a little heat), so battery current = motor current x output fraction. A drive motor pulling 20 A at 25% output takes only about 5 A from its PDH port.",
        "That is why the PDH port finder looks for which channel <i>rises</i>, not for the motor's own number, and why a motor stalled at low output can be hot while its breaker never notices."] },
    wiggle_test: { title: "The wiggle test", short: "With the robot on and disabled, gently move each cable and plug in turn while a tool watches for errors. The step that makes something happen is where the bad connection is.",
      body: ["Loose plugs and cracked wires usually work fine when nothing moves, and fail when the robot hits something. Wiggling recreates that one place at a time.",
        "The tool watches every controller (did it drop off the bus, reboot, or see its supply dip?) and the CAN bus's error counters. Because the counters recover within milliseconds, the robot counts every loop that saw an error, so a glitch too short for a person to notice still shows.",
        "Go in order along the CAN chain, then each controller's power leads, then the main power. Keep hands out while the robot is enabled."] },
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
      body: ["The goal is where you want to end up; getSetpoint() is where the plan says to be now - feed its velocity to the feedforward. It runs on the roboRIO at 50 Hz, so it suits slower mechanisms better than a 1 kHz steering loop."], links: ["profiled"] },
  };

  // Phrases in plain text that link to a lesson, longest first. Used for guide steps and advice.
  const TERMS = [
    ["static friction", "kS"], ["feedforward", "feedforward"], ["dead time", "dead_time"], ["rise time", "rise_time"],
    ["overshoot", "overshoot"], ["settling", "settling_time"], ["left over", "steady_state_error"], ["stops short", "steady_state_error"],
    ["steady-state error", "steady_state_error"], ["oscillat", "oscillation"], ["ringing", "oscillation"], ["saturat", "saturation"], ["flat out", "saturation"],
    ["current limit", "current_limit"], ["ramp rate", "ramp_rate"], ["windup", "integral_windup"], ["wind up", "integral_windup"], ["IZone", "iZone"],
    ["absolute encoder", "absolute_encoder"], ["motor encoder", "motor_encoder"], ["offsets", "offset"], ["offset", "offset"], ["inverted", "inversion"],
    ["inversion", "inversion"], ["gear ratio", "gear_ratio"], ["gearing", "gear_ratio"], ["speed filter", "velocity_filter"], ["velocity filter", "velocity_filter"],
    ["auto-sync", "encoder_sync"], ["deadman", "deadman"], ["on blocks", "environment"], ["carpet", "carpet_scrub"], ["setpoint", "setpoint"],
    ["kP", "kP"], ["kD", "kD"], ["kI", "kI"], ["kS", "kS"], ["kV", "kV"], ["kA", "kA"], ["PID", "feedback"], ["battery", "voltage_sag"],
    ["motion profile", "motion_profile"], ["trapezoid", "trapezoid_profile"], ["MAXMotion", "maxmotion_position"], ["heat estimate", "heat_estimate"],
    ["derate", "derate"], ["stall", "stall"], ["bevel gear", "bevel_gear"], ["straight-edge", "straight_edge"],
    ["coast", "coast_mode"], ["redeploy", "redeploy"], ["slip current", "slip_current"], ["traction", "traction"], ["slip", "traction"], ["CAN bus", "can_bus"],
    ["terminator", "can_termination"], ["termination", "can_termination"], ["power leads", "power_path"], ["PDH port", "power_path"], ["battery side", "battery_current"], ["camera mount", "camera_mount"], ["moment of inertia", "moment_of_inertia"], ["field survey", "field_survey"], ["wiggle test", "wiggle_test"], ["keep the wheels still", "hold_still"], ["hand check", "hand_check"],
  ];

  // ---------------------------------------------------------------- the hover card
  const tip = document.createElement("div");
  tip.className = "learn-tip";
  tip.setAttribute("role", "tooltip");
  tip.id = "learn-tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  let hideTimer = null, anchor = null;

  function card(key, extra) {
    const l = L[key];
    if (!l) return extra ? `<div>${esc(extra)}</div>` : "";
    return `${extra ? `<div class="learn-extra">${esc(extra)}</div>` : ""}
      <div class="learn-title">${esc(l.title)}</div><div>${esc(l.short)}</div>
      <button class="learn-more" data-lesson="${esc(key)}">Lesson →</button>`;
  }

  function place(x, y) {
    tip.style.left = "0px"; tip.style.top = "0px";
    const r = tip.getBoundingClientRect();
    const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    let left = Math.min(Math.max(8, x - r.width / 2), vw - r.width - 8);
    let top = y + 14;
    if (top + r.height > vh - 8) top = Math.max(8, y - r.height - 14);
    tip.style.left = left + window.scrollX + "px";
    tip.style.top = top + window.scrollY + "px";
  }

  function showFor(el) {
    const key = el.dataset.learn;
    if (!L[key]) return;
    clearTimeout(hideTimer);
    anchor = el;
    tip.innerHTML = card(key, el.dataset.learnText);
    tip.hidden = false;
    const r = el.getBoundingClientRect();
    place(r.left + r.width / 2, r.bottom);
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

  document.addEventListener("mouseover", e => {
    const el = e.target.closest && e.target.closest("[data-learn]");
    if (el) showFor(el);
    else if (!e.target.closest || !e.target.closest(".learn-tip")) { if (anchor) hideSoon(); }
  });
  document.addEventListener("focusin", e => { const el = e.target.closest && e.target.closest("[data-learn]"); if (el) showFor(el); });
  document.addEventListener("focusout", e => { if (e.target.closest && e.target.closest("[data-learn]")) hideSoon(); });
  tip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  tip.addEventListener("mouseleave", hideSoon);
  document.addEventListener("keydown", e => { if (e.key === "Escape") { hide(); closeDrawer(); } });
  document.addEventListener("click", e => {
    const more = e.target.closest && e.target.closest("[data-lesson]");
    if (more) { e.preventDefault(); hide(); open(more.dataset.lesson); return; }
    const el = e.target.closest && e.target.closest("[data-learn]");
    // A tap (no hover) on a term opens its lesson; on inputs and buttons, clicks keep their job.
    if (el && !el.matches("input, select, button, textarea") && L[el.dataset.learn]
        && !el.closest("button")) { hide(); open(el.dataset.learn); }
  });

  // ---------------------------------------------------------------- the lesson drawer
  const drawer = document.createElement("aside");
  drawer.className = "learn-drawer";
  drawer.setAttribute("aria-label", "Control theory lessons");
  drawer.hidden = true;
  document.body.appendChild(drawer);

  function lessonHtml(key) {
    const l = L[key];
    const unit = UNITS.find(u => u.lessons.includes(key));
    const idx = unit ? unit.lessons.indexOf(key) : -1;
    const next = unit && unit.lessons[idx + 1];
    return `<div class="row" style="justify-content:space-between">
        <button class="btn small" data-lindex="1">← All lessons</button>
        <button class="btn small" data-lclose="1" aria-label="Close lessons">✕</button></div>
      ${unit ? `<div class="muted small">${esc(unit.title)}</div>` : ""}
      <h2>${esc(l.title)}</h2>
      <p class="learn-short">${esc(l.short)}</p>
      ${(l.body || []).map(p => `<p>${p}</p>`).join("")}
      ${l.see ? `<div class="callout"><b>On the graphs:</b> ${esc(l.see)}</div>` : ""}
      ${l.try ? `<div class="callout"><b>Try it:</b> ${esc(l.try)}</div>` : ""}
      ${(l.links || []).length ? `<div class="small"><b>Read more</b><ul>${l.links.map(k => `<li><a href="${LINK[k][0]}" target="_blank" rel="noopener">${esc(LINK[k][1])}</a></li>`).join("")}</ul></div>` : ""}
      ${next ? `<button class="btn" data-lesson="${esc(next)}">Next: ${esc(L[next].title)} →</button>` : ""}`;
  }

  function indexHtml() {
    return `<div class="row" style="justify-content:space-between"><h2>Lessons</h2>
        <button class="btn small" data-lclose="1" aria-label="Close lessons">✕</button></div>
      <p class="small muted">In WPILib's order: feedforward, then feedback. Every underlined word in the tool opens one of these.</p>
      ${UNITS.map(u => `<div class="learn-unit ${u.locked && !secondOrderReady() ? "locked" : ""}"><h3>${esc(u.title)}</h3>
        ${u.locked && !secondOrderReady() ? `<p class="small muted">Unlocks once steering and drive pass their first-order targets in the Guide. You can still read ahead.</p>` : ""}
        <div class="learn-list">${u.lessons.map(k => `<button class="btn small" data-lesson="${k}">${esc(L[k].title)}</button>`).join("")}</div></div>`).join("")}`;
  }

  function secondOrderReady() { return typeof Guide !== "undefined" && !!Guide.firstOrderDone && Guide.firstOrderDone(); }

  function open(key) {
    drawer.innerHTML = key && L[key] ? lessonHtml(key) : indexHtml();
    drawer.hidden = false;
    drawer.scrollTop = 0;
    const first = drawer.querySelector("h2");
    if (first) { first.tabIndex = -1; first.focus(); }
  }
  function closeDrawer() { drawer.hidden = true; }
  drawer.addEventListener("click", e => {
    if (e.target.closest("[data-lclose]")) closeDrawer();
    else if (e.target.closest("[data-lindex]")) open(null);
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
      html = html.slice(0, at) + `<span class="term" data-learn="${key}">${m[2]}</span>` + html.slice(at + m[2].length);
      used.add(key); count++;
    }
    return html;
  }
  const term = (key, text) => `<span class="term" data-learn="${key}">${esc(text || (L[key] && L[key].title) || key)}</span>`;
  const chips = keys => keys.filter(k => L[k]).map(k => `<button class="chip learn-chip" data-lesson="${k}">${esc(L[k].title)}</button>`).join("");

  return { L, UNITS, open, showAt, hide, link, term, chips };
})();
