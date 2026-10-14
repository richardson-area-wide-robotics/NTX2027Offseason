package frc.lib.slothtune;

/**
 * Decides, every loop, whether a running test may continue.
 *
 * <p>Pure logic with no WPILib or hardware dependency, so every rule here is unit tested by
 * feeding it numbers. The harness gathers {@link Inputs} from the robot and acts on the
 * {@link Verdict}; nothing in here can move a motor.
 *
 * <p>The rules, and why each exists:
 *
 * <ul>
 *   <li><b>Disabled</b> stops everything. The Driver Station disable is the real e-stop; this only
 *       makes sure the test records that it was cut short rather than finishing "successfully".
 *   <li><b>Laptop gone</b> stops everything. A test started from a laptop must not keep running
 *       after the laptop that could stop it has disconnected.
 *   <li><b>Deadman</b> on {@link TestEnvironment#FIELD} and {@link TestEnvironment#BLOCKS}:
 *       nothing that spins a wheel runs unless a person is holding it. Before a test starts that is a wait; releasing it mid-test aborts,
 *       because a step response with a gap in the middle is not a step response.
 *   <li><b>Driver override</b>: touching a stick aborts at once and hands the robot back.
 *   <li><b>Blocks interlock</b>: on blocks the gyro must not see the chassis turning while wheels
 *       are driven, and no wheel may work like one carrying weight. If either happens, the robot
 *       is on the floor, whatever the laptop was told.
 *   <li><b>Geofence, impact, stall, overspeed</b> on the field.
 *   <li><b>Battery</b>: refuse to start on a tired pack, abort on a sag that risks a brownout.
 * </ul>
 */
public final class SafetySupervisor {

  /** What happens next. */
  public enum Action {
    /** Carry on. */
    CONTINUE,
    /** Hold the robot still and wait; the test has not started its measured part. */
    WAIT,
    /** Stop the robot and end the test. */
    ABORT
  }

  /** An {@link Action} and the sentence to show a person. */
  public record Verdict(Action action, String reason) {
    static final Verdict OK = new Verdict(Action.CONTINUE, "");

    static Verdict waitFor(String reason) {
      return new Verdict(Action.WAIT, reason);
    }

    static Verdict abort(String reason) {
      return new Verdict(Action.ABORT, reason);
    }

    public boolean isOk() {
      return action == Action.CONTINUE;
    }
  }

  /** Tunable thresholds. Defaults are deliberately conservative; see {@link SlothTuneConfig}. */
  public static final class Limits {
    /** A laptop heartbeat older than this means the laptop is gone. */
    public double heartbeatTimeoutS = 0.5;
    /** Any driver stick past this aborts. */
    public double driverOverride = 0.2;
    /** Refuse to start below this on the field. */
    public double minStartVoltsField = 11.8;
    /** Refuse to start below this on blocks or in sim. */
    public double minStartVoltsBlocks = 11.0;
    /** Abort below this, sustained for {@link #sustainS}. */
    public double brownoutVolts = 7.0;
    /** Horizontal acceleration that counts as hitting something, m/s^2. About 1.2 g. */
    public double impactMps2 = 12.0;
    /** On blocks, a gyro rate above this while wheels are driven means the chassis is moving. */
    public double blocksYawRateDps = 20.0;
    /** On blocks, horizontal acceleration above this, sustained, means the chassis is moving. */
    public double blocksAccelMps2 = 2.5;
    /** Wheel speed allowed above the commanded cap before calling it a runaway. */
    public double overspeedMarginMps = 0.4;
    /** Drive current as a fraction of its limit that, with no wheel speed, counts as stalled. */
    public double stallCurrentFraction = 0.85;
    /** Below this wheel speed a module at high current is stalled, m/s. */
    public double stallSpeedMps = 0.15;
    /** How long a condition must hold before it counts, seconds. Rejects single-sample noise. */
    public double sustainS = 0.15;
    /** Stall must hold this long, seconds. Accelerating from rest briefly looks like a stall. */
    public double stallSustainS = 0.4;
    /** In a wall push, the chassis moving this far means it is not against a wall, meters. */
    public double wallTravelM = 0.3;
    /**
     * On blocks: a drive current above this, held for {@link #carryHoldS} while the wheel's speed
     * changes by less than {@link #carrySpeedChangeMps}, means the wheel is carrying weight. A
     * wheel in the air spins up within a few hundredths of a second and the current falls back to
     * friction (2 to 3 A); one carrying a quarter of a 55 kg robot takes about twenty times longer.
     * On the practice pod's physics no blocks run held 6 A for more than 0.02 s, and every floor run
     * that stepped its speed was caught within 0.16 s of the step. To confirm on a robot.
     */
    public double carryAmps = 6.0;
    /** How long a wheel's current must stay above {@link #carryAmps}, seconds. */
    public double carryHoldS = 0.15;
    /** A free wheel would change speed by far more than this in that time, m/s. */
    public double carrySpeedChangeMps = 1.5;
    /**
     * The lift check before a blocks test that drives the wheels: every drive motor gets
     * {@link #liftVolts} for {@link #liftPulseS}, and each wheel's speed gained per amp-second of
     * current is compared with {@link #liftMinMpsPerAmpS}. A wheel in the air gains it fast; one
     * carrying a quarter of the robot needs many times the current for less speed. On the practice
     * pod's physics, sampled as the robot samples (50 Hz, current a status frame late): blocks 1.9 to
     * 5.4 m/s per A*s, floor 0.12 to 0.48 (a 30 kg robot on NEOs is the highest), whatever the gains.
     * On the floor the pulse moves the robot a few centimeters. To confirm on a robot.
     */
    public double liftVolts = 2.5;
    public double liftPulseS = 0.12;
    /** Time for the wheels to coast still before the test itself starts, seconds. */
    public double liftSettleS = 0.4;
    public double liftMinMpsPerAmpS = 1.0;
  }

