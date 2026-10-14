package frc.lib.swervetune;

import java.util.ArrayList;
import java.util.List;

/**
 * Bring-up: runs chosen motors at a low output, briefly, and records every chosen motor's encoder,
 * current and output, so the laptop can say whether each turned, which way, how far against the
 * others on its shaft, and whether motors on one shaft fight.
 *
 * <p>Motors are picked by their place in the motor guard's list (the order the laptop sees in the
 * live data), as bit masks, since test arguments are numbers: {@code drive} are run at {@code duty}
 * (0.02 to 0.15, default 0.08) for {@code pulse} seconds (0.2 to 1.0, default 0.6) after a
 * {@value #QUIET_S} s baseline; {@code zero} are held at zero output for the whole test, so a motor
 * the code was holding in position can be turned by its shaft partner; {@code watch} are only
 * recorded. A follower is never driven or zeroed directly (that would end its follow mode): drive its
 * leader and watch it.
 *
 * <p>The robot's own code is paused for the test ({@link #pausesRobotCode}): a subsystem that sets
 * its motor every loop would otherwise fight the test. On blocks only, with the deadman held.
 *
 * <p>It stops at once if a driven motor draws more than {@code stop_amps} (5 to 40 A, default 25)
 * for {@value #STALL_S} s while barely turning: a jam, or motors on one shaft pushing against each
 * other.
 */
final class MotorTestProcedure implements Procedure {
  static final double QUIET_S = 0.3;
  static final double AFTER_S = 0.5;
  static final double STALL_S = 0.15;
  /** A driven motor turning slower than this, rotations a second, at high current is stalled. */
  static final double STALLED_RPS = 0.5;

  private final List<MotorGuard.Motor> drive = new ArrayList<>();
  private final List<MotorGuard.Motor> zero = new ArrayList<>();
  private final List<MotorGuard.Motor> all = new ArrayList<>();
  private double duty;
  private double pulseS;
  private double stopAmps;
  private double highSinceS = Double.NaN;
  private double lastT;
  private double[] lastRot = new double[0];
  private String cut;

  @Override
  public String name() {
    return "motor_test";
  }

