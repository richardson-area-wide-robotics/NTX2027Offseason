package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import frc.lib.slothtune.ManeuverCatalog.Family;
import frc.lib.slothtune.ManeuverCatalog.Leg;
import frc.lib.slothtune.ManeuverCatalog.Maneuver;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

/**
 * The maneuver catalog and the geometry that scores it, ported with the 2026 robot's tests. The
 * expected pose is the plan every run is judged against, so an error here would mis-score every
 * maneuver on the floor.
 */
class ManeuverCatalogTest {
  private static final double TEN_FT = ManeuverCatalog.TEN_FEET_M;
  private static final double FIVE_FT = ManeuverCatalog.FIVE_FEET_M;

  private static Pose2d end(Leg... legs) {
    return ManeuverCatalog.expectedPose(new Pose2d(), List.of(legs));
  }

  private static Maneuver named(String name) {
    return ManeuverCatalog.all().stream().filter(m -> m.name().equals(name)).findFirst().orElseThrow();
  }

  // ------------------------------------------------------------------ geometry

  @Test
  void tenFeetIs3048MillimetersAndFiveIsHalf() {
    assertEquals(3.048, TEN_FT, 1e-9);
    assertEquals(1.524, FIVE_FT, 1e-9);
  }

  @Test
  void aForwardLegMovesAlongTheStartingHeading() {
    Pose2d p = end(Leg.drive(TEN_FT));
    assertEquals(TEN_FT, p.getX(), 1e-9);
    assertEquals(0, p.getY(), 1e-9);
    assertEquals(0, p.getRotation().getDegrees(), 1e-9);
  }

  @Test
  void aReverseLegBacksUpWithoutTurningAround() {
    Pose2d p = end(Leg.drive(-TEN_FT));
    assertEquals(-TEN_FT, p.getX(), 1e-9);
    assertEquals(0, p.getRotation().getDegrees(), 1e-9, "driving in reverse must not change heading");
  }

  @Test
  void aDriveAfterALeftTurnGoesAlongTheNewHeading() {
    Pose2d p = end(Leg.drive(TEN_FT), Leg.turn(90), Leg.drive(FIVE_FT));
    assertEquals(TEN_FT, p.getX(), 1e-9);
    assertEquals(FIVE_FT, p.getY(), 1e-9);
    assertEquals(90, p.getRotation().getDegrees(), 1e-9);
  }

  @Test
  void aRightTurnGoesTheOtherWay() {
    Pose2d p = end(Leg.drive(TEN_FT), Leg.turn(-90), Leg.drive(FIVE_FT));
    assertEquals(TEN_FT, p.getX(), 1e-9);
    assertEquals(-FIVE_FT, p.getY(), 1e-9);
    assertEquals(-90, p.getRotation().getDegrees(), 1e-9);
  }

  @Test
  void twoSeventyLeftFacesWhereNinetyRightDoes() {
    // The very reason a turn must add up its rotation rather than servo to an absolute heading.
    assertEquals(end(Leg.turn(-90)).getRotation().getDegrees(), end(Leg.turn(270)).getRotation().getDegrees(), 1e-9);
  }

  @Test
  void aSquareAndATriangleClose() {
    Pose2d sq = end(Leg.drive(FIVE_FT), Leg.turn(90), Leg.drive(FIVE_FT), Leg.turn(90),
        Leg.drive(FIVE_FT), Leg.turn(90), Leg.drive(FIVE_FT), Leg.turn(90));
    assertEquals(0, sq.getX(), 1e-9);
    assertEquals(0, sq.getY(), 1e-9);
    assertEquals(0, sq.getRotation().getDegrees(), 1e-9);
    Pose2d tri = end(Leg.drive(FIVE_FT), Leg.turn(120), Leg.drive(FIVE_FT), Leg.turn(120),
        Leg.drive(FIVE_FT), Leg.turn(120));
    assertEquals(0, tri.getX(), 1e-6);
    assertEquals(0, tri.getY(), 1e-6);
  }

