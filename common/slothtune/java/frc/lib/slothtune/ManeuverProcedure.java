package frc.lib.slothtune;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.util.Units;
import frc.lib.slothtune.ManeuverCatalog.Leg;
import frc.lib.slothtune.ManeuverCatalog.Maneuver;
import java.util.Arrays;
import java.util.List;

/**
 * Runs one maneuver from the {@link ManeuverCatalog} leg by leg, on the floor, through the
 * drivetrain's own closed loop, and reports where it should have finished against where the
 * odometry says it did: the 2026 closed-loop accuracy run.
 *
 * <p>The plan is laid out from where the robot stands at the start. Each leg is a trapezoid
 * profile (the straight test's) with feedback on the plan, each loop on the sensor suited to it, as
 * the 2026 robot's commands did:
 *
 * <ul>
 *   <li><b>A drive</b>: distance along the planned line and drift across it from the pose, heading
 *       held on the planned heading with the gyro. It ends when the pose says the leg is done.
 *   <li><b>A turn</b>: the gyro's rotation added up loop by loop (a 270 degree turn cannot be an
 *       absolute heading target: the short way round is 90), the center held on the planned corner.
 * </ul>
 *
 * <p>Closing on the plan, not on where the last leg happened to stop, is what an auto following a
 * path does, and it keeps the controller's own leftovers out of the result: at the end the pose
 * sits on the plan, and the only error left is the pose's own. Commands go through
 * {@link DrivetrainIO#driveRobotRelative}: YAGSL's own kinematics and velocity loops, never raw
 * volts.
 *
 * <p>So the pose will nearly always say it arrived: odometry measures itself. The laptop scores
 * the run against a tape measure a person enters (or AprilTags seen at both ends) and treats the
 * odometry's number as the controller's residual only.
 */
final class ManeuverProcedure implements Procedure {
  static final double ALIGN_S = 0.6;
  static final double AIM_S = 0.3;
  static final double PAUSE_S = 0.4;
  static final double FINAL_S = 1.0;
  static final double SETTLE_MAX_S = 1.5;
  static final int SETTLE_LOOPS = 10;
  static final double DRIVE_TOL_M = 0.01;
  static final double TURN_TOL_DEG = 0.25;
  /** Feedback gains: m/s per meter of along-track or cross-track error, rad/s per radian. */
  static final double K_ALONG = 2.0;
  static final double K_CROSS = 2.0;
  static final double K_HEADING = 2.0;
  static final double K_TURN = 3.0;
  /** Least correction outside tolerance, so the last centimeter is not approached forever. */
  static final double MIN_MPS = 0.03;
  static final double MIN_DPS = 2.0;
  /** Wheels driving this long with the pose standing still means nothing can steer the run. */
  static final double FROZEN_S = 0.75;
  /** The geofence sits this far beyond the furthest corner of the path. */
  static final double FENCE_SLACK_M = 0.4;

  private static final int AIM = 0;
  private static final int MOVE = 1;
  private static final int SETTLE = 2;
  private static final int PAUSE = 3;

  private Maneuver maneuver;
  private int index;
  private double speedMps;
  private double accel;
  private double turnDps;
  private double turnAccelDps2;
  private double radiusM;
  private double capMps;

  // The run.
  private int leg = -1; // -1 while aligning at the start; legs.size() for the final settle
  private int phase;
  private double phaseStartT;
  private double[] startPose;
  /** Where the current leg starts on the plan, in the start's frame: meters, and degrees unwrapped. */
  private double planX;
  private double planY;
  private double planDeg;
  private double gyroPrev = Double.NaN;
  /** The gyro's rotation since the start, added up loop by loop, degrees. */
  private double totalTurned;
  private int inTolerance;
  private boolean finished;
  private double[] residual;
  private boolean[] settled;
  private int legsDone;
  private double refX;
  private double refY;
  private double refTurned;
  private double refT;
  private String frozen;
  private double lastT;
  // leg, commanded vx, vy (m/s) and omega (rad/s), for the recording.
  private final SharedDoubles live = new SharedDoubles(4);

