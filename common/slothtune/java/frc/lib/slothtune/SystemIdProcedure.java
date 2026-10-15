package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Identification, for model-based tuning: runs a mechanism's motors by voltage itself, with the
 * robot's own code paused, and records how the mechanism answers, so the laptop can fit its physics
 * (friction kS, back-EMF kV, inertia kA, gravity kG) and work its gains out from them. On blocks, before
 * the field. It only collects; the laptop judges.
 *
 * <p>The SPARKs are driven in voltage mode (each scales its output by its own supply, so a sagging
 * battery doesn't change what the motor gets) and record what they applied, their own supply, the
 * robot's battery, the position and speed the team's code reads, and the position and speed the
 * SPARK's own closed loop reads: the gap between that speed and the position's slope is the delay of
 * the SPARK's speed filter. Their status signals are sent every {@value #SIGNAL_MS} ms meanwhile.
 *
 * <p>A pivot or elevator never leaves its travel window ({@value #MARGIN} of the range inside its
 * limits). First it finds the band of volts that hold it still (friction either side of gravity) by
 * a seesaw: still, the voltage climbs on; moving, it turns against the motion; where motion starts
 * from rest is an edge of the band. Then slow sweeps across the window at a governed speed (the
 * voltage is the hold there plus an integral of the speed's error, so an arm's changing gravity is
 * taken up as it goes): friction and back-EMF. The first two, one each way at the same speed, draw a
 * map of the volts that hold it everywhere in the window: the average of the two at each place, where
 * friction and back-EMF cancel. Then quick steps from the map's hold (inertia). Every sweep and step
 * ends before the far edge by dropping the volts its speed was taking (friction's share and back-EMF's)
 * and governing the speed to zero: the motor's back-EMF brakes it hard, and gravity there is held by
 * the volts the governor had found there. The volts never jump: when the hold comes from somewhere
 * new (a new place held, the map's first place drawn both ways) the governor takes up the difference.
 * Every moving stage watches the edge it is really heading for, and it stops on its own if the
 * mechanism goes the wrong way, runs away, speeds up while braking, or keeps going past its window.
 * Its brake mode is on for the test, so zero volts is a short circuit, as the model assumes.
 *
 * <p>The seesaw first pushes toward the middle of the travel (a mechanism resting on a stop has
 * nowhere to go the other way) and stops if it finds itself pushing into a stop.
 *
 * <p>A flywheel or roller: the voltage ramped up until near {@code vmax}, then down; then a step up,
 * a step down to a third, and a ramp to rest; both ways for a roller ({@code both_ways}).
 *
 * <p>Args: {@code system}, {@code vmax} (its units per second, or its speed units for a flywheel;
 * never above slothtune.json's), {@code sweep} (a pivot's or elevator's first sweep speed, a fraction
 * of {@code vmax}), {@code ramp} (a flywheel's, volts a second), {@code step} (volts), {@code volts_max},
 * {@code hold} (a guess at the volts that hold it, from its physics; 0 if none), {@code both_ways},
 * {@code stop_amps}. Channels: {@code pos}, {@code vel}, {@code cmd} (volts asked), {@code stage}
 * (see {@link Stage}), {@code loop} (loops since it started), {@code batt}, {@code spos}, {@code svel}
 * (the SPARK's own), and per motor {@code volts0..}, {@code bus0..}, {@code amps0..}. A row each loop,
 * right after its command (see {@link #samplesEachLoop}).
 */
final class SystemIdProcedure implements Procedure {
  /** The window: this fraction of the range inside each limit. */
  static final double MARGIN = 0.05;
  /** Past the limits by this much of the range, it stops. */
  static final double OVERRUN = 0.03;
  /** Faster than this times {@code vmax}, it stops. */
  static final double SPEED_STOP = 1.5;
  /** Status signals while it records, ms (the defaults are 20 ms and slower). */
  static final int SIGNAL_MS = 10;
  /** How fast the seesaw moves the voltage, volts a second. */
  static final double FIND_RATE = 1.0;
  /** The seesaw never asks more than this. */
  static final double FIND_CAP = 4.0;
  /** Still this long, it is still. */
  static final double STILL_S = 0.3;
  /** A hold that hasn't stopped it in this long has failed. */
  static final double HOLD_MAX_S = 3.0;
  /** The brake starts where it would be this far ahead at its speed now. */
  static final double LEAD_S = 0.3;
  /** The speed governor changes the volts at most this fast in a sweep, V/s. */
  static final double SWEEP_RATE = 2.0;
  /** And this fast braking. */
  static final double BRAKE_RATE = 8.0;
  /** Its gain: a speed error of this fraction of {@code vmax} changes the volts at {@link #SWEEP_RATE}. */
  static final double GOVERNOR_ERROR = 0.1;
  /** The first sweeps' speed, a fraction of {@code vmax}; the next two go twice as fast. */
  static final double SWEEP_FRACTION = 0.15;
  /** The hold map's resolution: this many places across the window. */
  static final int BINS = 40;
  /** Starting near an edge, the seesaw first takes it this fraction of the range clear of it. */
  static final double CLEAR = 0.1;
  /** Driven hard without moving this long: something holds it. */
  static final double STALL_S = 0.5;
  /** A flywheel's step lasts at most this long, seconds. */
  static final double STEP_MAX_S = 4.0;
  /** Motion in the seesaw counts once it lasts this many loops the same way (one count's dither doesn't). */
  static final int MOVING_LOOPS = 3;
  /** A sweep's speed is steady once within a quarter of its target this many loops in a row. */
  static final int STEADY_LOOPS = 5;
  /** Pushed this far past the hold guess into a stop, still, it stops: volts. */
  static final double INTO_STOP_V = 2.0;
  private static final int NO_KEY = Integer.MIN_VALUE;

  /** What it is doing, recorded as a number in {@code stage}. */
  enum Stage {
    FIND, HOLD, SWEEP, STEP, DONE
  }

  private record Leg(Stage type, double amount, int dir) {}

  private TunableSystem sys;
  private boolean positional;
  private final List<MotorGuard.MotorChannel> driven = new ArrayList<>();
  private final List<MotorGuard.MotorChannel> all = new ArrayList<>();
  private final List<Boolean> wasCoast = new ArrayList<>();
  private final List<Leg> legs = new ArrayList<>();
  private int leg;
  private Stage stage = Stage.FIND;
  private int phase;
  private double stageStart;
  private volatile double cmd;
  private volatile double stageCode;
  /** Loops since it started: in the simulator, its physics' own clock (a step each loop). */
  private volatile double loops;
  private double vmax;
  private double ramp;
  private double step;
  private double voltsMax;
  private double stopAmps;
  private double min;
  private double max;
  private double lo;
  private double hi;
  private int dir;
  private double uRamp;
  private double peak;
  /** The speed governor's integral, volts; and its gain, volts a second per unit a second. */
  private double uInt;
  private double kI;
  /** The hold guess it was given. */
  private double guess;
  /** Where the hold came from last loop ({@link #holdAt} sets {@code lastKey}), and what it was. */
  private int holdKey = NO_KEY;
  private int lastKey = NO_KEY;
  private double holdWas;
  /** Its speed when the brake began; NaN in a hold that isn't a brake. */
  private double brakeV = Double.NaN;
  private int steadyN;
  private int movingN;
  private double movingSign;
  /** The hold map: the volts asked at each place moving up, and down, at the first sweeps' speed. */
  private final double[] mapUp = new double[BINS];
  private final double[] mapDn = new double[BINS];
  private final int[] nUp = new int[BINS];
  private final int[] nDn = new int[BINS];
  /** Where it has been held still, and at what volts, until the map is drawn. */
  private final List<double[]> holds = new ArrayList<>();
  /** The band's edges: volts where motion starts from rest, up and down; NaN until found. */
  private double uUp = Double.NaN;
  private double uDn = Double.NaN;
  private double uHold;
  private double findDir = 1;
  private boolean wasStill;
  private double turnU;
  private double turnV = Double.NaN;
  private double stillSince = Double.NaN;
  private double stallSince = Double.NaN;
  private double lastT = Double.NaN;
  /** The last few readings (position, or a flywheel's speed) and their times. */
  private final double[] histT = new double[16];
  private final double[] histX = new double[16];
  private int histN;
  private String cut;

  @Override
  public String name() {
    return "system_id";
  }

  /** It commands motors: the deadman, enable and heartbeat rules apply. */
  @Override
  public boolean spinsWheels() {
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  /** Its subsystem would set the same motors every loop: the robot's code pauses while it runs. */
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
    return 0.3;  // the drivetrain is stopped for this test: any wheel speed past a crawl is a fault
  }

  private static List<MotorGuard.Motor> motors(TestContext ctx, TunableSystem s) {
    List<MotorGuard.Motor> out = new ArrayList<>();
    for (MotorGuard.Motor m : ctx.motors) {
      if (s.motors.contains(m.name)) {
        out.add(m);
      }
    }
    return out;
  }

  @Override
  public String validate(TestContext ctx) {
    TunableSystem s = SystemLimitsProcedure.pick(ctx);
    if (s == null) {
      return "No such system: the code registers none at that number.";
    }
    if (!(SystemStepProcedure.cap(ctx.args.get("vmax", 0, 0, 1e6), s.maxVelocity) > 0)) {
      return "Give the test a top speed (vmax): the Systems tab works it out from the mechanism's physics.";
    }
    if (s.kind.positional && !s.hasLimits()) {
      return "Set the limits of " + s.name + " first: move it by hand to both ends (Systems tab, Limits).";
    }
    List<MotorGuard.Motor> ms = motors(ctx, s);
    if (ms.isEmpty()) {
      return "None of " + s.name + "'s motors is watched by the motor guard: list them in .motors(...) by the names "
          + "watchMotors gives them.";
    }
    if (ms.stream().allMatch(m -> m.channel.follower())) {
      return "Every motor of " + s.name + " follows another: list its leader in .motors(...) too.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return 120;
  }

  /** A row each loop (see {@link #samplesEachLoop}). */
  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  /** Its speeds come from position differences: a row right after each loop's command. */
  @Override
  public boolean samplesEachLoop() {
    return true;
  }

  @Override
  public void start(TestContext ctx) {
    sys = SystemLimitsProcedure.pick(ctx);
    positional = sys.kind.positional;
    vmax = SystemStepProcedure.cap(ctx.args.get("vmax", 0, 0, 1e6), sys.maxVelocity);
    ramp = ctx.args.get("ramp", 1.0, 0.1, 3);
    step = ctx.args.get("step", positional ? 3 : 4, 0.5, 10);
    voltsMax = ctx.args.get("volts_max", 8, 1, 11);
    stopAmps = ctx.args.get("stop_amps", 40, 10, 80);
    uHold = ctx.args.get("hold", 0, -6, 6);
    boolean bothWays = ctx.args.get("both_ways", sys.kind == TunableSystem.Kind.ROLLER ? 1 : 0) > 0.5;
    legs.clear();
    if (positional) {
      min = sys.min;
      max = sys.max;
      double range = max - min;
      lo = min + MARGIN * range;
      hi = max - MARGIN * range;
      double frac = ctx.args.get("sweep", SWEEP_FRACTION, 0.05, 0.4);
      for (double f : new double[] {frac, frac, 2 * frac, 2 * frac}) {
        legs.add(new Leg(Stage.SWEEP, f, 0));
      }
      kI = SWEEP_RATE / (GOVERNOR_ERROR * vmax);
      java.util.Arrays.fill(mapUp, 0);
      java.util.Arrays.fill(mapDn, 0);
      java.util.Arrays.fill(nUp, 0);
      java.util.Arrays.fill(nDn, 0);
      holds.clear();
      for (double volts : new double[] {step, step, 1.5 * step, 1.5 * step}) {
        legs.add(new Leg(Stage.STEP, Math.min(volts, voltsMax), 0));
      }
    } else {
      for (int d : bothWays ? new int[] {1, -1} : new int[] {1}) {
        legs.add(new Leg(Stage.SWEEP, ramp, d));
        legs.add(new Leg(Stage.STEP, Math.min(step, voltsMax), d));
      }
    }
    driven.clear();
    all.clear();
    wasCoast.clear();
    int i = 0;
    List<MotorGuard.Motor> ordered = new ArrayList<>(motors(ctx, sys));
    // Leaders first: volts0 is always a motor it drives (a follower's, inverted, would read negated).
    ordered.sort((x, y) -> Boolean.compare(x.channel.follower(), y.channel.follower()));
    for (MotorGuard.Motor m : ordered) {
      MotorGuard.MotorChannel c = m.channel;
      all.add(c);
      boolean leads = !c.follower();
      if (leads) {
        driven.add(c);
      }
      // Each step on its own: one motor that throws must not leave the lists out of step for end().
      Boolean coast = null;
      try {
        c.fastSignals(SIGNAL_MS);
      } catch (RuntimeException e) {
        ctx.note("motor " + i + ": its signals couldn't be sped up: " + e.getMessage());
      }
      try {
        // Brake: zero volts then shorts the motor, which is what the model means by zero volts.
        coast = positional ? c.coast() : null;
        if (Boolean.TRUE.equals(coast)) {
          c.setCoast(false);
        }
      } catch (RuntimeException e) {
        ctx.note("motor " + i + ": its idle mode couldn't be set: " + e.getMessage());
      }
      wasCoast.add(coast);
      ctx.sampler.channel("volts" + i, c::appliedVolts)
          .channel("bus" + i, c::busVolts)
          .channel("amps" + i, c::amps);
      ctx.note("motor " + i + ": " + m.name + (leads ? " (driven)" : " (follows)"));
      i++;
    }
    MotorGuard.MotorChannel first = driven.get(0);
    ctx.sampler.channel("pos", () -> sys.position.getAsDouble())
        .channel("vel", () -> sys.velocity.getAsDouble())
        .channel("cmd", () -> cmd)
        .channel("stage", () -> stageCode)
        .channel("loop", () -> loops)
        .channel("batt", ctx.io::busVolts)
        .channel("spos", first::feedbackPosition)
        .channel("svel", first::feedbackVelocity);
    ctx.note("system: " + sys.name + " (" + sys.kind + ", " + sys.units + ")");
    ctx.meta("vmax", vmax);
    ctx.meta("ramp", ramp);
    ctx.meta("step", step);
    ctx.meta("volts_max", voltsMax);
    ctx.meta("signal_ms", SIGNAL_MS);
    if (positional) {
      ctx.meta("min", min);
      ctx.meta("max", max);
      ctx.meta("lo", lo);
      ctx.meta("hi", hi);
    }
    if (ctx.env == TestEnvironment.SIM) {
      ctx.note("In the simulator its physics run from the test while the robot's code is paused.");
    }
    leg = 0;
    loops = 0;
    histN = 0;
    lastT = Double.NaN;
    uUp = Double.NaN;
    uDn = Double.NaN;
    guess = uHold;
    holdKey = NO_KEY;
    brakeV = Double.NaN;
    movingN = 0;
    // Toward the middle first: resting on a stop, there is nowhere to go the other way.
    double p0 = positional ? sys.position.getAsDouble() : Double.NaN;
    findDir = Double.isFinite(p0) && p0 > (lo + hi) / 2 ? -1 : 1;
    wasStill = false;
    turnV = Double.NaN;
    cut = null;
    cmd = positional ? uHold : 0;
    enter(positional ? Stage.FIND : Stage.SWEEP, 0);
    if (!positional) {
      dir = legs.get(0).dir;
      uRamp = 0;
    }
    for (MotorGuard.MotorChannel c : driven) {
      if (!c.testVolts(cmd)) {
        cut = "Its controller can't be run by voltage from a test.";
      }
    }
  }

  private void enter(Stage s, double t) {
    stage = s;
    stageCode = s.ordinal();
    stageStart = t;
    phase = 0;
    stillSince = Double.NaN;
    stallSince = Double.NaN;
  }

  /** The next leg after a hold, or done. */
  private boolean nextLeg(TestContext ctx, double t, double p) {
    if (leg >= legs.size()) {
      enter(Stage.DONE, t);
      return true;
    }
    Leg l = legs.get(leg);
    enter(l.type, t);
    if (positional) {
      dir = p < (lo + hi) / 2 ? 1 : -1;  // toward the farther edge
      // From the volts that held it here (no jump), plus friction's share, so it moves at once.
      double held = cmd;
      holdKey = NO_KEY;
      uInt = held - hold(p) + dir * (uUp - uDn) / 2;
      brakeV = Double.NaN;
      steadyN = 0;
    } else {
      dir = l.dir;
      uRamp = 0;
    }
    return false;
  }

  private void remember(double t, double x) {
    if (histN == histT.length) {
      System.arraycopy(histT, 1, histT, 0, histN - 1);
      System.arraycopy(histX, 1, histX, 0, histN - 1);
      histN--;
    }
    histT[histN] = t;
    histX[histN] = x;
    histN++;
  }

  /** The slope of the remembered readings over the last {@code n} loops; 0 until two. */
  private double slope(int n) {
    if (histN < 2) {
      return 0;
    }
    int a = Math.max(0, histN - 1 - n);
    double dt = histT[histN - 1] - histT[a];
    return dt > 0 ? (histX[histN - 1] - histX[a]) / dt : 0;
  }

  /** How far apart the readings of the last {@code s} seconds are. */
  private double spread(double s) {
    double now = histT[histN - 1];
    double lo = Double.POSITIVE_INFINITY;
    double hi = Double.NEGATIVE_INFINITY;
    for (int k = histN - 1; k >= 0 && now - histT[k] <= s + 1e-9; k--) {
      lo = Math.min(lo, histX[k]);
      hi = Math.max(hi, histX[k]);
    }
    return hi - lo;
  }

  /** The reading {@code s} seconds ago (the oldest remembered if not that old). */
  private double ago(double s) {
    double now = histT[histN - 1];
    for (int k = histN - 1; k >= 0; k--) {
      if (now - histT[k] >= s) {
        return histX[k];
      }
    }
    return histX[0];
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    double dt = Double.isFinite(lastT) ? Math.max(1e-3, t - lastT) : 0.02;
    lastT = t;
    boolean done;
    double p = Double.NaN;
    if (positional) {
      p = sys.position.getAsDouble();
      if (!Double.isFinite(p)) {
        cut = "It can't read " + sys.name + "'s position: stopped.";
        done = false;
      } else {
        remember(t, p);
        done = positionStep(ctx, t, p, slope(5), slope(3), dt);
      }
    } else {
      double v = sys.velocity.getAsDouble();
      remember(t, Double.isFinite(v) ? v : 0);
      done = speedStep(ctx, t, Double.isFinite(v) ? v : 0, dt);
    }
    if (cut != null) {
      // Stopping: the hold now (0 V for a flywheel, or before the hold is known), not the last command.
      cmd = safeVolts(p);
    }
    cmd = Math.max(-voltsMax, Math.min(voltsMax, cmd));
    for (MotorGuard.MotorChannel c : driven) {
      c.testVolts(cmd);
    }
    if (ctx.env == TestEnvironment.SIM && sys.subsystem != null) {
      // The scheduler is paused, and with it the subsystem's simulation: run the physics here.
      sys.subsystem.simulationPeriodic();
    }
    loops++;
    return done;
  }

  /**
   * The volts that hold it at {@code p}: the map the first two sweeps drew, between its nearest places
   * either side, else the nearest place it was held still. Notes where it came from in {@code lastKey}.
   */
  double holdAt(double p) {
    int b = bin(p);
    int below = -1;
    int above = -1;
    for (int k = b; k >= 0 && below < 0; k--) {
      below = nUp[k] > 0 && nDn[k] > 0 ? k : -1;
    }
    for (int k = b; k < BINS && above < 0; k++) {
      above = nUp[k] > 0 && nDn[k] > 0 ? k : -1;
    }
    if (below >= 0 && above >= 0 && above != below) {
      lastKey = below * BINS + above;
      double f = (p - center(below)) / (center(above) - center(below));
      return mapAt(below) + Math.max(0, Math.min(1, f)) * (mapAt(above) - mapAt(below));
    }
    if (below >= 0 || above >= 0) {
      lastKey = BINS * BINS + (below >= 0 ? below : above);
      return mapAt(below >= 0 ? below : above);
    }
    int near = -1;
    for (int k = 0; k < holds.size(); k++) {
      if (near < 0 || Math.abs(holds.get(k)[0] - p) < Math.abs(holds.get(near)[0] - p)) {
        near = k;
      }
    }
    lastKey = near < 0 ? -1 : 2 * BINS * BINS + near;
    return near < 0 ? uHold : holds.get(near)[1];
  }

  /**
   * The hold at {@code p} for a governed stage. When it comes from somewhere new (a new place held,
   * the map's first place drawn both ways) the governor's integral takes up the difference, so the
   * volts never jump: a jump of a volt drove a strong arm into its stop.
   */
  private double hold(double p) {
    double h = holdAt(p);
    if (holdKey != NO_KEY && lastKey != holdKey) {
      uInt -= h - holdWas;
    }
    holdKey = lastKey;
    holdWas = h;
    return h;
  }

  /** What to send when it stops: the hold where it is, or 0 V (a flywheel, or the hold not yet found). */
  private double safeVolts(double p) {
    if (!positional || Double.isNaN(uUp) || Double.isNaN(uDn)) {
      return 0;
    }
    return Double.isFinite(p) ? holdAt(p) : uHold;
  }

  /**
   * Volts per unit of speed, from the map: at each place drawn both ways at the first sweeps' speed,
   * half the gap between up and down is friction's share and back-EMF's (gravity cancels). 0 until then.
   */
  private double kv() {
    double sum = 0;
    int n = 0;
    for (int k = 0; k < BINS; k++) {
      if (nUp[k] > 0 && nDn[k] > 0) {
        sum += (mapUp[k] / nUp[k] - mapDn[k] / nDn[k]) / 2;
        n++;
      }
    }
    double speed = legs.isEmpty() ? 0 : legs.get(0).amount * vmax;
    return n == 0 || !(speed > 0) ? 0 : Math.max(0, (sum / n - (uUp - uDn) / 2) / speed);
  }

  private int bin(double p) {
    return (int) Math.max(0, Math.min(BINS - 1, Math.floor((p - lo) / (hi - lo) * BINS)));
  }

  private double center(int b) {
    return lo + (b + 0.5) * (hi - lo) / BINS;
  }

  private double mapAt(int b) {
    return (mapUp[b] / nUp[b] + mapDn[b] / nDn[b]) / 2;
  }

  /** The speed governor: its integral chases {@code target}, never changing faster than {@code rate}. */
  private void govern(double target, double v, double dt, double rate) {
    uInt += Math.max(-rate, Math.min(rate, kI * (target - v))) * dt;
  }

  /**
   * A quick step's volts above the hold: what was asked, but never more than takes it to 60% of
   * {@code vmax} (the first two) or 90% (the last two), from the volts per speed the sweeps measured.
   * A fixed few volts would carry a light mechanism past its speed stop.
   */
  private double stepVolts(Leg l) {
    double kv = kv();
    if (!(kv > 0)) {
      return l.amount;
    }
    double frac = leg < legs.size() - 2 ? 0.6 : 0.9;
    return Math.min(l.amount, frac * kv * vmax + (uUp - uDn) / 2);
  }

  /**
   * Ends a sweep or step: the volts its speed was taking come off at once (friction's share and
   * back-EMF's in a sweep; the step's push in a step), leaving the gravity the governor had found
   * there, and the governor then takes it to rest. Never a hold measured somewhere else: past an
   * arm's top that pushed it on into its stop.
   */
  private boolean brake(double t, double p, double vq) {
    double target;
    if (stage == Stage.SWEEP) {
      target = cmd - Math.signum(vq) * ((uUp - uDn) / 2 + kv() * Math.abs(vq));
    } else {
      target = holdAt(p);
    }
    leg++;
    enter(Stage.HOLD, t);
    brakeV = Math.abs(vq);
    holdKey = NO_KEY;
    uInt = target - hold(p);
    cmd = target;
    return false;
  }

  /**
   * A moving stage's own checks: past its window and still going out, speeding up while braking, or
   * going the wrong way. Each means the volts it chose aren't stopping it, so the test stops.
   */
  private boolean runaway(double p, double vq, double vth, Leg l) {
    double range = max - min;
    double m2 = 0.5 * MARGIN * range;
    if ((p < lo - m2 && vq < -vth) || (p > hi + m2 && vq > vth)) {
      cut = String.format(Locale.ROOT, "%s kept going past the end of its test window (at %.3f %s): the volts "
          + "it chose didn't stop it. Stopped.", sys.name, sys.shown(p), sys.shownUnits());
      return true;
    }
    if (stage == Stage.HOLD && Double.isFinite(brakeV) && Math.abs(vq) > Math.max(1.25 * brakeV, brakeV + 0.05 * vmax)) {
      cut = String.format(Locale.ROOT, "%s sped up while braking (%.3f to %.3f %s/s): the volts that hold it there "
          + "are off. Stopped.", sys.name, sys.shown(brakeV), sys.shown(Math.abs(vq)), sys.shownUnits());
      return true;
    }
    if (l != null && stage == Stage.SWEEP) {
      if (dir * vq < -Math.max(0.1 * vmax, vth)) {
        cut = String.format(Locale.ROOT, "%s went the wrong way in a sweep (%.3f %s/s): stopped.", sys.name,
            sys.shown(Math.abs(vq)), sys.shownUnits());
        return true;
      }
      if (Math.abs(vq) > 2 * l.amount * vmax + vth) {
        cut = String.format(Locale.ROOT, "%s ran away in a sweep: %.3f %s/s, twice the speed it was held to. "
            + "Stopped.", sys.name, sys.shown(Math.abs(vq)), sys.shownUnits());
        return true;
      }
    }
    return false;
  }

  private boolean positionStep(TestContext ctx, double t, double p, double v, double vq, double dt) {
    double vth = 0.02 * vmax;
    boolean moving = Math.abs(v) > vth;
    boolean still = Math.abs(v) < vth / 2 && histN >= 3;
    double ts = t - stageStart;
    double range = max - min;
    if (p < min - OVERRUN * range || p > max + OVERRUN * range) {
      cut = String.format(Locale.ROOT, "%s went past its limits (%.3f, limits %.3f to %.3f %s): stopped.", sys.name,
          sys.shown(p), sys.shown(min), sys.shown(max), sys.shownUnits());
      return false;
    }
    if (Math.abs(v) > SPEED_STOP * vmax) {
      cut = String.format(Locale.ROOT, "%s moved at %.3f %s/s, faster than the test allows (%.3f): stopped.",
          sys.name, sys.shown(Math.abs(v)), sys.shownUnits(), sys.shown(vmax));
      return false;
    }
    switch (stage) {
      case FIND -> {
        if (histN < 3) {
          return false;  // not enough readings yet to tell still from moving
        }
        // Finer here: motion just starting at a band edge is slow, and the edge is read where it is seen.
        // It must last MOVING_LOOPS loops the same way: one encoder count's dither isn't motion.
        boolean stirring = Math.abs(v) > vth / 2 && Math.abs(vq) > vth / 2 && Math.signum(v) == Math.signum(vq);
        movingN = stirring ? (Math.signum(v) == movingSign ? movingN + 1 : 1) : 0;
        movingSign = Math.signum(v);
        moving = movingN >= MOVING_LOOPS;
        still = Math.abs(v) < vth / 4;
        if (moving && wasStill) {
          // Motion starting from rest, the voltage heading the same way: an edge of the band. The
          // speed reading spans five loops and must last three, so the voltage then was a little behind.
          double then = cmd - findDir * FIND_RATE * (0.06 + 0.02 * (MOVING_LOOPS - 1));
          if (v > 0 && findDir > 0 && Double.isNaN(uUp)) {
            uUp = then;
          } else if (v < 0 && findDir < 0 && Double.isNaN(uDn)) {
            uDn = then;
          }
        }
        if (moving && (wasStill || Double.isNaN(turnV))) {
          turnU = cmd;  // motion begins: how fast, and at what voltage
          turnV = Math.abs(v);
        }
        // Near an edge and heading away from it, it carries on until clear: an elevator resting on its
        // bottom stop has nowhere to go down to.
        boolean leaving = moving && (v > 0 ? p < lo + CLEAR * range : p > hi - CLEAR * range);
        if (leaving) {
          findDir = Math.signum(v);
        } else if (moving && Math.signum(v) != -findDir) {
          findDir = -Math.signum(v);  // turn against the motion
          turnU = cmd;
          turnV = Math.abs(v);
        } else if (moving && Math.abs(cmd - turnU) > 0.6 && Math.abs(v) > 1.5 * turnV + vth) {
          cut = String.format(Locale.ROOT, "Pushing %s %s moved it %s faster (%.2f V): its motor's inversion doesn't "
              + "match its position reading, or it needs more than that to hold it (give the test a hold guess). "
              + "Stopped.", sys.name, findDir > 0 ? "up" : "down", findDir > 0 ? "down" : "up", cmd);
          return false;
        }
        if (still) {
          wasStill = true;
        } else if (moving) {
          wasStill = false;
        }
        if (!Double.isNaN(uUp) && !Double.isNaN(uDn)) {
          if (uUp < uDn) {
            cut = String.format(Locale.ROOT, "%s moved up at %.2f V but down at %.2f V: positive volts move it the "
                + "wrong way for its position reading (check its motor's inversion). Stopped.", sys.name, uUp, uDn);
            return false;
          }
          uHold = (uUp + uDn) / 2;
          ctx.meta("u_up", uUp);
          ctx.meta("u_dn", uDn);
          ctx.meta("u_hold", uHold);
          holds.add(new double[] {p, uHold});
          cmd = uHold;
          enter(Stage.HOLD, t);
          brakeV = Double.NaN;
          holdKey = NO_KEY;
          uInt = cmd - hold(p);
          return false;
        }
        if (!leaving || Math.abs(v) < 0.1 * vmax) {
          cmd += findDir * FIND_RATE * dt;
        }
        // Pushing well past the guess toward a stop it is already beyond: it is on the stop.
        boolean intoStop = findDir > 0 ? p > hi : p < lo;
        stall(ctx, t, moving, intoStop && Math.abs(cmd - guess) > INTO_STOP_V);
        if (cut != null) {
          return false;
        }
        if (Math.abs(cmd) > Math.min(FIND_CAP, voltsMax)) {
          cut = String.format(Locale.ROOT, "%s didn't start moving %s by %.1f V: is it jammed, pushing into a stop "
              + "(its motor inverted?), or are these its motors? Stopped.", sys.name, findDir > 0 ? "up" : "down", cmd);
        } else if (ts > 25) {
          cut = "It took too long to find the volts that hold " + sys.name + " still: stopped.";
        } else if (Math.abs(v) > 0.25 * vmax) {
          cut = String.format(Locale.ROOT, "%s moved at %.3f %s/s while the test looked for the volts that hold it: "
              + "give the test a hold guess, or check its motor's inversion. Stopped.", sys.name,
              sys.shown(Math.abs(v)), sys.shownUnits());
        }
        return false;
      }
      case HOLD -> {
        // The hold there, and the governor taking the speed to zero: gravity the hold misjudged (an
        // arm's, away from where it was measured) is taken up as it goes.
        if (runaway(p, vq, vth, null)) {
          return false;
        }
        govern(0, vq, dt, BRAKE_RATE);
        cmd = hold(p) + uInt;
        // Settled: within a hair for the last STILL_S. Without friction (a simulated arm) the hold rocks a
        // little about its balance point and is never perfectly still.
        if (ts >= STILL_S && spread(STILL_S) <= 0.5 * vth * STILL_S) {
          holds.add(new double[] {p, cmd});
          uHold = cmd;
          return nextLeg(ctx, t, p);
        }
        if (ts > HOLD_MAX_S) {
          cut = String.format(Locale.ROOT, "%s wouldn't stay still at %.2f V: stopped.", sys.name, cmd);
        }
        return false;
      }
      case SWEEP, STEP -> {
        Leg l = legs.get(leg);
        if (runaway(p, vq, vth, l)) {
          return false;
        }
        if (stage == Stage.SWEEP) {
          // A governed speed, reached over half a second: the volts follow what holds it there.
          double target = dir * l.amount * vmax * Math.min(1, ts / 0.5);
          govern(target, vq, dt, SWEEP_RATE);
          cmd = hold(p) + uInt;
          // Steady: near its target for STEADY_LOOPS in a row, not just passing through it.
          steadyN = ts > 0.5 && Math.abs(vq - target) < 0.25 * Math.abs(target) ? steadyN + 1 : 0;
          boolean steady = steadyN >= STEADY_LOOPS;
          if (leg < 2 && steady) {
            int b = bin(p);  // the first two sweeps, one each way at the same speed: the hold map
            if (dir > 0) {
              mapUp[b] += cmd;
              nUp[b]++;
            } else {
              mapDn[b] += cmd;
              nDn[b]++;
            }
          }
        } else {
          cmd = holdAt(p) + dir * stepVolts(l);
        }
        // The edge it is really heading for: its leg's, or the other one if something carries it back.
        boolean ending = dir > 0 ? p + Math.max(0, vq) * LEAD_S >= hi : p + Math.min(0, vq) * LEAD_S <= lo;
        boolean backward = dir > 0 ? p + Math.min(0, vq) * LEAD_S <= lo : p + Math.max(0, vq) * LEAD_S >= hi;
        if (ending || backward || Math.abs(vq) > (stage == Stage.STEP ? 0.9 : 0.8) * vmax) {
          return brake(t, p, vq);
        }
        stall(ctx, t, moving, Math.abs(cmd - holdAt(p)) > 2);
        if (ts > 30) {
          cut = "A sweep across " + sys.name + "'s travel took over 30 s: stopped.";
        }
        return false;
      }
      default -> {
        return true;
      }
    }
  }

  /** Driven hard and not moving, or drawing past the stop current while slow: something holds it. */
  private void stall(TestContext ctx, double t, boolean moving, boolean pushing) {
    double amps = 0;
    for (MotorGuard.MotorChannel c : all) {
      double a = c.amps();
      if (Double.isFinite(a)) {
        amps = Math.max(amps, a);
      }
    }
    boolean stuck = !moving && (pushing || amps > stopAmps);
    stallSince = stuck ? (Double.isNaN(stallSince) ? t : stallSince) : Double.NaN;
    if (!Double.isNaN(stallSince) && t - stallSince >= STALL_S) {
      cut = String.format(Locale.ROOT, "%s didn't move with %.1f V (%.0f A): jammed, or something holds it. Stopped.",
          sys.name, cmd, amps);
    }
  }

  private boolean speedStep(TestContext ctx, double t, double v, double dt) {
    double vth = 0.02 * vmax;
    boolean moving = Math.abs(v) > vth;
    double ts = t - stageStart;
    if (Math.abs(v) > SPEED_STOP * vmax) {
      cut = String.format(Locale.ROOT, "%s reached %.0f %s, above the test's top speed: stopped.", sys.name,
          sys.shown(Math.abs(v)), sys.shownUnits());
      return false;
    }
    Leg l = leg < legs.size() ? legs.get(leg) : null;
    if (l == null) {
      cmd = 0;
      return true;
    }
    boolean steady = ts > 0.3 && Math.abs(v - ago(0.25)) < 0.01 * vmax;
    if (stage == Stage.SWEEP) {
      if (phase == 0) {
        uRamp += dir * l.amount * dt;  // up slowly, the speed following
        if (Math.abs(v) >= 0.85 * vmax || Math.abs(uRamp) >= voltsMax) {
          peak = Math.abs(uRamp);
          ctx.meta("peak_" + leg, peak);
          phase = 1;
        }
      } else if (phase == 1) {
        uRamp -= dir * l.amount * dt;  // and back down
        if (dir * uRamp <= 0) {
          uRamp = 0;
          phase = 2;
          stageStart = t;
        }
      } else if (!moving || ts > 3) {
        leg++;
        return nextLeg(ctx, t, Double.NaN);
      }
      cmd = uRamp;
    } else {
      double up = Math.min(l.amount, peak > 0 ? 0.7 * peak : l.amount);
      if (phase == 0) {
        cmd = dir * up;
        if (steady || ts > STEP_MAX_S || Math.abs(v) > 0.9 * vmax) {
          phase = 1;
          stageStart = t;
        }
      } else if (phase == 1) {
        cmd = dir * up / 3;
        if (steady || ts > STEP_MAX_S) {
          phase = 2;
          uRamp = cmd;
        }
      } else if (phase == 2) {
        uRamp -= dir * ramp * dt;
        if (dir * uRamp <= 0) {
          uRamp = 0;
          phase = 3;
          stageStart = t;
        }
        cmd = uRamp;
      } else {
        cmd = 0;
        if (!moving || ts > 3) {
          leg++;
          return nextLeg(ctx, t, Double.NaN);
        }
      }
    }
    stall(ctx, t, moving, Math.abs(cmd) > 2);
    return false;
  }

  @Override
  public String abortReason(TestContext ctx) {
    return cut;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    String what = switch (stage) {
      case FIND -> "finding the volts that hold it";
      case HOLD -> "holding";
      case SWEEP -> "slow sweep";
      case STEP -> "quick step";
      case DONE -> "done";
    };
    return String.format(Locale.ROOT, "%s: %s (%d of %d), %.2f V.", sys.name, what, Math.min(leg + 1, legs.size()),
        legs.size(), cmd);
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    try {
      // A pivot or elevator keeps its hold until its code is back; a flywheel coasts down.
      double last = safeVolts(positional ? sys.position.getAsDouble() : Double.NaN);
      cmd = last;
      for (MotorGuard.MotorChannel c : driven) {
        c.testVolts(last);
      }
      if (sys.stop != null) {
        sys.stop.run();
      } else if (sys.goal != null) {
        sys.goal.accept(positional ? sys.position.getAsDouble() : 0);
      }
    } finally {
      // Each motor on its own: one that throws must not leave the others on fast signals or in brake.
      for (int i = 0; i < all.size(); i++) {
        MotorGuard.MotorChannel c = all.get(i);
        try {
          if (i < wasCoast.size() && Boolean.TRUE.equals(wasCoast.get(i))) {
            c.setCoast(true);
          }
        } catch (RuntimeException e) {
          // Its idle mode stays brake until the robot restarts: safe.
        }
        try {
          c.fastSignals(0);
        } catch (RuntimeException e) {
          // Its signals stay fast until the robot restarts: more CAN traffic, nothing worse.
        }
      }
      stageCode = Stage.DONE.ordinal();
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return legs.isEmpty() ? 0 : Math.min(1.0, (double) leg / legs.size());
  }
}
