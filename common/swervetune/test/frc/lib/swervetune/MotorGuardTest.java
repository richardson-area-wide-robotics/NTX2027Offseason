package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import frc.lib.swervetune.MotorGuard.Motor;
import frc.lib.swervetune.MotorGuard.Stage;
import org.junit.jupiter.api.Test;

class MotorGuardTest {
  private final MotorGuard guard = new MotorGuard();
  private final FakeMotorChannel[] all = new FakeMotorChannel[8];
  private int count;
  private double t;

  private Motor add(String name, FakeMotorChannel c, MotorKind kind, boolean stallTimer) {
    all[count++] = c;
    return guard.register(name, c, kind, false, stallTimer);
  }

  private void run(double seconds) {
    long n = Math.round(seconds / 0.02);
    for (long i = 0; i < n; i++) {
      for (int k = 0; k < count; k++) {
        all[k].advance(0.02);
      }
      t += 0.02;
      guard.update(t);
    }
  }

  /** Seconds until the motor first reaches the stage, or infinity if it does not within max. */
  private double timeTo(Motor m, Stage s, double max) {
    double start = t;
    while (t - start < max) {
      run(0.02);
      if (m.stage() == s) {
        return t - start;
      }
    }
    return Double.POSITIVE_INFINITY;
  }

  // ------------------------------------------------------------------ heat model

  @Test
  void aNeo550At40AmpsIsCutWellBeforeItsWindingsFail() {
    // REV's locked-rotor test: a NEO 550 at 40 A burnt out after about 27 s while its sensor still
    // read about 40 C. A controller that ignores its limit, and a sensor that never moves: only
    // the heat model can save it.
    FakeMotorChannel c = new FakeMotorChannel(20);
    c.ignoresLimit = true;
    c.demandA = 40;
    Motor m = add("Arm", c, MotorKind.NEO_550, false);
    double warn = timeTo(m, Stage.WARN, 60);
    double derate = warn + timeTo(m, Stage.DERATE, 60);
    double shutoff = derate + timeTo(m, Stage.SHUTOFF, 60);
    assertTrue(warn > 3 && warn < derate && derate < shutoff, warn + " " + derate + " " + shutoff);
    assertTrue(shutoff > 10 && shutoff < 20, "cut at " + shutoff + " s; REV saw failure at ~27 s");
    assertEquals(MotorGuard.SHUTOFF_LIMIT_A, c.limit);
    assertTrue(m.cause().contains("heat estimate"), m.cause());
  }

  @Test
  void aNeo550At20AmpsIsLeftAlone() {
    // REV: a NEO 550 survived 220 s locked at 20 A, the team's policy limit for it.
    FakeMotorChannel c = new FakeMotorChannel(20);
    c.demandA = 20;
    c.rpm = 3000;
    Motor m = add("Arm", c, MotorKind.NEO_550, true);
    run(300);
    assertEquals(Stage.OK, m.stage());
    assertTrue(m.heatFraction() < 0.35, "heat " + m.heatFraction());
    assertEquals(0, c.sends);
  }

  @Test
  void deratingHoldsAnOverLimit550BelowFailure() {
    FakeMotorChannel c = new FakeMotorChannel(40); // over its 20 A policy, not enforced
    c.demandA = 40;
    c.rpm = 3000;
    Motor m = add("Arm", c, MotorKind.NEO_550, true);
    double maxHeat = 0;
    boolean derated = false;
    for (int i = 0; i < 600 * 5; i++) {
      run(0.2);
      maxHeat = Math.max(maxHeat, m.heatFraction());
      derated |= m.stage() == Stage.DERATE;
      assertTrue(m.stage() != Stage.SHUTOFF, "never needs cutting at " + t);
    }
    assertTrue(derated);
    assertTrue(maxHeat < 0.75, "max heat " + maxHeat);
  }

  @Test
  void driveMotorsAreNotCutForPushingButHeatStillCounts() {
    // A drive motor stalls in every pushing match. REV: a NEO V1.1 fails after ~105 s at 60 A.
    FakeMotorChannel c = new FakeMotorChannel(60);
    c.demandA = 60;
    Motor m = add("frontleft drive", c, MotorKind.NEO_V1_1, false);
    run(20);
    assertEquals(Stage.OK, m.stage(), "a 20 s push is fine");
    assertEquals(0, m.stallSeconds());
    double derate = 20 + timeTo(m, Stage.DERATE, 80);
    assertTrue(derate > 45 && derate < 75, "derated at " + derate + " s");
    run(200);
    assertTrue(m.stage() != Stage.SHUTOFF, "half current keeps it alive: " + m.cause());
  }

