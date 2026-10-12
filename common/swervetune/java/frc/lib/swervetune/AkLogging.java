package frc.lib.swervetune;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.kinematics.SwerveModuleState;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.RobotBase;
import java.io.File;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.littletonrobotics.junction.Logger;
import org.littletonrobotics.junction.networktables.NT4Publisher;
import org.littletonrobotics.junction.wpilog.WPILOGWriter;

/**
 * AdvantageKit on both robots: every match logged to a USB stick, and everything streamed live to
 * AdvantageScope. The only class in the library that knows AdvantageKit exists.
 *
 * <p>What AdvantageKit records on its own once started: the Driver Station (mode, joysticks),
 * {@code SystemStats} (battery voltage and current, brownouts, and the CAN bus's utilization,
 * bus-off, TX-full and receive/transmit error counts) and {@code PowerDistribution} (every PDH
 * channel's current, the PDH voltage, faults and sticky faults). Those are the raw signals the
 * CAN and power fault finding reads.
 *
 * <p>What this adds every loop, under AdvantageKit's {@code RealOutputs}:
 *
 * <ul>
 *   <li>{@code SwerveStates/Measured} and {@code SwerveStates/Setpoints}: AdvantageScope's Swerve
 *       tab draws these;
 *   <li>{@code Odometry/Robot}: its Field tab draws this;
 *   <li>{@code Motors/<name>/...}: every motor the guard watches - stage, heat, temperature,
 *       current, limit, the controller's own supply voltage, and any failure it has flagged;
 *   <li>{@code SwerveTune/Test}: which tuning test, if any, was running.
 * </ul>
 *
 * <p>No log is ever written to the roboRIO's own small flash: without a USB stick, data is only
 * streamed live.
 */
public final class AkLogging {
  private static boolean started;
  private static final Map<String, String[]> KEYS = new HashMap<>();

  private AkLogging() {}

  /**
   * Starts AdvantageKit. Call it first in {@code Robot}'s constructor; {@code Robot} must extend
   * {@code LoggedRobot}.
   *
   * @return where the logs go, in a sentence
   */
  public static String start(String project) {
    if (started) {
      return "AdvantageKit was already started.";
    }
    Logger.recordMetadata("ProjectName", project);
    Logger.recordMetadata("SwerveTuneProtocol", Integer.toString(SwerveTuneTopics.PROTOCOL_VERSION));
    String where;
    if (RobotBase.isReal()) {
      File usb = new File("/U");
      if (usb.isDirectory() && usb.canWrite()) {
        Logger.addDataReceiver(new WPILOGWriter("/U/logs"));
        where = "Logging every match to the USB stick (/U/logs) and streaming to AdvantageScope.";
      } else {
        where = "No USB stick in the roboRIO: streaming live to AdvantageScope, but no match log is"
            + " kept. Insert a FAT32 USB stick to keep logs.";
        DriverStation.reportWarning("[AdvantageKit] " + where, false);
      }
    } else {
      where = "Simulation: streaming live to AdvantageScope; nothing is saved.";
    }
    Logger.addDataReceiver(new NT4Publisher());
    Logger.recordMetadata("LogDestination", where);
    Logger.start();
    started = true;
    System.out.println("[swervetune] " + where);
    return where;
  }

  /** Whether {@link #start} ran: in unit tests it never does, and nothing is recorded. */
  public static boolean isStarted() {
    return started;
  }

  /** One loop's outputs. Called by {@link SwerveTune#periodic}. */
  static void record(DrivetrainIO io, List<MotorGuard.Motor> motors, String test) {
    if (!started) {
      return;
    }
    int n = io.moduleCount();
    SwerveModuleState[] measured = new SwerveModuleState[n];
    SwerveModuleState[] setpoints = new SwerveModuleState[n];
    for (int m = 0; m < n; m++) {
      double angle = io.steerDeg(m);
      measured[m] = new SwerveModuleState(io.driveMps(m), Rotation2d.fromDegrees(angle));
      double spV = io.driveSetpointMps(m);
      double spA = io.steerSetpointDeg(m);
      setpoints[m] = new SwerveModuleState(Double.isFinite(spV) ? spV : 0,
          Rotation2d.fromDegrees(Double.isFinite(spA) ? spA : angle));
    }
    Logger.recordOutput("SwerveStates/Measured", measured);
    Logger.recordOutput("SwerveStates/Setpoints", setpoints);
    double[] p = io.pose();
    Logger.recordOutput("Odometry/Robot", new Pose2d(p[0], p[1], Rotation2d.fromDegrees(p[2])));
    Logger.recordOutput("Drive/GyroYawDeg", io.headingDeg());
    for (MotorGuard.Motor m : motors) {
      String[] k = KEYS.computeIfAbsent(m.name, name -> {
        String b = "Motors/" + name + "/";
        return new String[] {b + "Stage", b + "HeatPct", b + "TempC", b + "Amps", b + "LimitA",
            b + "BusVolts", b + "Flags"};
      });
      Logger.recordOutput(k[0], m.stage().name());
      Logger.recordOutput(k[1], 100 * m.heatFraction());
      Logger.recordOutput(k[2], m.tempC());
      Logger.recordOutput(k[3], m.amps());
      Logger.recordOutput(k[4], m.activeLimitA());
      Logger.recordOutput(k[5], m.busVolts());
      Logger.recordOutput(k[6], m.flags());
    }
    Logger.recordOutput("SwerveTune/Test", test);
  }
}