  @Override
  public String name() {
    return "maneuver";
  }

  @Override
  public boolean spinsWheels() {
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return true;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return env == TestEnvironment.FIELD;
  }

  /** Room beyond the path for the robot's own corners as it turns in place, meters. */
  static double marginM(double radiusM) {
    return Math.max(0.4, radiusM + 0.15);
  }

  private static String number(double v) {
    return v == Math.rint(v) && Math.abs(v) < 1e9 ? Long.toString((long) v) : Double.toString(v);
  }

  /** Picks the maneuver and the speeds from the arguments; a sentence if it can't. */
  private String pick(TestContext ctx) {
    List<Maneuver> all = ManeuverCatalog.all();
    maneuver = null;
    if (ctx.args.has("id")) {
      maneuver = ManeuverCatalog.byId(Math.round(ctx.args.get("id", -1)));
      if (maneuver == null) {
        return "No maneuver has that id in this robot code: the tool's catalog and the robot"
            + " library's differ. Update whichever is older.";
      }
    } else if (ctx.args.has("index")) {
      double v = ctx.args.get("index", -1);
      if (v != Math.rint(v) || v < 0 || v >= all.size()) {
        return String.format("No maneuver at index %s: there are %d, numbered 0 to %d.", number(v),
            all.size(), all.size() - 1);
      }
      maneuver = all.get((int) v);
    } else {
      return String.format("Pick a maneuver to run: its index, 0 to %d, or its id.", all.size() - 1);
    }
    index = all.indexOf(maneuver);
    radiusM = SpinProcedure.maxRadius(ctx.io);
    capMps = ctx.speedCapMps;
    speedMps = Math.min(ctx.args.get("speed", 1.0, 0.2, 4.0), ctx.speedCapMps);
    accel = ctx.args.get("accel", 1.0, 0.3, 3.0);
    // Turning in place the outermost wheel rolls at omega x radius: held to the same speed and
    // acceleration as a drive.
    turnDps = Math.min(ctx.args.get("turn_dps", 90, 20, 360), Math.toDegrees(speedMps / radiusM));
    turnAccelDps2 = Math.toDegrees(accel / radiusM);
    return null;
  }

  @Override
  public String validate(TestContext ctx) {
    String why = pick(ctx);
    if (why != null) {
      return why;
    }
    double[] e = ManeuverCatalog.extentM(maneuver.legs());
    double m = marginM(radiusM);
    double ahead = e[0] + m;
    double side = e[2] + m;
    if (ctx.spaceForwardM < ahead || ctx.spaceSideM < side) {
      return String.format("%s needs %.0f in of clear floor ahead and %.0f in to each side, and %.0f by"
              + " %.0f in is declared. Pick a smaller maneuver, or clear more floor.",
          maneuver.name(), Units.metersToInches(ahead), Units.metersToInches(side),
          Units.metersToInches(ctx.spaceForwardM), Units.metersToInches(ctx.spaceSideM));
    }
    return null;
  }

  @Override
  public double spaceBudgetM(TestContext ctx) {
    if (pick(ctx) != null) {
      return 0;
    }
    return ManeuverCatalog.extentM(maneuver.legs())[3] + FENCE_SLACK_M;
  }

  /** Seconds the profile of one leg takes. */
  private double profileS(Leg l) {
    return l.isTurn()
        ? StraightLineProcedure.profileSeconds(Math.abs(l.value()), turnDps, turnAccelDps2)
        : StraightLineProcedure.profileSeconds(Math.abs(l.value()), speedMps, accel);
  }