  /** Everything the supervisor looks at, gathered fresh each loop. */
  public static final class Inputs {
    public TestEnvironment env = TestEnvironment.UNSET;
    public boolean enabled;
    public boolean fmsAttached;
    public boolean autonomous;
    public double nowS;
    public double heartbeatAgeS = Double.POSITIVE_INFINITY;
    public boolean guiDeadman;
    public boolean controllerDeadman;
    /** Largest absolute driver stick deflection, 0..1. */
    public double driverStickMax;
    /** Distance from where the test started, meters, from odometry. */
    public double displacementM;
    /** Largest measured wheel speed, m/s. */
    public double maxWheelSpeedMps;
    /** Largest drive current as a fraction of the drive current limit, 0..1+. */
    public double maxDriveCurrentFraction;
    /** Wheel speed of the module drawing that current, m/s. */
    public double speedAtMaxCurrentMps;
    /** Each module's drive current, amps, and wheel speed, m/s, for the carrying-weight check. */
    public double[] driveAmps = new double[0];
    public double[] wheelSpeedsMps = new double[0];
    /** Each module's name, for saying which wheel. */
    public String[] moduleNames = new String[0];
    /** Chassis yaw rate from the heading, deg/s. */
    public double yawRateDps;
    /** Horizontal acceleration magnitude, m/s^2, or NaN if the IMU gives none. Raw: impacts are spikes. */
    public double horizontalAccelMps2 = Double.NaN;
    /**
     * The same, smoothed over about 0.1 s. Wheels spinning on blocks shake the frame, and that
     * vibration must not read as the chassis moving.
     */
    public double horizontalAccelSmoothedMps2 = Double.NaN;
    public double busVolts = 12.5;
    public boolean gyroConnected = true;
    public boolean gyroCalibrating = false;
    /**
     * Set when a drivetrain motor is derated or shut off by the {@link MotorGuard}, saying which and
     * why; empty otherwise.
     */
    public String hotMotor = "";
  }

  /** What the running test is allowed to do, so the rules that apply can be chosen. */
  public record TestProfile(
      boolean spinsWheels, boolean movesChassis, double speedCapMps, double spaceBudgetM,
      boolean pushesWall) {
    public TestProfile(boolean spinsWheels, boolean movesChassis, double speedCapMps,
        double spaceBudgetM) {
      this(spinsWheels, movesChassis, speedCapMps, spaceBudgetM, false);
    }
  }

  private final Limits limits;
  private double blocksMotionSince = Double.NaN;
  private double brownoutSince = Double.NaN;
  private double stallSince = Double.NaN;
  /** Per module: when its drive current went above {@link Limits#carryAmps}, and its speed then. */
  private double[] carrySince = new double[0];
  private double[] carryFromMps = new double[0];

  public SafetySupervisor(Limits limits) {
    this.limits = limits;
  }

  public Limits limits() {
    return limits;
  }

  /** Forgets sustained-condition timers. Call when a test starts. */
  public void reset() {
    blocksMotionSince = Double.NaN;
    brownoutSince = Double.NaN;
    stallSince = Double.NaN;
    carrySince = new double[0];
    carryFromMps = new double[0];
  }

