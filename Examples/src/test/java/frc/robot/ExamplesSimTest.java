package frc.robot;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.hal.HAL;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.simulation.DriverStationSim;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import frc.robot.Subsystems.Elevator;
import frc.robot.Subsystems.Feeder;
import frc.robot.Subsystems.Shooter;
import frc.robot.Subsystems.ShooterPivot;
import frc.robot.Subsystems.TwoJointArm;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * Each past season's mechanism, rebuilt, in the simulator: its own commands move it under WPILib's
 * physics, through the SPARK's own loop, to where it should be.
 */
class ExamplesSimTest {

  @BeforeAll
  static void enabled() {
    HAL.initialize(500, 0);
    DriverStationSim.setEnabled(true);
    DriverStationSim.notifyNewData();
    DriverStation.refreshData();
  }

  /** Runs the scheduler (each subsystem's periodic and its physics) for a while, or until done. */
  static void run(Command c, double seconds, BooleanSupplier watch) {
    CommandScheduler.getInstance().schedule(c);
    for (int i = 0; i < seconds / 0.02; i++) {
      DriverStationSim.notifyNewData();
      CommandScheduler.getInstance().run();
      if (watch != null && !watch.getAsBoolean()) {
        throw new AssertionError("broke its rule at step " + i);
      }
    }
  }

  @Test
  void theElevatorLiftsToEachLevelAndHolds() {
    Elevator e = new Elevator();
    run(e.toL3(), 3.0, null);
    assertEquals(Elevator.L3, e.position(), 0.02, "at L3, held up by kG");
    run(e.toL1(), 3.0, null);
    assertEquals(Elevator.L1, e.position(), 0.02);
    run(e.goTo(5.0), 3.0, null);
    assertTrue(e.position() <= Elevator.MAX_HEIGHT + 0.01, "never past its top");
  }

  @Test
  void theShooterPivotGoesToItsPresetsAndStaysInside() {
    ShooterPivot p = new ShooterPivot();
    run(p.toAmp(), 3.0, null);
    assertEquals(ShooterPivot.AMP, p.degrees(), 2.0);
    run(p.toSubwoofer(), 3.0, null);
    assertEquals(ShooterPivot.SUBWOOFER, p.degrees(), 2.0);
    run(p.aimAtSpeaker(() -> 3.0), 2.0, null);
    assertEquals(Math.toDegrees(Math.atan2(2.0066, 3.0)), p.degrees(), 2.0, "2024's camera aim");
  }

  @Test
  void theArmTucksItsElbowBeforeTheShoulderMoves() {
    TwoJointArm a = new TwoJointArm();
    double startShoulder = a.shoulderDegrees();
    // Until the elbow has tucked, the shoulder stays where it was.
    boolean[] tucked = {false};
    BooleanSupplier rule = () -> {
      tucked[0] |= Math.abs(a.elbowDegrees() - TwoJointArm.ELBOW_TUCKED) < 3.0;
      return tucked[0] || Math.abs(a.shoulderDegrees() - startShoulder) < 2.0;
    };
    run(a.moveTo(TwoJointArm.Pose.CONE_HIGH), 12.0, rule);
    assertEquals(TwoJointArm.Pose.CONE_HIGH.shoulder, a.shoulderDegrees(), 3.0);
    assertEquals(TwoJointArm.Pose.CONE_HIGH.elbow, a.elbowDegrees(), 3.0);
  }

  @Test
  void theShooterWheelsReachTheirSpeedsAndThenItKicks() {
    Shooter s = new Shooter();
    // A 60 A limit on each wheel spins it up in a couple of seconds.
    run(s.speaker(), 4.0, null);
    assertTrue(s.atSpeed(), "both wheels within 3% of left " + Shooter.SPEAKER_LEFT_RPM + ", right " + Shooter.SPEAKER_RIGHT_RPM);
  }

  @Test
  void theFeederRunsAtItsSpeedUntilTheBeamBreaks() {
    Feeder f = new Feeder();
    Command in = f.intakeNote();
    run(in, 2.0, null);
    assertTrue(in.isScheduled(), "the simulator's beam is never broken, so it keeps going");
    assertTrue(!f.hasNote());
    assertEquals(Feeder.FEED_RPM, f.rpm(), 0.03 * Feeder.FEED_RPM);
  }
}