  @Test
  void geometryComposesFromAnyStart() {
    Pose2d p = ManeuverCatalog.expectedPose(new Pose2d(4, 2, Rotation2d.fromDegrees(90)), List.of(Leg.drive(1)));
    assertEquals(4, p.getX(), 1e-9);
    assertEquals(3, p.getY(), 1e-9);
  }

  @Test
  void everyPermutationEndsWhereItsLegsSay() {
    // Out d, turn, then 10 ft along the new heading: the last leg runs along +y or -y.
    for (Maneuver m : ManeuverCatalog.permutations()) {
      double out = m.legs().get(0).value();
      double turn = m.legs().get(1).value();
      double last = m.legs().get(2).value();
      double facing = Math.IEEEremainder(turn, 360);
      Pose2d p = ManeuverCatalog.expectedPose(new Pose2d(), m.legs());
      assertEquals(out, p.getX(), 1e-9, m.name());
      assertEquals(Math.signum(facing) * last, p.getY(), 1e-9, m.name());
      assertEquals(facing, p.getRotation().getDegrees(), 1e-9, m.name());
    }
    Pose2d p = ManeuverCatalog.expectedPose(new Pose2d(), named("P_5ft_R270_rev10ft").legs());
    assertEquals(FIVE_FT, p.getX(), 1e-9);
    assertEquals(-TEN_FT, p.getY(), 1e-9, "270 right faces left, and reversing from there goes right");
    assertEquals(90, p.getRotation().getDegrees(), 1e-9);
  }

  @Test
  void retracingReturnsHomeFacingTheSameWay() {
    List<Leg> out = List.of(Leg.drive(TEN_FT), Leg.turn(90), Leg.drive(FIVE_FT));
    List<Leg> back = ManeuverCatalog.retraceLegs(out);
    assertEquals(-FIVE_FT, back.get(0).value(), 1e-9, "the last leg out is undone first");
    assertEquals(-90, back.get(1).value(), 1e-9);
    List<Leg> both = new ArrayList<>(out);
    both.addAll(back);
    Pose2d p = ManeuverCatalog.expectedPose(new Pose2d(), both);
    assertEquals(0, p.getX(), 1e-9);
    assertEquals(0, p.getY(), 1e-9);
    assertEquals(0, p.getRotation().getDegrees(), 1e-9);
  }

  // ------------------------------------------------------------------ the catalog

  @Test
  void twentyFiveManeuversInThreeFamilies() {
    assertEquals(16, ManeuverCatalog.permutations().size());
    assertEquals(4, ManeuverCatalog.outAndBackSamePath().size());
    assertEquals(5, ManeuverCatalog.outAndBackDifferentPath().size());
    assertEquals(25, ManeuverCatalog.all().size());
    for (Maneuver m : ManeuverCatalog.permutations()) {
      assertSame(Family.PERMUTATION, m.family());
      assertFalse(m.returnsToStart(), m.name() + " is drive-turn-drive: it does not close a loop");
    }
  }

  @Test
  void permutationsCoverEveryCombination() {
    List<Maneuver> p = ManeuverCatalog.permutations();
    assertEquals(8, p.stream().filter(m -> m.name().startsWith("P_10ft_")).count());
    assertEquals(8, p.stream().filter(m -> m.name().startsWith("P_5ft_")).count());
    assertEquals(8, p.stream().filter(m -> m.name().contains("_L")).count());
    assertEquals(8, p.stream().filter(m -> m.name().contains("_R")).count());
    assertEquals(8, p.stream().filter(m -> m.name().contains("270_")).count());
    assertEquals(8, p.stream().filter(m -> m.name().endsWith("rev10ft")).count());
  }