  @Override
  public double timeoutS(TestContext ctx) {
    if (pick(ctx) != null) {
      return 10;
    }
    double total = ALIGN_S + FINAL_S + 3;
    for (Leg l : maneuver.legs()) {
      total += AIM_S + profileS(l) + SETTLE_MAX_S + PAUSE_S;
    }
    return total;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  /** Distance covered {@code t} seconds into a trapezoid profile of length {@code d}. */
  static double profilePosition(double t, double d, double v, double a) {
    double total = StraightLineProcedure.profileSeconds(d, v, a);
    if (t <= 0) {
      return 0;
    }
    if (t >= total) {
      return d;
    }
    double peak = Math.min(v, Math.sqrt(a * d));
    double ramp = peak / a;
    if (t < ramp) {
      return 0.5 * a * t * t;
    }
    double braking = total - ramp;
    if (t < braking) {
      return 0.5 * a * ramp * ramp + peak * (t - ramp);
    }
    double left = total - t;
    return d - 0.5 * a * left * left;
  }

  static double wrapDeg(double deg) {
    return Math.IEEEremainder(deg, 360);
  }

  private static double clamp(double v, double limit) {
    return Math.max(-limit, Math.min(limit, v));
  }

  @Override
  public void start(TestContext ctx) {
    pick(ctx);
    List<Leg> legs = maneuver.legs();
    residual = new double[legs.size()];
    settled = new boolean[legs.size()];
    Arrays.fill(residual, Double.NaN);
    DrivetrainIO io = ctx.io;
    ctx.sampler
        .channel("leg", () -> live.get(0))
        .channel("cmd_vx", () -> live.get(1))
        .channel("cmd_vy", () -> live.get(2))
        .channel("cmd_omega", () -> live.get(3))
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .angle("heading", () -> io.pose()[2])
        .angle("gyro", io::headingDeg)
        .channel("vx_vision", () -> visionAxis(ctx, 0))
        .channel("vy_vision", () -> visionAxis(ctx, 1))
        .channel("vdeg_vision", () -> visionAxis(ctx, 2))
        .channel("vbus", io::busVolts);
    for (int i = 0; i < io.moduleCount(); i++) {
      final int m = i;
      String p = "m" + m + ".";
      ctx.sampler.channel(p + "v", () -> io.driveMps(m)).angle(p + "steer", () -> io.steerDeg(m));
    }
    live.set(0, -1);
    Pose2d expected = ManeuverCatalog.expectedPose(new Pose2d(), legs);
    double[] extent = ManeuverCatalog.extentM(legs);
    ctx.meta("maneuver_index", index);
    ctx.meta("maneuver_id", maneuver.id());
    ctx.meta("family", maneuver.family().ordinal());
    ctx.meta("returns", maneuver.returnsToStart() ? 1 : 0);
    ctx.meta("legs", legs.size());
    for (int i = 0; i < legs.size(); i++) {
      ctx.meta("leg" + i + "_turn", legs.get(i).isTurn() ? 1 : 0);
      ctx.meta("leg" + i + "_value", legs.get(i).value());
    }
    ctx.meta("expected_x", expected.getX());
    ctx.meta("expected_y", expected.getY());
    ctx.meta("expected_deg", expected.getRotation().getDegrees());
    ctx.meta("total_m", maneuver.totalDistanceM());
    ctx.meta("turn_total_deg", maneuver.totalTurnDeg());
    ctx.meta("budget_m", maneuver.budgetM());
    ctx.meta("extent_ahead_m", extent[0]);
    ctx.meta("extent_side_m", extent[2]);
    ctx.meta("speed", speedMps);
    ctx.meta("accel", accel);
    ctx.meta("turn_dps", turnDps);
    ctx.meta("drive_tol_m", DRIVE_TOL_M);
    ctx.meta("turn_tol_deg", TURN_TOL_DEG);
    ctx.note("Maneuver " + maneuver.name() + " (" + index + " of " + ManeuverCatalog.all().size()
        + "): " + maneuver.description() + ".");
    if (!ctx.visionInUse) {
      ctx.note("No AprilTag ground truth: mark the floor at the robot's center at the start, then measure"
          + " where its center stopped (forward along the starting direction, and to the left) and enter"
          + " it in the tool. The odometry steered the run, so it cannot grade it.");
    }
  }

  private static double visionAxis(TestContext ctx, int axis) {
    double[] p = ctx.visionPose == null ? null : ctx.visionPose.get();
    return p == null || p.length <= axis ? Double.NaN : p[axis];
  }

  /** The pose's position in the start's frame: forward and left of where the run began, meters. */
  private double[] inStartFrame(double[] pose) {
    double h0 = Math.toRadians(startPose[2]);
    double dx = pose[0] - startPose[0];
    double dy = pose[1] - startPose[1];
    return new double[] {dx * Math.cos(h0) + dy * Math.sin(h0), -dx * Math.sin(h0) + dy * Math.cos(h0)};
  }

  /** Points every wheel for the next leg, standing still: along the line, or along its circle. */
  private void aim(DrivetrainIO io, Leg l) {
    double flip = l.value() < 0 ? 180 : 0;
    for (int m = 0; m < io.moduleCount(); m++) {
      double angle = l.isTurn() ? SpinFeedforwardProcedure.tangentDeg(io.moduleLocationM(m)) : 0;
      io.setModuleState(m, 0, angle + flip);
    }
    command(io, 0, 0, 0, false);
  }

  /** Every wheel stopped where it points. */
  private void hold(DrivetrainIO io) {
    for (int m = 0; m < io.moduleCount(); m++) {
      io.setModuleState(m, 0, io.steerDeg(m));
    }
    command(io, 0, 0, 0, false);
  }

  /**
   * One chassis command, robot-relative, scaled down if any wheel would pass the speed cap, and
   * recorded.
   */
  private void command(DrivetrainIO io, double vx, double vy, double omega, boolean send) {
    double wheel = Math.hypot(vx, vy) + Math.abs(omega) * radiusM;
    if (wheel > capMps && wheel > 0) {
      double k = capMps / wheel;
      vx *= k;
      vy *= k;
      omega *= k;
    }
    live.set(1, vx);
    live.set(2, vy);
    live.set(3, omega);
    if (send) {
      io.driveRobotRelative(vx, vy, omega);
    }
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    DrivetrainIO io = ctx.io;
    double[] pose = io.pose();
    double gyro = io.headingDeg();
    totalTurned += Double.isNaN(gyroPrev) ? 0 : wrapDeg(gyro - gyroPrev);
    gyroPrev = gyro;
    lastT = t;
    List<Leg> legs = maneuver.legs();

    if (leg < 0) {
      if (!legs.isEmpty()) {
        aim(io, legs.get(0));
      }
      if (t >= ALIGN_S) {
        // The plan is laid out from here: standing still, wheels pointed.
        startPose = pose.clone();
        totalTurned = 0;
        leg = 0;
        phase = AIM;
        phaseStartT = t;
        live.set(0, 0);
      }
      return false;
    }
    if (leg >= legs.size()) {
      hold(io);
      if (t - phaseStartT >= FINAL_S) {
        finished = true;
        return true;
      }
      return false;
    }

    Leg l = legs.get(leg);
    double into = t - phaseStartT;
    if (phase == AIM) {
      aim(io, l);
      if (into >= AIM_S) {
        phase = MOVE;
        phaseStartT = t;
        inTolerance = 0;
        refX = pose[0];
        refY = pose[1];
        refTurned = totalTurned;
        refT = t;
      }
      return false;
    }
    if (phase == PAUSE) {
      hold(io);
      if (into >= PAUSE_S) {
        // The next leg starts where this one should have ended.
        if (l.isTurn()) {
          planDeg += l.value();
        } else {
          planX += l.value() * Math.cos(Math.toRadians(planDeg));
          planY += l.value() * Math.sin(Math.toRadians(planDeg));
        }
        leg++;
        phase = AIM;
        phaseStartT = t;
        live.set(0, leg);
      }
      return false;
    }

    // MOVE, then SETTLE once the profile has run out.
    double profile = profileS(l);
    if (phase == MOVE && into >= profile) {
      phase = SETTLE;
      phaseStartT = t;
      into = 0;
    }
    double tProfile = phase == MOVE ? into : profile;
    double[] s = inStartFrame(pose);
    double error = l.isTurn() ? turn(io, l, tProfile, s) : drive(io, l, tProfile, s);
    watchFrozen(io, pose, t);
    if (phase == SETTLE) {
      double tol = l.isTurn() ? TURN_TOL_DEG : DRIVE_TOL_M;
      inTolerance = Math.abs(error) <= tol ? inTolerance + 1 : 0;
      if (inTolerance >= SETTLE_LOOPS || into >= SETTLE_MAX_S) {
        residual[leg] = error;
        settled[leg] = inTolerance >= SETTLE_LOOPS;
        legsDone = leg + 1;
        phase = PAUSE;
        phaseStartT = t;
        hold(io);
      }
    }
    return false;
  }

  /**
   * A drive leg's command for this loop, from the robot's position in the start's frame; returns
   * the distance still to go along the planned line, meters.
   */
  private double drive(DrivetrainIO io, Leg l, double tProfile, double[] s) {
    double d = l.value();
    double dir = Math.signum(d);
    double dist = Math.abs(d);
    double line = Math.toRadians(planDeg);
    double ux = Math.cos(line);
    double uy = Math.sin(line);
    double dx = s[0] - planX;
    double dy = s[1] - planY;
    double along = dx * ux + dy * uy;
    double cross = -dx * uy + dy * ux;
    double remaining = d - along;
    double vAlong;
    if (phase == MOVE) {
      double ref = dir * profilePosition(tProfile, dist, speedMps, accel);
      double vRef = dir * StraightLineProcedure.profileSpeed(tProfile, dist, speedMps, accel);
      vAlong = vRef + clamp(K_ALONG * (ref - along), 0.5 * speedMps);
    } else {
      vAlong = clamp(K_ALONG * remaining, 0.5 * speedMps);
      if (Math.abs(remaining) <= DRIVE_TOL_M) {
        vAlong = 0;
      } else if (Math.abs(vAlong) < MIN_MPS) {
        vAlong = Math.copySign(MIN_MPS, remaining);
      }
    }
    double vCross = clamp(-K_CROSS * cross, 0.5 * speedMps);
    double omega = clamp(-K_HEADING * Math.toRadians(totalTurned - planDeg), 0.5 * Math.toRadians(turnDps));
    // The line's frame to the robot's: rotate by the line's heading less the robot's.
    double rel = line - Math.toRadians(totalTurned);
    double vx = vAlong * Math.cos(rel) - vCross * Math.sin(rel);
    double vy = vAlong * Math.sin(rel) + vCross * Math.cos(rel);
    command(io, vx, vy, omega, true);
    return remaining;
  }

  /**
   * A turn leg's command for this loop, the center held on the planned corner; returns the
   * rotation still to go, degrees.
   */
  private double turn(DrivetrainIO io, Leg l, double tProfile, double[] s) {
    double want = l.value();
    double dir = Math.signum(want);
    double mag = Math.abs(want);
    double remaining = planDeg + want - totalTurned;
    double dps;
    if (phase == MOVE) {
      double ref = planDeg + dir * profilePosition(tProfile, mag, turnDps, turnAccelDps2);
      double wRef = dir * StraightLineProcedure.profileSpeed(tProfile, mag, turnDps, turnAccelDps2);
      dps = wRef + clamp(K_TURN * (ref - totalTurned), 0.5 * turnDps);
    } else {
      dps = clamp(K_TURN * remaining, 0.5 * turnDps);
      if (Math.abs(remaining) <= TURN_TOL_DEG) {
        dps = 0;
      } else if (Math.abs(dps) < MIN_DPS) {
        dps = Math.copySign(MIN_DPS, remaining);
      }
    }
    double fx = clamp(-K_ALONG * (s[0] - planX), 0.25 * speedMps);
    double fy = clamp(-K_ALONG * (s[1] - planY), 0.25 * speedMps);
    double h = Math.toRadians(totalTurned);
    double vx = fx * Math.cos(h) + fy * Math.sin(h);
    double vy = -fx * Math.sin(h) + fy * Math.cos(h);
    command(io, vx, vy, Math.toRadians(dps), true);
    return remaining;
  }

  /** Wheels driving while the pose stands still: the run is steering on nothing. */
  private void watchFrozen(DrivetrainIO io, double[] pose, double t) {
    double wheels = 0;
    for (int m = 0; m < io.moduleCount(); m++) {
      wheels += Math.abs(io.driveMps(m));
    }
    wheels /= Math.max(1, io.moduleCount());
    boolean moved = Math.hypot(pose[0] - refX, pose[1] - refY) > 0.02
        || Math.abs(totalTurned - refTurned) > 2.0;
    if (wheels < 0.2 || moved) {
      refX = pose[0];
      refY = pose[1];
      refTurned = totalTurned;
      refT = t;
    } else if (t - refT > FROZEN_S && frozen == null) {
      frozen = String.format("The robot's pose stopped changing while its wheels drove at %.1f ft/s: the"
          + " odometry, or a robot that is stuck. Nothing could steer the run, so it stopped.",
          Units.metersToFeet(wheels));
    }
  }

  @Override
  public String abortReason(TestContext ctx) {
    return frozen;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    if (maneuver == null || leg < 0) {
      return null;
    }
    int n = maneuver.legs().size();
    if (leg >= n) {
      return String.format("All %d legs done: standing still while it measures where it ended.", n);
    }
    return String.format("Leg %d of %d: %s%s.", leg + 1, n, maneuver.legs().get(leg),
        phase == SETTLE ? ", settling" : "");
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    command(ctx.io, 0, 0, 0, false);
    ctx.io.stop();
    if (maneuver == null || residual == null) {
      return;
    }
    for (int i = 0; i < residual.length; i++) {
      ctx.meta("leg" + i + "_residual", residual[i]);
      ctx.meta("leg" + i + "_settled", settled[i] ? 1 : 0);
    }
    ctx.meta("legs_done", legsDone);
    ctx.meta("complete", finished ? 1 : 0);
    if (startPose == null) {
      return;
    }
    double[] p = ctx.io.pose();
    double[] s = inStartFrame(p);
    double eh = wrapDeg(p[2] - startPose[2]);
    ctx.meta("end_x", s[0]);
    ctx.meta("end_y", s[1]);
    ctx.meta("end_deg", eh);
    ctx.meta("gyro_turned_deg", totalTurned);
    ctx.meta("end_t", lastT);
    Pose2d expected = ManeuverCatalog.expectedPose(new Pose2d(), maneuver.legs());
    ctx.note(String.format("Planned end: %.1f in forward, %.1f in left, facing %+.1f deg. Odometry's end:"
            + " %.1f in, %.1f in, %+.1f deg.",
        Units.metersToInches(expected.getX()), Units.metersToInches(expected.getY()),
        expected.getRotation().getDegrees(), Units.metersToInches(s[0]), Units.metersToInches(s[1]), eh));
  }

  @Override
  public double progress(TestContext ctx, double t) {
    if (maneuver == null || leg < 0) {
      return 0;
    }
    return Math.min(1, (leg + (leg < maneuver.legs().size() && phase >= SETTLE ? 0.75 : 0.25))
        / (maneuver.legs().size() + 0.5));
  }
}
