package frc.lib.swervetune;

/**
 * Records one Driver Station controller exactly as the robot code receives it: every axis, the
 * buttons and the D-pad, about every 20 ms (each Driver Station packet).
 *
 * <p>The laptop's Controllers tab checks a controller plugged into the laptop; this is the same
 * check through the robot, so it sees what the robot code sees - including a button bounce the
 * Driver Station passes on, which a toggle in the code would act on. Runs disabled, commands
 * nothing, and ends early when asked (the "Done" of the buttons step).
 *
 * <p>Channels: {@code a0..a5} (WPILib axis numbers: on an Xbox controller 0/1 the left stick, 2/3 the
 * triggers, 4/5 the right stick), {@code buttons} (bit 0 is button 1) and {@code pov} (degrees, -1
 * when the D-pad is released).
 */
final class ControllerProcedure implements Procedure {
  static final int AXES = 6;
  private volatile boolean stopRequested;
  private double durationS;

  @Override
  public String name() {
    return "controller";
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

  private static int port(TestContext ctx) {
    return (int) Math.round(ctx.args.get("port", 0, 0, 5));
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.signals == null) {
      return "This robot code can't read the Driver Station's controllers.";
    }
    int p = port(ctx);
    if (ctx.signals.stickAxes(p).length == 0) {
      return "No controller on Driver Station port " + p + ". Plug it in and check its USB tab.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return ctx.args.get("duration_s", 5, 0.5, 90) + 2;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  @Override
  public void start(TestContext ctx) {
    stopRequested = false;
    durationS = ctx.args.get("duration_s", 5, 0.5, 90);
    int p = port(ctx);
    RobotSignals s = ctx.signals;
    for (int i = 0; i < AXES; i++) {
      final int a = i;
      ctx.sampler.channel("a" + a, () -> {
        double[] v = s.stickAxes(p);
        return a < v.length ? v[a] : Double.NaN;
      });
    }
    ctx.sampler
        .channel("buttons", () -> s.stickButtons(p))
        .channel("pov", () -> s.stickPov(p));
    ctx.meta("port", p);
    ctx.meta("axis_count", s.stickAxes(p).length);
    ctx.meta("is_xbox", s.stickIsXbox(p) ? 1 : 0);
    ctx.meta("duration_s", durationS);
    ctx.note("Controller on port " + p + ": " + s.stickName(p));
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    return stopRequested || t >= durationS;
  }

  // WPILib's Xbox button numbers, 1 to 10, by the names the laptop's Controllers tab uses.
  static final String[] XBOX_BUTTONS = {"A", "B", "X", "Y", "Left bumper", "Right bumper", "Back", "Start",
      "Left stick press", "Right stick press"};

  /** "Pressed now: A, D-pad up": the laptop lights each button as the robot sees it. */
  static String pressedNow(int buttons, int pov) {
    java.util.List<String> on = new java.util.ArrayList<>();
    for (int i = 0; i < XBOX_BUTTONS.length; i++) {
      if ((buttons & (1 << i)) != 0) {
        on.add(XBOX_BUTTONS[i]);
      }
    }
    if (pov >= 0) {
      int d = ((pov % 360) + 360) % 360;
      if (d >= 315 || d <= 45) {
        on.add("D-pad up");
      }
      if (d >= 45 && d <= 135) {
        on.add("D-pad right");
      }
      if (d >= 135 && d <= 225) {
        on.add("D-pad down");
      }
      if (d >= 225 && d <= 315) {
        on.add("D-pad left");
      }
    }
    return "Pressed now: " + (on.isEmpty() ? "nothing" : String.join(", ", on));
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    int p = port(ctx);
    return pressedNow(ctx.signals.stickButtons(p), ctx.signals.stickPov(p));
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {}

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1.0, t / Math.max(0.1, durationS));
  }

  @Override
  public void requestStop() {
    stopRequested = true;
  }
}