  /**
   * Whether a test may start at all. Checked once, before anything moves. A refusal here is a
   * sentence telling the person what to change, never a silent no.
   *
   * @return null if it may start, otherwise the reason it may not
   */
  public String refuseStart(Inputs in, TestProfile test, boolean needsEnabled) {
    if (in.fmsAttached) {
      return "The FMS is attached. Tuning tests never run on a match field.";
    }
    if (in.autonomous) {
      return "The robot is in autonomous. Use Teleop or Test mode for tuning.";
    }
    if (!test.spinsWheels()) {
      return null;
    }
    if (!in.env.allowsActuation) {
      return "Say where the robot is first: On blocks or On the floor. Motion tests stay locked until"
          + " you do.";
    }
    if (needsEnabled && in.heartbeatAgeS > limits.heartbeatTimeoutS) {
      return "No heartbeat from the laptop tool, so nothing could stop this test. Start the tool"
          + " and try again.";
    }
    double minVolts =
        in.env == TestEnvironment.FIELD ? limits.minStartVoltsField : limits.minStartVoltsBlocks;
    if (in.env != TestEnvironment.SIM && in.busVolts < minVolts) {
      return String.format(
          "Battery is at %.1f V; this test needs %.1f V to start. A tired pack changes every"
              + " number this test measures. Swap it.",
          in.busVolts, minVolts);
    }
    if (in.env != TestEnvironment.SIM && !in.gyroConnected) {
      return "The gyro is not reporting. The on-blocks check and impact detection both depend on it."
          + " Check its CAN or USB connection.";
    }
    if (in.env == TestEnvironment.FIELD && test.movesChassis() && test.spaceBudgetM() <= 0) {
      return "Tell the tool how much clear floor there is before running a test that drives.";
    }
    return null;
  }

  /** Whether the running test may continue this loop. */
  public Verdict check(Inputs in, TestProfile test, boolean started) {
    if (!in.enabled) {
      return started
          ? Verdict.abort("Robot disabled.")
          : Verdict.waitFor("Enable the robot (Teleop or Test) to start.");
    }
    if (in.fmsAttached) {
      return Verdict.abort("FMS attached.");
    }
    if (!test.spinsWheels()) {
      return Verdict.OK;
    }
    if (in.heartbeatAgeS > limits.heartbeatTimeoutS) {
      return Verdict.abort("Lost the laptop tool's heartbeat.");
    }
    if (in.env != TestEnvironment.SIM) {
      if (!in.gyroConnected) {
        return Verdict.abort("The gyro stopped reporting.");
      }
      if (in.gyroCalibrating) {
        return started
            ? Verdict.abort("The gyro started calibrating mid-test; its readings cannot be trusted.")
            : Verdict.waitFor("The gyro is calibrating. Keep the robot completely still.");
      }
    }
    if (!in.hotMotor.isEmpty()) {
      return started
          ? Verdict.abort(in.hotMotor + " Its current limit was cut, so nothing measured from here"
              + " on would be true. Let it cool.")
          : Verdict.waitFor(in.hotMotor + (in.hotMotor.contains("stall") ? " Clear what it is stuck on."
              : in.hotMotor.contains("can't aim") ? " Fix the steering motor first." : " Waiting for it to cool."));
    }
    if (in.driverStickMax > limits.driverOverride) {
      return Verdict.abort("Driver moved a stick. Control handed back.");
    }

    if (in.env.needsDeadman() && !(in.guiDeadman || in.controllerDeadman)) {
      return started
          ? Verdict.abort("Deadman released.")
          : Verdict.waitFor("Hold the deadman to start.");
    }

    if (in.env == TestEnvironment.BLOCKS) {
      boolean chassisMoving =
          Math.abs(in.yawRateDps) > limits.blocksYawRateDps
              || (!Double.isNaN(in.horizontalAccelSmoothedMps2)
                  && in.horizontalAccelSmoothedMps2 > limits.blocksAccelMps2);
      if (sustained(chassisMoving, in.nowS, SustainTimer.BLOCKS)) {
        return Verdict.abort(
            "The chassis is moving, so the robot is NOT on blocks. Put it on blocks, or set"
                + " On the floor.");
      }
      int m = carryingWheel(in);
      if (m >= 0) {
        return Verdict.abort(String.format("NOT on blocks: the %s wheel drew over %.0f A for %.2f s"
                + " while its speed changed only %.2f m/s, so it is pushing weight (the robot's, on the"
                + " floor) or rubbing on something. A wheel in the air spins up in a few hundredths of"
                + " a second. Put the robot on blocks, or set On the floor.",
            m < in.moduleNames.length ? in.moduleNames[m] : "module " + m, limits.carryAmps,
            limits.carryHoldS, Math.abs(Math.abs(in.wheelSpeedsMps[m]) - carryFromMps[m])));
      }
    }

    if (in.env == TestEnvironment.FIELD) {
      if (!Double.isNaN(in.horizontalAccelMps2) && in.horizontalAccelMps2 > limits.impactMps2) {
        return Verdict.abort(
            String.format("Impact: %.1f m/s^2. Check the robot and what it hit.", in.horizontalAccelMps2));
      }
      if (test.movesChassis() && in.displacementM > test.spaceBudgetM()) {
        return Verdict.abort(
            String.format(
                "Left the declared space: %.2f m from the start, budget %.2f m.",
                in.displacementM, test.spaceBudgetM()));
      }
      if (test.pushesWall()) {
        // Pushing at high current with the wheels still is the test; moving is the fault.
        if (in.displacementM > limits.wallTravelM) {
          return Verdict.abort(String.format(
              "The robot moved %.2f m: it is not against a solid wall, or the wall gave way.",
              in.displacementM));
        }
      } else {
        boolean stalled =
            in.maxDriveCurrentFraction > limits.stallCurrentFraction
                && Math.abs(in.speedAtMaxCurrentMps) < limits.stallSpeedMps;
        if (sustained(stalled, in.nowS, SustainTimer.STALL)) {
          return Verdict.abort("Wheels stalled at high current: the robot is pushing on something.");
        }
      }
    }

    if (in.env != TestEnvironment.SIM
        && in.maxWheelSpeedMps > test.speedCapMps() + limits.overspeedMarginMps) {
      return Verdict.abort(
          String.format(
              "Wheel speed %.2f m/s is over the %.2f m/s cap. Something is not following its"
                  + " command.",
              in.maxWheelSpeedMps, test.speedCapMps()));
    }

    boolean sagging = in.env != TestEnvironment.SIM && in.busVolts < limits.brownoutVolts;
    if (sustained(sagging, in.nowS, SustainTimer.BROWNOUT)) {
      return Verdict.abort(String.format("Battery sagged to %.1f V. Brownout risk.", in.busVolts));
    }
    return Verdict.OK;
  }