  // ------------------------------------------------------------------ stall timer

  @Test
  void aJamWarnsDeratesThenCutsOutAndStaysOutUntilReleased() {
    FakeMotorChannel c = new FakeMotorChannel(80);
    c.demandA = 100; // driven into a hard stop
    Motor m = add("Intake pivot", c, MotorKind.VORTEX, true);
    double warn = timeTo(m, Stage.WARN, 30);
    assertEquals(3.0, warn, 0.05);
    double derate = warn + timeTo(m, Stage.DERATE, 30);
    assertEquals(10.0 / 3, derate, 0.05);
    assertEquals(40, c.limit);
    // Derated, it still counts, at half rate: (10 - 3.33) * 2 more seconds.
    double shutoff = derate + timeTo(m, Stage.SHUTOFF, 30);
    assertEquals(10.0 / 3 + 40.0 / 3, shutoff, 0.1);
    assertEquals(MotorGuard.SHUTOFF_LIMIT_A, c.limit);
    assertTrue(m.cause().startsWith("stalled"), m.cause());

    run(30); // still being driven into the jam
    assertEquals(Stage.SHUTOFF, m.stage(), "stays off while the jam is still being pushed");

    c.demandA = 0; // the operator lets go
    run(9);
    assertEquals(Stage.SHUTOFF, m.stage(), "the stall timer has to run all the way down");
    run(1.5);
    assertEquals(Stage.OK, m.stage());
    assertEquals(80, c.limit, "the original limit is back");
    assertTrue(guard.events().stream().anyMatch(e -> e.contains("Intake pivot up DERATE -> SHUTOFF")),
        guard.events().toString());
  }

  @Test
  void aTurningMotorAtItsLimitIsNotAStall() {
    FakeMotorChannel c = new FakeMotorChannel(40);
    c.demandA = 40;
    c.rpm = 2000; // accelerating a flywheel hard
    Motor m = add("Shooter", c, MotorKind.VORTEX, true);
    run(20);
    assertEquals(0, m.stallSeconds());
  }

  // ------------------------------------------------------------------ sensor and hysteresis

  @Test
  void sensorStagesStepUpAtOnceAndDownOnly10DegreesClear() {
    FakeMotorChannel c = new FakeMotorChannel(20);
    Motor m = add("Arm", c, MotorKind.NEO_550, true); // 45 / 55 / 65 C
    double[][] steps = {
      {50, Stage.WARN.ordinal()},
      {56, Stage.DERATE.ordinal()},
      {66, Stage.SHUTOFF.ordinal()},
      {60, Stage.SHUTOFF.ordinal()},
      {54, Stage.DERATE.ordinal()},
      {50, Stage.DERATE.ordinal()},
      {44, Stage.WARN.ordinal()},
      {36, Stage.WARN.ordinal()},
      {34, Stage.OK.ordinal()},
    };
    for (double[] s : steps) {
      c.tempC = s[0];
      run(0.1);
      assertEquals(Stage.values()[(int) s[1]], m.stage(), "at " + s[0] + " C");
    }
    assertEquals(20, c.limit);
  }

  // ------------------------------------------------------------------ overrides

  @Test
  void anOverrideHoldsAHeatShutoffAtHalfCurrentForAtMost20Seconds() {
    FakeMotorChannel c = new FakeMotorChannel(20);
    Motor m = add("Arm", c, MotorKind.NEO_550, true);
    c.tempC = 66;
    run(0.1);
    assertEquals(Stage.SHUTOFF, m.stage());
    String reply = guard.override("Arm", 100, t);
    assertTrue(reply.contains("20 s"), reply);
    run(0.1);
    assertEquals(Stage.DERATE, m.stage());
    assertEquals(10, c.limit);
    assertTrue(m.cause().contains("override"), m.cause());
    run(20);
    assertEquals(Stage.SHUTOFF, m.stage(), "the override ran out");
    assertEquals(MotorGuard.SHUTOFF_LIMIT_A, c.limit);
  }

