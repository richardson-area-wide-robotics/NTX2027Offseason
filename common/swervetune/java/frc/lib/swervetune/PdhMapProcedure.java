package frc.lib.swervetune;

/**
 * Finds which PDH port feeds each swerve motor: on blocks, pulses one motor at a time and records
 * every PDH channel's current; the laptop picks, for each pulse, the channel that rose.
 *
 * <p>The PDH is read from AdvantageKit's per-loop snapshot ({@link TestContext#pdhCurrents}), since
 * AdvantageKit already holds the PDH and a second handle would be refused. Each motor gets a quiet
 * {@value #QUIET_S} s, then a {@value #PULSE_S} s pulse; the quiet part is the baseline, so a
 * channel that was already drawing current (a compressor, a radio) does not confuse the result.
 *
 * <p>A drive motor is pulsed with a fixed voltage; a steering motor by sweeping its module's angle
 * at {@value #SWEEP_DPS} degrees a second, so it keeps drawing current for the whole pulse instead
 * of one spike. Only the swerve motors, and only on blocks: a drive wheel spins in the air and a
 * steering module turns most of a revolution. Mechanism motors can have hard stops, so their ports
 * come from a practice log (the laptop matches each motor's current to a PDH channel) or are typed
 * in.
 */
final class PdhMapProcedure implements Procedure {
  static final double QUIET_S = 0.6;
  static final double PULSE_S = 0.8;
  static final double SWEEP_DPS = 540;

  private double volts;
  private int count;
  private double slot;
  private double on;
  private double[] pdh = new double[0];
  private double[] hold = new double[0];
  private int sweeping = -1;
  private double sweepDeg;

  @Override
  public String name() {
    return "pdh_map";
  }

  @Override
  public boolean drivesWheels() {
    return true;
  }

  @Override
  public boolean spinsWheels() {
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return env == TestEnvironment.BLOCKS || env == TestEnvironment.SIM;
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.env != TestEnvironment.SIM && ctx.pdhCurrents.get().length == 0) {
      return "No PDH currents to read. AdvantageKit reads the PDH: check Robot.java calls"
          + " AkLogging.start, and that the PDH is on the CAN bus (its light, and REV Hardware Client).";
    }
    return null;
  }

  @Override
  public double expectedTopSpeedMps(TestContext ctx) {
    // Wheels free on blocks: the pulse's volts over 12 V of the module's free speed.
    double v = ctx.args.get("volts", 4.0, 1.0, 6.0);
    return v / 12.0 * ctx.io.maxModuleSpeedMps();
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return 2 * ctx.io.moduleCount() * (QUIET_S + PULSE_S) + 3;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  @Override
  public void start(TestContext ctx) {
    volts = ctx.args.get("volts", 4.0, 1.0, 6.0);
    count = 2 * ctx.io.moduleCount();
    slot = 0;
    on = 0;
    pdh = ctx.pdhCurrents.get();
    sweeping = -1;
    hold = new double[ctx.io.moduleCount()];
    for (int m = 0; m < hold.length; m++) {
      hold[m] = ctx.io.steerDeg(m);
    }
    ctx.meta("pulse_volts", volts);
    ctx.meta("sweep_dps", SWEEP_DPS);
    ctx.meta("quiet_s", QUIET_S);
    ctx.meta("pulse_s", PULSE_S);
    ctx.meta("pdh_channels", pdh.length);
    for (int k = 0; k < count; k++) {
      ctx.note("pulse " + k + ": " + motorName(ctx, k));
    }
    if (ctx.env == TestEnvironment.SIM) {
      ctx.note("The simulator's PDH reads zero: this run only checks the pulse sequence.");
    }
    ctx.sampler.channel("slot", () -> slot).channel("on", () -> on);
    for (int i = 0; i < pdh.length; i++) {
      final int ch = i;
      ctx.sampler.channel("pdh" + ch, () -> ch < pdh.length ? pdh[ch] : Double.NaN);
    }
  }

  private static String motorName(TestContext ctx, int k) {
    return ctx.io.moduleName(k / 2) + (k % 2 == 0 ? " drive" : " steer");
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    pdh = ctx.pdhCurrents.get();
    DrivetrainIO io = ctx.io;
    int k = (int) (t / (QUIET_S + PULSE_S));
    if (k >= count) {
      on = 0;
      io.stop();
      return true;
    }
    double intoPulse = t - k * (QUIET_S + PULSE_S) - QUIET_S;
    boolean pulsing = intoPulse >= 0;
    slot = k;
    on = pulsing ? 1 : 0;
    int module = k / 2;
    boolean drive = k % 2 == 0;
    if (sweeping >= 0 && !(pulsing && !drive && module == sweeping)) {
      // Where a sweep ended becomes the hold, so the module never swings back during the next
      // motor's quiet baseline.
      hold[sweeping] = sweepDeg;
      sweeping = -1;
    }
    for (int m = 0; m < io.moduleCount(); m++) {
      io.setDriveVolts(m, pulsing && drive && m == module ? volts : 0);
      if (pulsing && !drive && m == module) {
        sweeping = m;
        sweepDeg = hold[m] + SWEEP_DPS * Math.min(intoPulse, PULSE_S);
        io.setSteerDeg(m, sweepDeg);
      } else {
        io.setSteerDeg(m, hold[m]);
      }
    }
    return false;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    on = 0;
    ctx.io.stop();
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1, t / (count * (QUIET_S + PULSE_S)));
  }
}
