package frc.lib.slothtune;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Transform2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.util.Units;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The accuracy maneuvers, and the geometry that says where each one should finish.
 *
 * <p>Ported from the 2026 robot's {@code CalibrationManeuvers}. A maneuver is a list of legs: drive
 * a signed distance along the current heading, or turn a signed angle in place. Because the
 * finishing pose follows exactly from the legs, every run has a plan to compare against, and the
 * accuracy requirement, 1 in of error for every 10 ft driven, is judged against it.
 *
 * <p>Three families, each answering a different question:
 *
 * <ul>
 *   <li><b>Permutations</b>: drive, turn, drive. {10 ft, 5 ft} out, {90, 270} degrees, {left,
 *       right}, then 10 ft {forward, reverse}. A turn accurate one way and not the other, or a
 *       reverse leg with more backlash than forward, shows only when both variants are run.
 *   <li><b>Out and back, same path</b>: the robot retraces its way home. A wheel-scale error
 *       largely <em>cancels</em> here (both legs wrong by the same share, in opposite directions),
 *       so what survives is heading error, backlash and hysteresis. A small closure here does not
 *       mean the wheels are calibrated.
 *   <li><b>Out and back, different path</b>: home by another route, so scale and heading errors
 *       add up instead of cancelling: the closest thing to a real autonomous path.
 * </ul>
 *
 * <p>Pure geometry, no hardware, so the expected poses are unit tested. The laptop tool keeps a
 * copy of this list ({@code maneuvers.py}); a run asked for by {@link #id} refuses when the two
 * differ, rather than running the wrong maneuver.
 */
public final class ManeuverCatalog {

  /** Ten feet, the distance the accuracy requirement is written against. */
  public static final double TEN_FEET_M = Units.feetToMeters(10);

  public static final double FIVE_FEET_M = Units.feetToMeters(5);

  /** The accuracy requirement as a fraction of the distance driven: 1 in per 10 ft. */
  public static final double BUDGET_PER_M = 1.0 / 120.0;

  private ManeuverCatalog() {}

  /** What a leg does. */
  public enum LegType {
    /** Drive along the current heading. Value is signed meters; negative reverses. */
    DRIVE,
    /** Turn in place. Value is signed degrees; positive is counter-clockwise (left). */
    TURN
  }

  /** The three families, in catalog order. */
  public enum Family {
    PERMUTATION,
    SAME_PATH,
    DIFFERENT_PATH
  }

  /**
   * One step of a maneuver.
   *
   * @param type whether it drives or turns
   * @param value signed meters for a drive, signed degrees for a turn
   */
  public record Leg(LegType type, double value) {
    public static Leg drive(double meters) {
      return new Leg(LegType.DRIVE, meters);
    }

    public static Leg turn(double degrees) {
      return new Leg(LegType.TURN, degrees);
    }

    public boolean isTurn() {
      return type == LegType.TURN;
    }

    @Override
    public String toString() {
      return isTurn()
          ? String.format("turn %+.0f deg", value)
          : String.format("drive %+.1f in", Units.metersToInches(value));
    }
  }

  /**
   * A named sequence of legs.
   *
   * @param name short identifier, also the log key; never changes once published
   * @param description what it drives, for a person
   * @param family which question it answers
   * @param legs the steps, in order
   */
  public record Maneuver(String name, String description, Family family, List<Leg> legs) {
    public Maneuver {
      legs = List.copyOf(legs);
    }

    /** Whether it should finish where it began, so the closure error is the measure. */
    public boolean returnsToStart() {
      return family != Family.PERMUTATION;
    }

    /** Distance driven, ignoring direction, meters. */
    public double totalDistanceM() {
      double total = 0;
      for (Leg leg : legs) {
        if (!leg.isTurn()) {
          total += Math.abs(leg.value());
        }
      }
      return total;
    }

    /** Every turn added up, signed, degrees: 360 for a left-hand square. */
    public double totalTurnDeg() {
      double total = 0;
      for (Leg leg : legs) {
        if (leg.isTurn()) {
          total += leg.value();
        }
      }
      return total;
    }

    /** The error allowed at the end: 1 in for every 10 ft driven, meters. */
    public double budgetM() {
      return totalDistanceM() * BUDGET_PER_M;
    }

    public long id() {
      return ManeuverCatalog.id(name);
    }
  }

  private static final List<Maneuver> ALL = build();

  /** Every maneuver: the permutations, then the same-path returns, then the different-path ones. */
  public static List<Maneuver> all() {
    return ALL;
  }

  /** The maneuver at a catalog index, or null. */
  public static Maneuver byIndex(int index) {
    return index >= 0 && index < ALL.size() ? ALL.get(index) : null;
  }

  /** The maneuver with this {@link #id}, or null. */
  public static Maneuver byId(long id) {
    for (Maneuver m : ALL) {
      if (m.id() == id) {
        return m;
      }
    }
    return null;
  }

  /**
   * A number for a name that the laptop computes the same way (maneuvers.py), so it can ask for a
   * maneuver by what it is rather than where it sits in the list. Below 2^31, so a double carries it
   * exactly.
   */
  public static long id(String name) {
    long h = 0;
    for (int i = 0; i < name.length(); i++) {
      h = (h * 131 + name.charAt(i)) % 1_000_000_007L;
    }
    return h;
  }

  /**
   * Where a list of legs should finish, starting from {@code start}. Composed as rigid transforms,
   * so it is exact: a drive moves along the <em>current</em> heading, a turn rotates in place.
   */
  public static Pose2d expectedPose(Pose2d start, List<Leg> legs) {
    Pose2d pose = start;
    for (Leg leg : legs) {
      if (leg.isTurn()) {
        pose = pose.plus(new Transform2d(new Translation2d(), Rotation2d.fromDegrees(leg.value())));
      } else {
        pose = pose.plus(new Transform2d(new Translation2d(leg.value(), 0), new Rotation2d()));
      }
    }
    return pose;
  }

  /**
   * Legs that retrace {@code legs} exactly: the order reversed and every value negated, so the
   * robot backs along the same line rather than turning around, and ends facing the way it began.
   */
  public static List<Leg> retraceLegs(List<Leg> legs) {
    List<Leg> back = new ArrayList<>();
    for (int i = legs.size() - 1; i >= 0; i--) {
      Leg leg = legs.get(i);
      back.add(new Leg(leg.type(), -leg.value()));
    }
    return back;
  }

  /**
   * How far the robot's center goes from where it starts, meters, with the start at the origin
   * facing +x: {@code {ahead, behind, to either side, from the start}}. Drives are straight lines
   * and turns happen in place, so the corners of the path bound it.
   */
  public static double[] extentM(List<Leg> legs) {
    double ahead = 0;
    double behind = 0;
    double side = 0;
    double radius = 0;
    Pose2d pose = new Pose2d();
    for (Leg leg : legs) {
      pose = expectedPose(pose, List.of(leg));
      ahead = Math.max(ahead, pose.getX());
      behind = Math.max(behind, -pose.getX());
      side = Math.max(side, Math.abs(pose.getY()));
      radius = Math.max(radius, pose.getTranslation().getNorm());
    }
    return new double[] {ahead, behind, side, radius};
  }

  // ------------------------------------------------------------------ family 1: drive, turn, drive

  /**
   * Every combination of outbound distance, turn and final leg direction: {10 ft, 5 ft} out, times
   * {90, 270} degrees, times {left, right}, times 10 ft {forward, reverse}. Sixteen.
   */
  public static List<Maneuver> permutations() {
    List<Maneuver> out = new ArrayList<>();
    double[] outbound = {TEN_FEET_M, FIVE_FEET_M};
    String[] outboundNames = {"10ft", "5ft"};
    String[] outboundWords = {"10 ft", "5 ft"};
    double[] turns = {90, 270};
    // Positive is counter-clockwise, which is left.
    int[] signs = {1, -1};
    String[] sideNames = {"L", "R"};
    String[] sideWords = {"left", "right"};
    double[] last = {TEN_FEET_M, -TEN_FEET_M};
    String[] lastNames = {"fwd10ft", "rev10ft"};
    String[] lastWords = {"10 ft forward", "10 ft in reverse"};
    for (int d = 0; d < outbound.length; d++) {
      for (double turn : turns) {
        for (int s = 0; s < signs.length; s++) {
          for (int f = 0; f < last.length; f++) {
            String name = "P_" + outboundNames[d] + "_" + sideNames[s] + (int) turn + "_" + lastNames[f];
            String description = "Drive " + outboundWords[d] + ", turn " + (int) turn + " deg "
                + sideWords[s] + ", then " + lastWords[f];
            out.add(new Maneuver(name, description, Family.PERMUTATION,
                List.of(Leg.drive(outbound[d]), Leg.turn(turn * signs[s]), Leg.drive(last[f]))));
          }
        }
      }
    }
    return out;
  }

  // ------------------------------------------------------------------ family 2: out and back, same path

  /**
   * Out, then back home along the identical path. The closure error is the measure, and it
   * isolates heading error, backlash and hysteresis: a wheel-scale error largely cancels.
   */
  public static List<Maneuver> outAndBackSamePath() {
    List<Maneuver> out = new ArrayList<>();
    // No turning at all: any closure error is drive-side hysteresis or heading drift.
    out.add(new Maneuver("OB_same_straight10ft",
        "Out 10 ft forward, back 10 ft in reverse along the same line", Family.SAME_PATH,
        List.of(Leg.drive(TEN_FEET_M), Leg.drive(-TEN_FEET_M))));
    out.add(new Maneuver("OB_same_straight5ft",
        "Out 5 ft forward, back 5 ft in reverse along the same line", Family.SAME_PATH,
        List.of(Leg.drive(FIVE_FEET_M), Leg.drive(-FIVE_FEET_M))));
    // The same physical path, both legs driven forward: separates reverse-direction effects.
    out.add(new Maneuver("OB_same_turnaround10ft",
        "Out 10 ft, turn 180 deg, drive 10 ft forward, turn 180 deg back", Family.SAME_PATH,
        List.of(Leg.drive(TEN_FEET_M), Leg.turn(180), Leg.drive(TEN_FEET_M), Leg.turn(180))));
    // An L out and the same L retraced back.
    List<Leg> shape = List.of(Leg.drive(TEN_FEET_M), Leg.turn(90), Leg.drive(FIVE_FEET_M));
    List<Leg> both = new ArrayList<>(shape);
    both.addAll(retraceLegs(shape));
    out.add(new Maneuver("OB_same_L_retrace",
        "L-shape out (10 ft, left 90 deg, 5 ft), then the identical L retraced back to the start",
        Family.SAME_PATH, both));
    return out;
  }

  // ------------------------------------------------------------------ family 3: out and back, different path

  /**
   * Back to the start by a different route, so scale and heading errors add up instead of
   * cancelling. The harder test, and the closest to an autonomous path.
   */
  public static List<Maneuver> outAndBackDifferentPath() {
    List<Maneuver> out = new ArrayList<>();
    double f = FIVE_FEET_M;
    double t = TEN_FEET_M;
    // Four equal legs and four left turns close perfectly: what it misses by is the accumulated
    // per-turn and per-leg error.
    out.add(new Maneuver("OB_diff_square5ft",
        "5 ft square, four left turns: the closure is the accumulated turn error", Family.DIFFERENT_PATH,
        List.of(Leg.drive(f), Leg.turn(90), Leg.drive(f), Leg.turn(90),
            Leg.drive(f), Leg.turn(90), Leg.drive(f), Leg.turn(90))));
    // The same square the other way round, to expose a turn error that depends on direction.
    out.add(new Maneuver("OB_diff_square5ft_right",
        "5 ft square clockwise, four right turns: compare with the left-hand square", Family.DIFFERENT_PATH,
        List.of(Leg.drive(f), Leg.turn(-90), Leg.drive(f), Leg.turn(-90),
            Leg.drive(f), Leg.turn(-90), Leg.drive(f), Leg.turn(-90))));
    out.add(new Maneuver("OB_diff_rectangle",
        "Rectangle with left turns: 10 ft out, 5 ft across, 10 ft back, 5 ft across", Family.DIFFERENT_PATH,
        List.of(Leg.drive(t), Leg.turn(90), Leg.drive(f), Leg.turn(90),
            Leg.drive(t), Leg.turn(90), Leg.drive(f), Leg.turn(90))));
    // The 2026 catalog called this "mixed turns", but its legs (kept, so old logs still compare)
    // are the rectangle with four right turns: the mirror of the one above.
    out.add(new Maneuver("OB_diff_mixed_turns",
        "Rectangle with right turns: 10 ft out, 5 ft across, 10 ft back, 5 ft across", Family.DIFFERENT_PATH,
        List.of(Leg.drive(t), Leg.turn(-90), Leg.drive(f), Leg.turn(-90),
            Leg.drive(t), Leg.turn(-90), Leg.drive(f), Leg.turn(-90))));
    // Turns that are not right angles, so a per-degree turn error shows at another size.
    out.add(new Maneuver("OB_diff_triangle",
        "Equilateral triangle with 5 ft sides and 120 deg left turns", Family.DIFFERENT_PATH,
        List.of(Leg.drive(f), Leg.turn(120), Leg.drive(f), Leg.turn(120), Leg.drive(f), Leg.turn(120))));
    return out;
  }

  private static List<Maneuver> build() {
    List<Maneuver> all = new ArrayList<>();
    all.addAll(permutations());
    all.addAll(outAndBackSamePath());
    all.addAll(outAndBackDifferentPath());
    return Collections.unmodifiableList(all);
  }

  /** Distance driven across a set of maneuvers, meters: how much time and floor a session needs. */
  public static double totalDistanceM(List<Maneuver> maneuvers) {
    double total = 0;
    for (Maneuver m : maneuvers) {
      total += m.totalDistanceM();
    }
    return total;
  }
}