  @Test
  void anOverrideCannotSaveAMotorThatIsAlreadyCooking() {
    FakeMotorChannel c = new FakeMotorChannel(20);
    Motor m = add("Arm", c, MotorKind.NEO_550, true);
    c.tempC = 76; // 10 C past shutoff
    guard.override("ALL", 20, t);
    run(0.1);
    assertEquals(Stage.SHUTOFF, m.stage());
  }

  @Test
  void anOverrideNeverLiftsAStallCut() {
    FakeMotorChannel c = new FakeMotorChannel(80);
    c.demandA = 100;
    Motor m = add("Intake pivot", c, MotorKind.VORTEX, true);
    timeTo(m, Stage.SHUTOFF, 30);
    guard.override("ALL", 20, t);
    run(1);
    assertEquals(Stage.SHUTOFF, m.stage());
  }

  @Test
  void anOverrideForAnUnknownMotorSaysSo() {
    add("Arm", new FakeMotorChannel(20), MotorKind.NEO_550, true);
    assertTrue(guard.override("Elevator", 10, t).contains("No motor called Elevator"));
  }

  // ------------------------------------------------------------------ failures

  @Test
  void outputWithNoCurrentIsFlaggedAsUnpluggedOrBurnt() {
    FakeMotorChannel c = new FakeMotorChannel(40);
    Motor m = add("Feeder", c, MotorKind.NEO_UNKNOWN, true);
    c.duty = 0.5; // asked to run; no current flows and nothing turns
    run(1);
    assertTrue(m.flags().contains("no current"), m.flags());
    c.demandA = 5;
    c.rpm = 3000;
    run(0.1);
    assertEquals("", m.flags());
  }

  @Test
  void aFaultyTemperatureSensorDoesNotCutTheMotor() {
    FakeMotorChannel c = new FakeMotorChannel(80);
    Motor m = add("frontleft drive", c, MotorKind.VORTEX, true);
    c.tempC = 200; // a broken sensor or cable, not a motor at 200 C
    c.demandA = 10;
    run(1.0);
    assertEquals(MotorGuard.Stage.OK, m.stage(), m.cause());
    assertTrue(m.flags().contains("unplugged or faulty"), m.flags());
  }

  @Test
  void sensorNonsenseAndControllerFaultsAreFlagged() {
    FakeMotorChannel c = new FakeMotorChannel(40);
    Motor m = add("Feeder", c, MotorKind.NEO_UNKNOWN, true);
    c.tempC = 0;
    c.faults = "gate driver";
    c.sticky = "sensor";
    run(0.1);
    assertTrue(m.flags().contains("temperature sensor reads 0"), m.flags());
    assertTrue(m.flags().contains("faults: gate driver"), m.flags());
    assertFalse(m.flags().contains("since last cleared"), "a fault that already cleared is history, not a failure now");
    assertEquals("faults since last cleared: sensor", m.history());
  }

  @Test
  void aModuleWhoseSteeringIsCutDrivesAtHalfPower() {
    FakeMotorChannel drive = new FakeMotorChannel(60);
    FakeMotorChannel steer = new FakeMotorChannel(20);
    steer.ignoresLimit = true;
    steer.demandA = 40;
    Motor d = add("frontleft drive", drive, MotorKind.VORTEX, false);
    Motor s = add("frontleft steer", steer, MotorKind.NEO_550, false);
    assertTrue(timeTo(s, Stage.SHUTOFF, 60) < 60);
    run(0.1);
    assertEquals(Stage.DERATE, d.stage());
    assertTrue(d.cause().contains("steering motor is cut off"), d.cause());
    steer.demandA = 0;
    assertTrue(timeTo(s, Stage.OK, 600) < 600);
    run(0.1);
    assertEquals(Stage.OK, d.stage(), "back to full power once the steering motor is");
  }

