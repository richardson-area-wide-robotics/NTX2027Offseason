package frc.lib.swervetune;

/**
 * One test the robot can run on request.
 *
 * <p>A procedure only collects data and moves motors. It never judges the result: the analysis,
 * the advice and the pass/fail verdicts all live in the laptop tool, in one place, so that a
 * student in the GUI and an agent on the command line are always told the same thing about the
 * same run.
 *
 * <p>Life cycle, driven by {@link SwerveTune}: {@link #validate} once; then {@link #start} once
 * the safety supervisor is satisfied; {@link #execute} every robot loop until it returns true;
 * {@link #end} exactly once, including after an abort.
 */
public interface Procedure {

  /** The name the laptop uses to ask for it, e.g. {@code steer_step}. */
  String name();

  /** Whether it commands any motor. Decides deadman, heartbeat and environment rules. */
  boolean spinsWheels();

  /**
   * Whether it drives the wheels (not only the steering). On blocks such a test starts with a lift
   * check: a short pulse that tells a wheel in the air from one carrying the robot.
   */
  default boolean drivesWheels() {
    return false;
  }

  /** Whether the chassis is expected to travel. Decides the geofence. */
  boolean movesChassis(TestContext ctx);

  /**
   * Whether the robot is meant to push against a wall. The field's stall rule is then the point
   * of the test, not a fault, so it is replaced by a rule that the chassis must not move.
   */
  default boolean pushesWall() {
    return false;
  }

  /**
   * Whether the robot's own code pauses while it runs (every command cancelled, the command
   * scheduler and with it every subsystem's periodic stopped), for a test that runs a mechanism's
   * motor directly: a subsystem setting that motor every loop would fight it. It resumes when the
   * test ends, however it ends.
   */
  default boolean pausesRobotCode() {
    return false;
  }

  /** A reason to stop now, checked every loop (a jam, motors fighting); null to carry on. */
  default String abortReason(TestContext ctx) {
    return null;
  }

  /** Whether the robot must be enabled. Capture-only procedures run disabled, safest of all. */
  default boolean needsEnabled() {
    return spinsWheels();
  }

  /** Environments it may run in. */
  boolean allowedIn(TestEnvironment env);

  /**
   * Checks arguments and space before anything moves.
   *
   * @return null if it may run, otherwise a sentence saying what to change
   */
  String validate(TestContext ctx);

  /** Distance from the start the run may legitimately reach, meters. The geofence is this. */
  /**
   * The fastest the wheels are expected to turn in this test, m/s; the overspeed stop sits a margin
   * above it. Speed-commanded tests use the speed cap; a test that commands volts says what its
   * volts give.
   */
  default double expectedTopSpeedMps(TestContext ctx) {
    return ctx.speedCapMps;
  }

  /**
   * A line for the laptop's banner while the test runs, e.g. the buttons held right now in a
   * joystick check; null keeps "Running.".
   */
  default String liveMessage(TestContext ctx, double t) {
    return null;
  }

  default double spaceBudgetM(TestContext ctx) {
    return 0;
  }

  /** Longest it may take, seconds, after which it is aborted. */
  double timeoutS(TestContext ctx);

  /** How fast the sampler records, Hz. */
  default double sampleRateHz(TestContext ctx) {
    return 100;
  }

  /** Registers sampler channels and sends first commands. */
  void start(TestContext ctx);

  /**
   * One robot loop.
   *
   * @param t seconds since {@link #start}
   * @return true when finished
   */
  boolean execute(TestContext ctx, double t);

  /** Stops what it was doing and restores anything it changed. Always called, even after abort. */
  void end(TestContext ctx, boolean aborted);

  /** 0 to 1, for a progress bar. */
  double progress(TestContext ctx, double t);

  /** Asks an open-ended procedure, such as a capture, to finish cleanly. */
  default void requestStop() {}
}
