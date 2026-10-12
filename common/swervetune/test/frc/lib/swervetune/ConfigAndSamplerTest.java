package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ConfigAndSamplerTest {

  @Test
  void miniJsonReadsWhatTheToolWrites() {
    Object v = MiniJson.parse("{\"a\": [1, -2.5e1, true, null], \"b\": {\"c\": \"x\\\"y\\u0041\"}}");
    Map<?, ?> m = (Map<?, ?>) v;
    assertEquals(List.of(1.0, -25.0, true), ((List<?>) m.get("a")).subList(0, 3));
    assertNull(((List<?>) m.get("a")).get(3));
    assertEquals("x\"yA", ((Map<?, ?>) m.get("b")).get("c"));
  }

  @Test
  void miniJsonRejectsBrokenFilesWithALineNumber() {
    var e = assertThrows(IllegalArgumentException.class, () -> MiniJson.parse("{\n\"a\": 1,\n}"));
    assertTrue(e.getMessage().contains("line 3"), e.getMessage());
  }

  @Test
  void missingFileChangesNothing() {
    SwerveTuneConfig c = SwerveTuneConfig.load(Path.of("definitely/not/here.json"));
    assertEquals("motor", c.steerFeedback);
    assertFalse(c.encoderAutoSync);
    assertEquals(0, c.driveVelocityPeriodMs);
    assertTrue(c.driveFeedforward.isEmpty());
    assertNull(c.chassisDiscretizationTeleop);
    assertEquals(1, c.warnings.size());
  }

  @Test
  void parsesEverySection() {
    SwerveTuneConfig c = SwerveTuneConfig.parse("""
        {
          "steerFeedback": "absolute",
          "encoderAutoSync": {"enabled": true, "deadbandDeg": 0.5},
          "driveVelocityFilter": {"periodMs": 16, "depth": 2},
          "driveFeedforward": {
            "frontleft": {"kS": 0.12, "kV": 2.71, "kA": 0.31},
            "frontright": {"kV": 2.7}
          },
          "angularVelocityCompensation": {"teleop": true, "auto": false, "coefficient": 0.08},
          "chassisDiscretization": {"auto": true},
          "operator": {"driverPort": 0, "deadmanPort": 2, "deadmanButton": 5, "overrideAxes": [1, 4]},
          "testLimits": {"defaultSpeedCapMps": 0.8, "minStartVoltsField": 12.0}
        }
        """);
    assertEquals("absolute", c.steerFeedback);
    assertTrue(c.encoderAutoSync);
    assertEquals(0.5, c.encoderAutoSyncDeadbandDeg);
    assertEquals(16, c.driveVelocityPeriodMs);
    assertArrayEquals(new double[] {0.12, 2.71, 0.31}, c.driveFeedforward.get("frontleft"));
    assertFalse(c.driveFeedforward.containsKey("frontright"), "kS missing: ignored, not guessed");
    assertTrue(c.warnings.get(0).contains("frontright"));
    assertTrue(c.angularVelocityCompensationTeleop);
    assertEquals(0.08, c.angularVelocityCoefficient);
    assertNull(c.chassisDiscretizationTeleop, "absent means YAGSL's own default");
    assertTrue(c.chassisDiscretizationAuto);
    assertEquals(2, c.deadmanPort);
    assertArrayEquals(new int[] {1, 4}, c.overrideAxes);
    assertEquals(0.8, c.defaultSpeedCapMps);
    assertEquals(12.0, c.limits.minStartVoltsField);
  }

  @Test
  void badSteerFeedbackIsAWarningNotAChange() {
    SwerveTuneConfig c = SwerveTuneConfig.parse("{\"steerFeedback\": \"abs\"}");
    assertEquals("motor", c.steerFeedback);
    assertEquals(1, c.warnings.size());
  }

  @Test
  void samplerUnwrapsAnglesThroughTheWrap() {
    double[] clock = {0};
    double[] angle = {350};
    Sampler s = Sampler.create(16).angle("a", () -> angle[0]).channel("b", () -> 7);
    s.start(() -> clock[0]);
    for (double a : new double[] {350, 359, 3, 10, 355, 340}) {
      angle[0] = a;
      s.sampleNow();
      clock[0] += 0.005;
    }
    Map<String, double[]> d = s.snapshot();
    assertArrayEquals(new double[] {350, 359, 363, 370, 355, 340}, d.get("a"), 1e-9);
    assertArrayEquals(new double[] {0, 0.005, 0.01, 0.015, 0.02, 0.025}, d.get("t"), 1e-9);
    assertEquals(7, d.get("b")[0]);
  }

  @Test
  void samplerStopsAtCapacityAndSaysSo() {
    Sampler s = Sampler.create(16).channel("x", () -> 1);
    s.start(() -> 0);
    for (int i = 0; i < 40; i++) {
      s.sampleNow();
    }
    assertEquals(16, s.rows());
    assertTrue(s.overflowed());
  }

  @Test
  void timelineFindsSegments() {
    Timeline t = new Timeline().add("a", 1, 10).add("b", 0.5, 20);
    assertEquals(0, t.indexAt(0));
    assertEquals(0, t.indexAt(0.99));
    assertEquals(1, t.indexAt(1.0));
    assertEquals(2, t.indexAt(1.5));
    assertEquals(0.25, t.timeInto(1, 1.25), 1e-12);
  }

  @Test
  void trapezoidProfileCoversItsDistance() {
    double d = 3;
    double v = 1;
    double a = 1;
    double total = StraightLineProcedure.profileSeconds(d, v, a);
    double covered = 0;
    double dt = 0.0005;
    for (double t = 0; t < total; t += dt) {
      covered += StraightLineProcedure.profileSpeed(t, d, v, a) * dt;
    }
    assertEquals(d, covered, 0.01);
    // a triangular profile too: too short to reach full speed
    total = StraightLineProcedure.profileSeconds(0.5, 2, 1);
    covered = 0;
    for (double t = 0; t < total; t += dt) {
      covered += StraightLineProcedure.profileSpeed(t, 0.5, 2, 1) * dt;
    }
    assertEquals(0.5, covered, 0.01);
  }

  @Test
  void driveStepRefusesARunThatDoesNotFit() {
    FakeDrivetrain io = new FakeDrivetrain();
    TestContext tight = context(io, TestEnvironment.FIELD, 1.5, 1.0);
    DriveStepProcedure p = new DriveStepProcedure();
    String why = p.validate(tight);
    assertTrue(why != null && why.contains("clear floor"), String.valueOf(why));
    TestContext roomy = context(io, TestEnvironment.FIELD, 1.5, 6.0);
    assertNull(p.validate(roomy));
    // the default field profile goes out and back, so the geofence is far less than the total travel
    assertTrue(p.spaceBudgetM(roomy) < 4.0);
  }

  @Test
  void feedforwardRunShrinksToFitTheFloor() {
    FakeDrivetrain io = new FakeDrivetrain();
    DriveFeedforwardProcedure p = new DriveFeedforwardProcedure();
    assertNull(p.validate(context(io, TestEnvironment.FIELD, 1.5, 6.0)));
    assertTrue(p.validate(context(io, TestEnvironment.FIELD, 1.5, 0.6)).contains("at least"));
  }

  @Test
  void abbreviationsMatchYagslNames() {
    assertEquals("fl", SwerveTune.abbreviation("frontleft"));
    assertEquals("br", SwerveTune.abbreviation("back_right"));
    assertEquals("br", SwerveTune.abbreviation("RearRight"));
  }

  static TestContext context(FakeDrivetrain io, TestEnvironment env, double cap, double space) {
    return new TestContext(io, TestArgs.empty(), env, new int[] {0, 1, 2, 3}, cap, space, space,
        false, Sampler.create(64), true, () -> true, () -> null);
  }
}