  /**
   * The first module whose drive current has stayed above {@link Limits#carryAmps} for
   * {@link Limits#carryHoldS} while its speed changed by less than {@link Limits#carrySpeedChangeMps}:
   * a wheel carrying weight. -1 if none.
   */
  private int carryingWheel(Inputs in) {
    int n = Math.min(in.driveAmps.length, in.wheelSpeedsMps.length);
    if (carrySince.length != n) {
      carrySince = new double[n];
      carryFromMps = new double[n];
      java.util.Arrays.fill(carrySince, Double.NaN);
    }
    for (int m = 0; m < n; m++) {
      double v = Math.abs(in.wheelSpeedsMps[m]);
      if (!(in.driveAmps[m] > limits.carryAmps)) {
        carrySince[m] = Double.NaN;
        continue;
      }
      if (Double.isNaN(carrySince[m])) {
        carrySince[m] = in.nowS;
        carryFromMps[m] = v;
      }
      if (in.nowS - carrySince[m] >= limits.carryHoldS
          && Math.abs(v - carryFromMps[m]) < limits.carrySpeedChangeMps) {
        return m;
      }
    }
    return -1;
  }

  private enum SustainTimer {
    BLOCKS,
    BROWNOUT,
    STALL
  }

  /** True once {@code condition} has held continuously for the sustain time of that timer. */
  private boolean sustained(boolean condition, double nowS, SustainTimer which) {
    double since =
        switch (which) {
          case BLOCKS -> blocksMotionSince;
          case BROWNOUT -> brownoutSince;
          case STALL -> stallSince;
        };
    if (!condition) {
      since = Double.NaN;
    } else if (Double.isNaN(since)) {
      since = nowS;
    }
    switch (which) {
      case BLOCKS -> blocksMotionSince = since;
      case BROWNOUT -> brownoutSince = since;
      case STALL -> stallSince = since;
    }
    double needed = which == SustainTimer.STALL ? limits.stallSustainS : limits.sustainS;
    return condition && nowS - since >= needed;
  }
}