  @Test
  void namesAndIdsAreUniqueAndTheOrderIsPinned() {
    Set<String> names = new HashSet<>();
    Set<Long> ids = new HashSet<>();
    for (Maneuver m : ManeuverCatalog.all()) {
      assertTrue(names.add(m.name()), "names are log keys: " + m.name());
      assertTrue(ids.add(m.id()), "ids pick a maneuver: " + m.name());
      assertTrue(m.id() >= 0 && m.id() < (1L << 31), "a double carries it exactly");
      assertSame(m, ManeuverCatalog.byId(m.id()));
    }
    // The laptop's maneuvers.py computes the same numbers and keeps the same order.
    assertEquals(131818226L, ManeuverCatalog.id("OB_diff_square5ft"));
    assertEquals(443694424L, ManeuverCatalog.id("P_10ft_L90_fwd10ft"));
    assertEquals("P_10ft_L90_fwd10ft", ManeuverCatalog.byIndex(0).name());
    assertEquals("P_10ft_R90_fwd10ft", ManeuverCatalog.byIndex(2).name());
    assertEquals("OB_same_straight10ft", ManeuverCatalog.byIndex(16).name());
    assertEquals("OB_diff_square5ft", ManeuverCatalog.byIndex(20).name());
    assertEquals("OB_diff_triangle", ManeuverCatalog.byIndex(24).name());
    assertNull(ManeuverCatalog.byIndex(25));
    assertNull(ManeuverCatalog.byId(1));
  }

  @Test
  void everyLoopReallyCloses() {
    for (Maneuver m : ManeuverCatalog.all()) {
      if (!m.returnsToStart()) {
        continue;
      }
      Pose2d p = ManeuverCatalog.expectedPose(new Pose2d(), m.legs());
      assertEquals(0, Math.hypot(p.getX(), p.getY()), 1e-6, m.name() + " is flagged as a loop");
      assertEquals(0, Math.IEEEremainder(p.getRotation().getDegrees(), 360), 1e-6, m.name());
    }
  }

  @Test
  void squaresAndRectanglesRunBothWays() {
    assertTrue(named("OB_diff_square5ft").legs().stream().anyMatch(l -> l.value() == 90));
    assertTrue(named("OB_diff_square5ft_right").legs().stream().anyMatch(l -> l.value() == -90));
    // Its 2026 description said mixed turns; its legs are four right turns, the rectangle's mirror.
    assertEquals(-360, named("OB_diff_mixed_turns").totalTurnDeg(), 1e-9);
    assertEquals(360, named("OB_diff_rectangle").totalTurnDeg(), 1e-9);
  }

  @Test
  void distancesBudgetsAndFloorAreSane() {
    double total = ManeuverCatalog.totalDistanceM(ManeuverCatalog.all());
    assertTrue(total > 50 && total < 500, "a session, not a marathon: " + total);
    for (Maneuver m : ManeuverCatalog.all()) {
      assertTrue(m.totalDistanceM() > 0, m.name() + " drives nowhere");
      double[] e = ManeuverCatalog.extentM(m.legs());
      // The floor check measures clear floor ahead and to each side only.
      assertEquals(0, e[1], 1e-9, m.name() + " goes behind its start");
      assertTrue(e[3] >= Math.max(e[0], e[2]) - 1e-9);
    }
    Maneuver square = named("OB_diff_square5ft");
    assertEquals(0.0508, square.budgetM(), 1e-9, "20 ft driven: 2 in");
    double[] e = ManeuverCatalog.extentM(named("P_10ft_L90_fwd10ft").legs());
    assertEquals(TEN_FT, e[0], 1e-9);
    assertEquals(TEN_FT, e[2], 1e-9);
    assertEquals(Math.hypot(TEN_FT, TEN_FT), e[3], 1e-9);
  }

  @Test
  void descriptionsAreForPeople() {
    for (Maneuver m : ManeuverCatalog.all()) {
      assertFalse(m.description().isBlank(), m.name());
      assertTrue(m.description().chars().allMatch(c -> c < 128), m.name());
    }
  }
}