  @Test
  void heatCutsAreCountedSoTheyOutliveTheCooling() {
    FakeMotorChannel c = new FakeMotorChannel(20);
    c.ignoresLimit = true;
    c.demandA = 40;
    Motor m = add("Arm", c, MotorKind.NEO_550, false);
    assertTrue(timeTo(m, Stage.SHUTOFF, 60) < 60);
    c.demandA = 0;
    assertTrue(timeTo(m, Stage.OK, 600) < 600, "it cools");
    assertEquals(1, m.shutoffs());
    assertEquals(1, m.derates());
  }

  @Test
  void theLongestOverrideIsWhatTheDashboardShows() {
    FakeMotorChannel a = new FakeMotorChannel(20);
    FakeMotorChannel b = new FakeMotorChannel(20);
    add("Arm", a, MotorKind.NEO_550, false);
    add("Wrist", b, MotorKind.NEO_550, false);
    run(0.1);
    assertEquals(0, guard.overrideRemainingS(t), 1e-9);
    guard.override("Arm", 20, t);
    run(5);
    assertEquals(15, guard.overrideRemainingS(t), 0.05);
  }

  // ------------------------------------------------------------------ wiring

  @Test
  void aControllerThatDropsOffTheBusIsCountedAndJudgedOnNothingStale() {
    FakeMotorChannel c = new FakeMotorChannel(40);
    c.demandA = 60;
    c.ignoresLimit = true;
    Motor m = add("Feeder", c, MotorKind.NEO_2_0, false);
    run(1);
    double heat = m.heatFraction();
    c.present = false;
    run(3);
    assertFalse(m.present());
    assertEquals(1, m.dropouts());
    assertEquals(heat, m.heatFraction(), 1e-12, "its frozen 60 A must not keep heating the estimate");
    assertTrue(m.flags().contains("not heard"), m.flags());
    c.present = true;
    run(0.1);
    c.present = false;
    run(0.1);
    assertEquals(2, m.dropouts());
    assertTrue(guard.events().stream().anyMatch(e -> e.contains("Feeder dropped off the CAN bus")));
  }

  @Test
  void aRebootMeansItLostPowerAndIsCountedOnce() {
    FakeMotorChannel c = new FakeMotorChannel(40);
    Motor m = add("Feeder", c, MotorKind.NEO_2_0, true);
    c.resetFlag = true;
    run(0.5);
    assertEquals(1, m.resets());
    assertFalse(c.resetFlag, "the flag is cleared so the next reboot counts again");
    c.resetFlag = true;
    run(0.1);
    assertEquals(2, m.resets());
    assertTrue(guard.events().stream().anyMatch(e -> e.contains("lost power")));
  }

  @Test
  void lowSupplyWarningsAreCountedByEpisode() {
    FakeMotorChannel c = new FakeMotorChannel(40);
    Motor m = add("Feeder", c, MotorKind.NEO_2_0, true);
    c.brownout = true;
    run(0.5);
    c.brownout = false;
    run(0.1);
    c.brownout = true;
    run(0.1);
    assertEquals(2, m.brownouts());
  }

  // ------------------------------------------------------------------ policy and plumbing

  @Test
  void theCurrentPolicyIsEnforcedAtRegistrationWhenAsked() {
    FakeMotorChannel over = new FakeMotorChannel(40);
    Motor m = guard.register("Arm", over, MotorKind.NEO_550, true);
    assertEquals(20, over.limit);
    assertEquals(20, m.baseLimitA());
    FakeMotorChannel reported = new FakeMotorChannel(80);
    guard.register("Shooter", reported, MotorKind.NEO_V1_1, false);
    assertEquals(80, reported.limit, "reported, not changed");
    FakeMotorChannel unknown = new FakeMotorChannel(0);
    assertEquals(60, guard.register("Intake", unknown, MotorKind.NEO_UNKNOWN, true).baseLimitA());
    FakeMotorChannel sim = new FakeMotorChannel(0);
    sim.simulated = true;
    guard.register("Sim", sim, MotorKind.VORTEX, true);
    String report = String.join("\n", guard.report());
    assertTrue(report.contains("Arm (NEO 550): current limit 40 A is over the 20 A policy; lowered"),
        report);
    assertTrue(report.contains("Shooter (NEO V1.1): current limit 80 A is over the 60 A policy."),
        report);
    assertTrue(report.contains("Intake") && report.contains("could not read"), report);
    assertFalse(report.contains("Sim"), "a simulated motor has nothing to report");
  }

