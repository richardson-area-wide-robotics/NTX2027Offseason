package frc.lib.swervetune;

/**
 * Loads the CAN bus and counts its errors: a few seconds quiet, then every swerve controller's
 * status frames sped up (about 60% more traffic), then quiet again.
 *
 * <p>A missing or broken terminator, or a marginal connection, garbles frames now and then; more
 * traffic means more frames to garble, so errors that hide on a quiet bus can show under load. A
 * clean result proves little: a short robot bus can run without errors with one terminator
 * missing. The multimeter check (the Wiring tab's termination check) is the only sure test; this
 * is the one that needs no meter. Moves nothing; runs disabled.
 *
 * <p>Channels: {@code util} (0-1), {@code busoff}, {@code txfull} (counts since power-on),
 * {@code rxerr}, {@code txerr} (the controller's error counters now), {@code phase} (0 quiet,
 * 1 loaded, 2 after).
 */
final class CanLoadProcedure implements Procedure {
  static final double QUIET_S = 3;
  static final double LOADED_S = 8;
  static final double AFTER_S = 2;

  private boolean loaded;
  private boolean restored;
  private volatile int phase;
  private boolean fastOk = true;

  @Override
  public String name() {
    return "can_load";
  }

  @Override
  public boolean spinsWheels() {
    return false;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  @Override
  public boolean needsEnabled() {
    return false;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return true;
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.signals == null || ctx.signals.canStatus().length < 5) {
      return "This robot code can't read the CAN bus's status, so there is nothing to count.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return QUIET_S + LOADED_S + AFTER_S + 3;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  private static double at(double[] s, int i) {
    return i < s.length ? s[i] : Double.NaN;
  }

  @Override
  public void start(TestContext ctx) {
    loaded = false;
    restored = false;
    phase = 0;
    RobotSignals s = ctx.signals;
    ctx.sampler
        .channel("util", () -> at(s.canStatus(), 0))
        .channel("busoff", () -> at(s.canStatus(), 1))
        .channel("txfull", () -> at(s.canStatus(), 2))
        .channel("rxerr", () -> at(s.canStatus(), 3))
        .channel("txerr", () -> at(s.canStatus(), 4))
        .channel("phase", () -> phase);
    ctx.meta("quiet_s", QUIET_S);
    ctx.meta("loaded_s", LOADED_S);
    ctx.meta("after_s", AFTER_S);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    if (!loaded && t >= QUIET_S) {
      loaded = true;
      phase = 1;
      DrivetrainIO.ApplyResult r = ctx.io.applyFastTelemetry(true);
      fastOk = r.ok();
      if (!r.ok()) {
        ctx.note("Couldn't speed up the status frames: " + r.message());
      }
    }
    if (loaded && !restored && t >= QUIET_S + LOADED_S) {
      restore(ctx);
      phase = 2;
    }
    return t >= QUIET_S + LOADED_S + AFTER_S;
  }

  private void restore(TestContext ctx) {
    restored = true;
    DrivetrainIO.ApplyResult r = ctx.io.applyFastTelemetry(false);
    if (!r.ok()) {
      r = ctx.io.applyFastTelemetry(false);
    }
    if (!r.ok()) {
      ctx.note("Couldn't put the status frames back to normal (" + r.message() + "): restart the robot code.");
    }
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    double[] c = ctx.signals.canStatus();
    String busy = Double.isFinite(at(c, 0)) ? String.format("%.0f%% busy", 100 * at(c, 0)) : "busy: unknown";
    String errs = at(c, 3) > 0 || at(c, 4) > 0
        ? String.format("errors now (%.0f receive, %.0f transmit)", at(c, 3), at(c, 4)) : "no errors now";
    String what = phase == 0 ? "Quiet" : phase == 1 ? "Loaded" : "Quiet again";
    return what + ": " + busy + ", " + errs + ".";
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    if (loaded && !restored) {
      restore(ctx);
    }
    ctx.meta("fast_ok", fastOk ? 1 : 0);
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1.0, t / (QUIET_S + LOADED_S + AFTER_S));
  }
}
