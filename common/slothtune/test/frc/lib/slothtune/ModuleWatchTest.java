package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import edu.wpi.first.networktables.NetworkTableInstance;
import frc.lib.slothtune.ModuleWatch.Rule;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

/** The laptop monitor's checks, on the robot: held long enough, counted once per episode. */
class ModuleWatchTest {
  private final ModuleWatch w = new ModuleWatch(new String[] {"frontleft", "frontright"});
  private double t;

  /** Runs for a while with module 0 at these readings and module 1 behaving. */
  private void run(double seconds, boolean enabled, double steer, double sp, double motor, double v, double vSp) {
    for (int i = 0; i < Math.round(seconds / 0.02); i++) {
      t += 0.02;
      w.update(t, enabled, new double[] {steer, 0}, new double[] {sp, 0}, new double[] {motor, 0},
          new double[] {v, 0}, new double[] {vSp, 0});
    }
  }

  private ModuleWatch.Flag flag(String module, ModuleWatch.Rule r) {
    return w.flags().stream().filter(f -> f.module.equals(module) && f.rule == r).findFirst().orElseThrow();
  }

  @Test
  void steeringOffItsAngleCountsOnceAfterHalfASecond() {
    run(0.3, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(0, flag("frontleft", ModuleWatch.Rule.STEER_OFF).count, "not yet: a quick move is fine");
    run(0.4, true, 0, 30, 0, 1.0, 1.0);
    var f = flag("frontleft", ModuleWatch.Rule.STEER_OFF);
    assertEquals(1, f.count);
    assertTrue(f.active);
    run(2.0, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(1, f.count, "one long episode is one");
    // A flag clears once its condition has been gone for a second, as the laptop's do.
    run(1.2, true, 30, 30, 30, 1.0, 1.0);
    run(0.8, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(2, f.count, "a new episode counts again");
    assertEquals(0, flag("frontright", ModuleWatch.Rule.STEER_OFF).count);
  }

  @Test
  void aShortBreakIsTheSameEpisodeAndTheFlagStaysUp() {
    run(0.7, true, 0, 30, 0, 1.0, 1.0);
    var f = flag("frontleft", ModuleWatch.Rule.STEER_OFF);
    run(0.4, true, 30, 30, 30, 1.0, 1.0);
    assertTrue(f.active, "gone for less than a second: still raised, so it doesn't blink on the laptop");
    run(0.8, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(1, f.count, "a flicker is not a new episode");
    run(1.1, true, 30, 30, 30, 1.0, 1.0);
    assertFalse(f.active, "gone for a second: cleared");
  }

  @Test
  void anglesWrapAroundAndDisabledIsQuiet() {
    run(1.0, true, 179, -179, 179, 1.0, 1.0);
    assertEquals(0, flag("frontleft", ModuleWatch.Rule.STEER_OFF).count, "179 and -179 are 2 degrees apart");
    run(1.0, false, 0, 90, 0, 0, 1.0);
    assertEquals(0, flag("frontleft", ModuleWatch.Rule.STEER_OFF).count, "disabled: nothing is commanded");
  }

  @Test
  void theTwoSteeringSensorsDisagreeingWhileStill() {
    run(1.2, false, 10, 10, 15, 0, 0);
    assertEquals(1, flag("frontleft", ModuleWatch.Rule.SENSORS_DISAGREE).count, "5 degrees apart, standing still");
    run(1.2, false, 10, 10, 12, 0, 0);
    assertFalse(flag("frontleft", ModuleWatch.Rule.SENSORS_DISAGREE).active, "2 degrees is within 3");
    run(1.2, true, 10, 10, 15, 2.0, 2.0);
    assertEquals(1, flag("frontleft", ModuleWatch.Rule.SENSORS_DISAGREE).count, "moving: the motor encoder lags; not judged");
  }

  @Test
  void aWheelTurningAgainstItsCommand() {
    run(0.5, true, 0, 0, 0, -0.8, 1.0);
    assertEquals(1, flag("frontleft", ModuleWatch.Rule.BACKWARDS).count);
    run(1.2, true, 0, 0, 0, 0.05, 1.0);
    assertFalse(flag("frontleft", ModuleWatch.Rule.BACKWARDS).active, "barely turning is not backwards");
  }

  @Test
  void robotHealthKeepsTheCount() {
    DashboardAlerts alerts = new DashboardAlerts(false);
    run(0.6, true, 0, 0, 0, -0.8, 1.0);
    alerts.modules(w);
    String line = alerts.showing.get("watch/frontleft/Backwards");
    assertTrue(line.startsWith("kWarning") && line.contains("once this session"), line);
    run(1.5, true, 0, 0, 0, 1.0, 1.0);
    alerts.modules(w);
    assertTrue(alerts.showing.get("watch/frontleft/Backwards").contains("once this session"), "kept after it stops");
  }

  // ------------------------------------------------------------------ the rest of the laptop's rules

  private static final String[] FOUR = {"frontleft", "frontright", "backleft", "backright"};
  private final ModuleWatch w4 = new ModuleWatch(FOUR);
  private final ModuleWatch.Inputs in = healthy();
  private final DashboardAlerts alerts = new DashboardAlerts(false);

  /** A four-module robot driving forward at 1 m/s, everything as it should be. */
  private static ModuleWatch.Inputs healthy() {
    ModuleWatch.Inputs in = new ModuleWatch.Inputs();
    in.enabled = true;
    in.steer = new double[4];
    in.steerSp = new double[4];
    in.steerMotor = new double[4];
    in.v = new double[] {1, 1, 1, 1};
    in.vSp = new double[] {1, 1, 1, 1};
    in.pos = new double[4];
    in.driveAmps = new double[] {5, 5, 5, 5};
    in.driveTemp = new double[] {30, 30, 30, 30};
    in.steerTemp = new double[] {30, 30, 30, 30};
    in.absIssue = new double[4];
    in.faults = new String[] {"", "", "", ""};
    in.headingDeg = 0;
    in.busVolts = 12.5;
    in.gyroType = "navX";
    return in;
  }

  /** Runs the four-module robot for a while, calling {@code each} before every loop. */
  private void step(double seconds, Runnable each) {
    for (int i = 0; i < Math.round(seconds / 0.02); i++) {
      t += 0.02;
      each.run();
      w4.update(t, in);
    }
  }

  private void step(double seconds) {
    step(seconds, () -> { });
  }

  private ModuleWatch.Flag f4(int module, Rule r) {
    return w4.flag(module, r);
  }

  private String shown(String key) {
    alerts.modules(w4);
    return alerts.showing.get(key);
  }

  /** The motor guard's motors, as the robot registers them, at these temperatures. */
  private static List<MotorGuard.Motor> motors(String suffix, double... temps) {
    List<MotorGuard.Motor> out = new ArrayList<>();
    for (int i = 0; i < temps.length; i++) {
      MotorGuard.Motor m = new MotorGuard.Motor(FOUR[i] + suffix, MotorKind.NEO_V1_1, new FakeMotorChannel(60), false);
      m.tempC = temps[i];
      out.add(m);
    }
    return out;
  }

  @Test
  void aSteeringErrorThatKeepsChangingSignIsAnOscillation() {
    int[] k = {0};
    step(1.0, () -> {
      k[0]++;
      in.steer[0] = (k[0] / 5) % 2 == 0 ? 6 : -6; // 6 degrees either side, five swings a second
      in.steer[1] = k[0] % 2 == 0 ? 0.5 : -0.5; // jitter under a degree is not a swing
    });
    ModuleWatch.Flag f = f4(0, Rule.STEER_SWINGS);
    assertTrue(f.active);
    assertEquals(1, f.count);
    assertTrue(f.detail().endsWith("swings/s"), f.detail());
    assertEquals(0, f4(1, Rule.STEER_SWINGS).count);
    assertTrue(shown("watch/frontleft/SteerOscillation").contains("swinging back and forth"));
    step(2.5, () -> in.steer[0] = 0);
    assertFalse(f.active, "settled");
    in.enabled = false;
    step(1.0, () -> {
      k[0]++;
      in.steer[0] = (k[0] / 5) % 2 == 0 ? 6 : -6;
    });
    assertEquals(1, f.count, "disabled: pushed by hand, not the steering loop");
  }

  @Test
  void anAbsoluteEncoderReadFailingForAFifthOfASecond() {
    in.absIssue[2] = 1;
    step(0.1);
    assertEquals(0, f4(2, Rule.ABSOLUTE_READ).count, "one bad read is noise");
    step(0.2);
    assertEquals(1, f4(2, Rule.ABSOLUTE_READ).count);
    assertTrue(shown("watch/backleft/AbsoluteReadIssue").startsWith("kWarning: backleft: absolute encoder"));
  }

  @Test
  void aWheelWellShortOfItsSpeedIsLoggedButNeverShown() {
    in.vSp[0] = 3.0;
    in.v[0] = 1.5;
    in.vSp[1] = 3.0;
    in.v[1] = 2.8;
    step(1.2);
    ModuleWatch.Flag f = f4(0, Rule.LAGGING);
    assertTrue(f.active);
    assertEquals("4.92 of 9.84 ft/s", f.detail());
    assertEquals(0, f4(1, Rule.LAGGING).count, "7% short is keeping up");
    assertNull(shown("watch/frontleft/DriveLagging"), "pushing does this all match: not for the drive team");
    in.enabled = false;
    step(2.5);
    assertFalse(f.active);
  }

  @Test
  void aDriveMotorAtHighCurrentWithTheWheelBarelyTurning() {
    in.driveLimitA = 40;
    in.driveAmps[0] = 36; // over 85% of the limit
    in.v[0] = 0.05;
    in.driveAmps[1] = 30;
    in.v[1] = 0.05;
    in.driveAmps[2] = 36;
    in.v[2] = 1.0;
    step(0.5);
    assertTrue(f4(0, Rule.STALL).active);
    assertEquals("36 A", f4(0, Rule.STALL).detail());
    assertEquals(0, f4(1, Rule.STALL).count, "under 85% of the limit");
    assertEquals(0, f4(2, Rule.STALL).count, "turning: it is accelerating, not stalled");
    assertNull(shown("watch/frontleft/Stall"), "pushing a wall does this: not for the drive team");
  }

  @Test
  void overSeventyDegreesOnlyWhileTheMotorGuardWatchesNothing() {
    in.driveTemp[0] = 75;
    step(1.9);
    assertEquals(0, f4(0, Rule.HOT).count, "held for 2 s first");
    step(0.2);
    assertTrue(f4(0, Rule.HOT).active);
    assertTrue(shown("watch/frontleft/Hot").contains("motor is over 70 \u00b0C now (75 \u00b0C)"));
    ModuleWatch guarded = new ModuleWatch(FOUR);
    guarded.bindMotors(motors(" drive", 75, 30, 30, 30));
    for (int i = 0; i < 200; i++) {
      guarded.update(t += 0.02, in);
    }
    assertEquals(0, guarded.flag(0, Rule.HOT).count, "the guard's kind-aware heat rules replace it");
  }

  @Test
  void aControllerFaultFlagsAtOnceWithItsWords() {
    in.faults[3] = "drive CAN fault";
    step(0.02);
    ModuleWatch.Flag f = f4(3, Rule.FAULTS);
    assertTrue(f.active);
    assertEquals("drive CAN fault", f.detail());
    assertTrue(shown("watch/backright/Faults").contains("backright: motor controller reports a fault now (drive CAN fault)"));
    w4.bindMotors(motors(" drive", 30, 30, 30, 30));
    assertNull(shown("watch/backright/Faults"), "with the guard watching, its own red line says it");
  }

  @Test
  void aBatterySaggingBelowEightVoltsWhileEnabled() {
    in.busVolts = 7.5;
    step(0.3);
    ModuleWatch.Flag f = w4.robot(Rule.LOW_BATTERY);
    assertEquals(1, f.count);
    assertEquals("SlothTune/Watch/Robot/LowBattery", f.logKey);
    assertEquals("kWarning: The robot: battery voltage is sagging below 8 V now (7.5 V), once this session. "
        + Rule.LOW_BATTERY.look, shown("watch/robot/LowBattery"));
    in.busVolts = 12.5;
    step(1.2);
    in.enabled = false;
    in.busVolts = 7.0;
    step(1.0);
    assertEquals(1, f.count, "disabled: nothing is drawing current, so a low reading is the battery at rest");
  }

  @Test
  void aGyroDropoutCountsButTheCalibrationAtPowerOnDoesNot() {
    in.enabled = false;
    in.gyroCalibrating = true;
    step(3.0);
    ModuleWatch.Flag f = w4.robot(Rule.GYRO);
    assertTrue(f.active, "the laptop still shows it: keep the robot still");
    assertEquals(0, f.count);
    assertNull(shown("watch/robot/GyroProblem"), "every power-on calibrates: nothing to fix");
    in.gyroCalibrating = false;
    step(1.2);
    assertFalse(f.active);
    in.enabled = true;
    in.gyroConnected = false;
    step(0.6);
    assertEquals(1, f.count);
    assertEquals("navX, NOT CONNECTED, ready", f.detail());
    assertTrue(shown("watch/robot/GyroProblem").startsWith("kWarning: The robot: gyro is not connected"));
  }

  /** Drives straight for {@code meters}, each module reporting {@code scale} of the true distance. */
  private void driveStraight(double meters, double... scale) {
    step(meters, () -> {
      for (int m = 0; m < 4; m++) {
        in.pos[m] += 0.02 * scale[m];
      }
    });
  }

  @Test
  void oneModuleReportingLessGroundOnAField() {
    in.onField = true;
    driveStraight(2.0, 1, 1, 0.92, 1);
    assertEquals(0, f4(2, Rule.RATIO).count, "not judged before 3 m");
    driveStraight(2.0, 1, 1, 0.92, 1);
    ModuleWatch.Flag f = f4(2, Rule.RATIO);
    assertTrue(f.active);
    assertTrue(f.detail().startsWith("-8.0% over "), f.detail());
    assertEquals(0, f4(0, Rule.RATIO).count + f4(1, Rule.RATIO).count + f4(3, Rule.RATIO).count);
    assertTrue(shown("watch/backleft/DriveRatioMismatch").contains("gear ratio may differ"));
  }

  @Test
  void theRatioCheckWaitsForAFieldAndRestsDuringATest() {
    driveStraight(5.0, 1, 1, 0.92, 1);
    assertEquals(0, f4(2, Rule.RATIO).count, "on blocks the wheels cover no ground together");
    in.onField = true;
    in.testing = true;
    driveStraight(5.0, 1, 1, 0.92, 1);
    assertEquals(0, f4(2, Rule.RATIO).count, "a slip test spins wheels against a wall");
  }

  @Test
  void oneSwerveMotorMuchHotterThanItsSiblings() {
    List<MotorGuard.Motor> list = motors(" drive", 62, 44, 45, 43);
    list.addAll(motors(" steer", 40, 41, 39, 40));
    list.add(new MotorGuard.Motor("Shooter leader", MotorKind.VORTEX, new FakeMotorChannel(80), true));
    w4.bindMotors(list);
    step(4.9);
    ModuleWatch.Flag f = w4.flags().stream().filter(x -> x.module.equals("frontleft drive")).findFirst().orElseThrow();
    assertEquals(0, f.count, "held for 5 s first");
    step(0.2);
    assertTrue(f.active);
    assertEquals("62 \u00b0C vs 44 \u00b0C", f.detail());
    assertEquals(1, w4.flags().stream().filter(x -> x.rule == Rule.SIBLINGS && x.count > 0).count());
    assertTrue(w4.flags().stream().noneMatch(x -> x.module.equals("Shooter leader")), "a mechanism has no siblings");
    assertTrue(shown("watch/frontleft drive/HotterThanSiblings").startsWith("kWarning: frontleft drive: runs much hotter"));
  }

  @Test
  void aDrivetrainWarmAllOverIsNotASiblingProblem() {
    w4.bindMotors(motors(" drive", 61, 58, 63, 60));
    step(10);
    assertTrue(w4.flags().stream().noneMatch(x -> x.count > 0));
  }

  @Test
  void aTuningTestRestsTheMotionChecksButNotTheBattery() {
    in.testing = true;
    in.steerSp[0] = 40;
    in.v[1] = -1;
    in.busVolts = 7.5;
    step(2.0);
    assertEquals(0, f4(0, Rule.STEER_OFF).count, "a steering test makes big errors on purpose");
    assertEquals(0, f4(1, Rule.BACKWARDS).count);
    assertEquals(1, w4.robot(Rule.LOW_BATTERY).count);
  }

  @Test
  void mostModulesAtOnceIsOneLineNamingTheSharedCause() {
    Arrays.fill(in.absIssue, 1);
    step(0.3);
    String line = shown("watch/modules/AbsoluteReadIssue");
    assertTrue(line.contains("4 modules (frontleft, frontright, backleft, backright)"), line);
    assertTrue(line.contains("something they share"), line);
    assertNull(alerts.showing.get("watch/frontleft/AbsoluteReadIssue"), "not a line per module as well");
  }

  @Test
  void theLaptopReadsEveryCheckOverNetworkTables() {
    NetworkTableInstance nt = NetworkTableInstance.create();
    try {
      FakeDrivetrain io = new FakeDrivetrain();
      SlothTuneHarnessTest.Signals ds = new SlothTuneHarnessTest.Signals();
      double[] now = {100};
      SlothTune tune = new SlothTune(io, nt, ds, () -> now[0], "test robot", SlothTuneConfig.parse("{}"), false,
          new SlothTuneHarnessTest.Ownership(), true);
      io.bus = 7.0;
      for (int i = 0; i < 25; i++) {
        io.step(0.02);
        now[0] += 0.02;
        tune.periodic();
      }
      String[] rules = nt.getStringArrayTopic(SlothTuneTopics.WATCH_RULES).subscribe(new String[0]).get();
      String[] who = nt.getStringArrayTopic(SlothTuneTopics.WATCH_WHO).subscribe(new String[0]).get();
      double[] values = nt.getDoubleArrayTopic(SlothTuneTopics.WATCH_VALUES).subscribe(new double[0]).get();
      assertEquals(rules.length, who.length);
      assertEquals(rules.length * ModuleWatch.STRIDE, values.length);
      for (Rule r : Rule.values()) {
        assertTrue(Arrays.asList(rules).contains(r.laptop), r.laptop);
      }
      int battery = Arrays.asList(rules).indexOf("low_battery");
      assertEquals("", who[battery], "the whole robot");
      assertEquals(1, values[battery * ModuleWatch.STRIDE], "active");
      assertEquals(1, values[battery * ModuleWatch.STRIDE + 1], "one episode");
      assertEquals(7.0, values[battery * ModuleWatch.STRIDE + 3], 1e-9);
      assertTrue(Arrays.asList(who).contains("frontleft steer"), "the guard's swerve motors are compared too");
    } finally {
      nt.close();
    }
  }

  @Test
  void aLoopAllocatesNothing() {
    java.lang.management.ThreadMXBean base = ManagementFactory.getThreadMXBean();
    assumeTrue(base instanceof com.sun.management.ThreadMXBean, "needs HotSpot's allocation counter");
    com.sun.management.ThreadMXBean bean = (com.sun.management.ThreadMXBean) base;
    assumeTrue(bean.isThreadAllocatedMemorySupported());
    bean.setThreadAllocatedMemoryEnabled(true);
    // A busy robot: every check judging, some raising and clearing, the ratio adding up on a field.
    List<MotorGuard.Motor> list = motors(" drive", 62, 44, 45, 43);
    list.addAll(motors(" steer", 40, 41, 39, 40));
    w4.bindMotors(list);
    in.onField = true;
    in.faults[3] = "drive CAN fault";
    in.gyroCalibrating = true;
    for (int i = 0; i < 20000; i++) {
      busyLoop(i);
    }
    long probe = bean.getCurrentThreadAllocatedBytes();
    sink = new double[1000];
    assertTrue(bean.getCurrentThreadAllocatedBytes() - probe >= 8000, "the counter sees an allocation");
    long before = bean.getCurrentThreadAllocatedBytes();
    for (int i = 20000; i < 30000; i++) {
      busyLoop(i);
    }
    long used = bean.getCurrentThreadAllocatedBytes() - before;
    // A single small object per loop would be 160,000 bytes here.
    assertTrue(used < 4096, used + " bytes allocated over 10,000 loops");
    assertTrue(w4.changes() > 10, "the loops did raise and clear flags");
  }

  /** Where the counter's self-check puts its array, so the compiler can't drop it. */
  private static volatile Object sink;

  private void busyLoop(int i) {
    t += 0.02;
    in.steer[0] = (i / 5) % 2 == 0 ? 6 : -6;
    in.steerSp[1] = (i / 100) % 2 == 0 ? 0 : 30;
    in.absIssue[2] = (i / 50) % 3 == 0 ? 1 : 0;
    in.busVolts = (i / 75) % 2 == 0 ? 12.5 : 7.5;
    for (int m = 0; m < 4; m++) {
      in.pos[m] += 0.02 * (m == 2 ? 0.92 : 1);
    }
    w4.update(t, in);
  }
}