  @Test
  void aLoweredLimitIsResentEveryTwoSecondsAndARefusalRetriedTwiceASecond() {
    FakeMotorChannel c = new FakeMotorChannel(20);
    Motor m = add("Arm", c, MotorKind.NEO_550, true);
    c.tempC = 66;
    run(10);
    assertEquals(Stage.SHUTOFF, m.stage());
    assertTrue(c.sends >= 5 && c.sends <= 7, c.sends + " sends in 10 s");

    FakeMotorChannel stubborn = new FakeMotorChannel(20);
    stubborn.refuses = true;
    stubborn.tempC = 66;
    add("Wrist", stubborn, MotorKind.NEO_550, true);
    run(5);
    assertTrue(stubborn.sends >= 9 && stubborn.sends <= 12, stubborn.sends + " tries in 5 s");
  }

  @Test
  void aNameCanOnlyBeRegisteredOnce() {
    guard.register("Arm", new FakeMotorChannel(20), MotorKind.NEO_550, false);
    assertThrows(IllegalArgumentException.class,
        () -> guard.register("Arm", new FakeMotorChannel(20), MotorKind.NEO_550, false));
  }

  @Test
  void motorKindsParseFromInventoryNamesAndYagslTypes() {
    assertEquals(MotorKind.NEO_550, MotorKind.parse("NEO 550"));
    assertEquals(MotorKind.NEO_550, MotorKind.parse("sparkmax_neo550"));
    assertEquals(MotorKind.VORTEX, MotorKind.parse("sparkflex_vortex"));
    assertEquals(MotorKind.VORTEX, MotorKind.parse("NEO Vortex"));
    assertEquals(MotorKind.NEO_2_0, MotorKind.parse("NEO 2.0"));
    assertEquals(MotorKind.NEO_V1_1, MotorKind.parse("NEO V1.1"));
    assertEquals(MotorKind.NEO_V1_1, MotorKind.parse("neo1.1"));
    assertEquals(MotorKind.NEO_UNKNOWN, MotorKind.parse("sparkmax_neo"));
  }

  @Test
  void theSafetySupervisorStopsATestOnAHotMotor() {
    SafetySupervisor sup = new SafetySupervisor(new SafetySupervisor.Limits());
    SafetySupervisor.Inputs in = new SafetySupervisor.Inputs();
    in.env = TestEnvironment.BLOCKS;
    in.enabled = true;
    in.heartbeatAgeS = 0.05;
    in.hotMotor = "The frontleft steer motor is at DERATE (heat estimate 72%).";
    var profile = new SafetySupervisor.TestProfile(true, false, 1.0, 0.0);
    assertEquals(SafetySupervisor.Action.WAIT, sup.check(in, profile, false).action());
    var v = sup.check(in, profile, true);
    assertEquals(SafetySupervisor.Action.ABORT, v.action());
    assertTrue(v.reason().contains("frontleft steer") && v.reason().contains("cool"), v.reason());
  }

  @Test
  void aControllerThatIsNotWhatTheCodeMadeIsFlagged() {
    FakeMotorChannel c = new FakeMotorChannel(80);
    c.model = "SPARK Flex";
    c.codeClass = "SPARK MAX";
    Motor m = guard.register("frontleft drive", c, MotorKind.VORTEX, false, false);
    guard.update(0.02);
    assertTrue(m.flags().contains("is a SPARK Flex but the code created a SPARK MAX"), m.flags());
    assertTrue(m.flags().contains("create it as new SparkFlex(...)"), "the class REVLib really has: " + m.flags());
    c.codeClass = "SPARK Flex";
    guard.update(0.04);
    assertFalse(m.flags().contains("is a SPARK"), "agreeing is fine");
    c.model = "";
    guard.update(0.06);
    assertFalse(m.flags().contains("is a SPARK"), "a controller that can't say isn't accused");
  }

  @Test
  void revlibStillHasTheMethodTheModelDetectionReaches() throws NoSuchMethodException {
    // SparkChannel.detectModel reaches this package-private method by reflection; if a REVLib
    // update renames it, this fails here instead of detection going quiet on the robot.
    assertTrue(com.revrobotics.spark.SparkBase.class.getDeclaredMethod("getSparkModel") != null);
  }
}