  @Override
  public boolean spinsWheels() {
    // It commands motors: the deadman, the heartbeat and the environment rules all apply.
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  @Override
  public boolean pausesRobotCode() {
    return true;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return env == TestEnvironment.BLOCKS || env == TestEnvironment.SIM;
  }

  @Override
  public double expectedTopSpeedMps(TestContext ctx) {
    // The drivetrain is stopped for this test: any wheel speed past a crawl is a fault.
    return 0.3;
  }

  private static List<MotorGuard.Motor> pick(TestContext ctx, String key) {
    long mask = (long) ctx.args.get(key, 0);
    List<MotorGuard.Motor> out = new ArrayList<>();
    for (int i = 0; i < ctx.motors.size() && i < 62; i++) {
      if ((mask >> i & 1L) == 1L) {
        out.add(ctx.motors.get(i));
      }
    }
    return out;
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.motors.isEmpty()) {
      return "No motors are registered with the motor guard: each subsystem's watchMotors must run.";
    }
    long known = ctx.motors.size() >= 62 ? -1L : (1L << ctx.motors.size()) - 1;
    for (String key : new String[] {"drive", "zero", "watch"}) {
      long mask = (long) ctx.args.get(key, 0);
      if ((mask & ~known) != 0) {
        return "The test names a motor the robot doesn't have (" + key + "). Refresh the laptop's motor list.";
      }
    }
    if (pick(ctx, "drive").isEmpty()) {
      return "No motor to run: pick at least one.";
    }
    for (MotorGuard.Motor m : pick(ctx, "drive")) {
      if (!m.channel.testDuty(0)) {
        return m.name + " can't be run by a test (its controller isn't one the tool can command).";
      }
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return QUIET_S + 1.0 + AFTER_S + 2;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 100;
  }

  @Override
  public void start(TestContext ctx) {
    duty = ctx.args.get("duty", 0.08, 0.02, 0.15) * (ctx.args.get("sign", 1) < 0 ? -1 : 1);
    pulseS = ctx.args.get("pulse", 0.6, 0.2, 1.0);
    stopAmps = ctx.args.get("stop_amps", 25, 5, 40);
    drive.clear();
    zero.clear();
    all.clear();
    drive.addAll(pick(ctx, "drive"));
    zero.addAll(pick(ctx, "zero"));
    for (String key : new String[] {"drive", "zero", "watch"}) {
      for (MotorGuard.Motor m : pick(ctx, key)) {
        if (!all.contains(m)) {
          all.add(m);
        }
      }
    }
    lastRot = new double[all.size()];
    for (int i = 0; i < all.size(); i++) {
      MotorGuard.Motor m = all.get(i);
      lastRot[i] = m.channel.motorRotations();
      final MotorGuard.MotorChannel c = m.channel;
      ctx.sampler.channel("m" + i + ".rot", c::motorRotations)
          .channel("m" + i + ".amps", c::amps)
          .channel("m" + i + ".duty", c::appliedDuty);
      ctx.note("motor " + i + ": " + m.name + (drive.contains(m) ? " (run)" : zero.contains(m) ? " (held at zero)" : " (watched)"));
    }
    ctx.meta("duty", duty);
    ctx.meta("pulse_s", pulseS);
    ctx.meta("quiet_s", QUIET_S);
    ctx.meta("after_s", AFTER_S);
    ctx.meta("stop_amps", stopAmps);
    double[] pdh = ctx.pdhCurrents.get();
    for (int i = 0; i < pdh.length; i++) {
      final int ch = i;
      ctx.sampler.channel("pdh" + ch, () -> {
        double[] now = ctx.pdhCurrents.get();
        return ch < now.length ? now[ch] : Double.NaN;
      });
    }
    if (ctx.env == TestEnvironment.SIM) {
      ctx.note("The simulator's motors don't turn: this run only checks the sequence.");
    }
    for (MotorGuard.Motor m : drive) {
      m.channel.testDuty(0);
    }
    for (MotorGuard.Motor m : zero) {
      m.channel.testDuty(0);
    }
    highSinceS = Double.NaN;
    lastT = 0;
    cut = null;
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    boolean pulsing = t >= QUIET_S && t < QUIET_S + pulseS;
    for (MotorGuard.Motor m : drive) {
      m.channel.testDuty(pulsing ? duty : 0);
    }
    for (MotorGuard.Motor m : zero) {
      m.channel.testDuty(0);
    }
    // A driven motor at high current that has stopped turning: jammed, or fighting its partner.
    double dt = Math.max(1e-3, t - lastT);
    String stalled = null;
    for (int i = 0; i < all.size(); i++) {
      MotorGuard.Motor m = all.get(i);
      double rot = m.channel.motorRotations();
      double rps = Math.abs(rot - lastRot[i]) / dt;
      lastRot[i] = rot;
      if (pulsing && drive.contains(m) && m.channel.amps() > stopAmps && rps < STALLED_RPS) {
        stalled = String.format("%s drew %.0f A without turning", m.name, m.channel.amps());
      }
    }
    lastT = t;
    if (stalled == null) {
      highSinceS = Double.NaN;
    } else if (Double.isNaN(highSinceS)) {
      highSinceS = t;
    }
    cut = stalled;
    return t >= QUIET_S + pulseS + AFTER_S;
  }

  @Override
  public String abortReason(TestContext ctx) {
    if (cut != null && lastT - highSinceS >= STALL_S) {
      return cut + ": jammed, or motors on one shaft pushing against each other. Stopped.";
    }
    return null;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    for (MotorGuard.Motor m : drive) {
      m.channel.testDuty(0);
    }
    for (MotorGuard.Motor m : zero) {
      m.channel.testDuty(0);
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1, t / (QUIET_S + pulseS + AFTER_S));
  }
}
