package frc.lib.swervetune;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.kinematics.SwerveModuleState;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.RuntimeType;
import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.littletonrobotics.conduit.ConduitApi;
import org.littletonrobotics.junction.Logger;
import org.littletonrobotics.junction.networktables.NT4Publisher;
import org.littletonrobotics.junction.wpilog.WPILOGWriter;

/**
 * AdvantageKit on both robots: every match logged to a USB stick (or a roboRIO 2's SD card), and
 * everything streamed live to AdvantageScope. The only class in the library that knows AdvantageKit exists.
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
 * <p>Where logs go: a USB stick when one is plugged in ({@code /U/logs}). Without one, a roboRIO 2
 * logs to its SD card ({@code /home/lvuser/logs}), deleting its oldest logs first so the card keeps
 * {@value #SD_KEEP_FREE_MB} MB free, and not logging at all if it cannot keep
 * {@value #SD_MIN_FREE_MB} MB free. A roboRIO 1 has no SD card - only a small internal flash that
 * the operating system needs - so without a stick it only streams live. WPILib's own
 * DataLogManager picks the same folders; AdvantageKit's logs are bigger, so this keeps more space
 * free than its 50 MB.
 */
public final class AkLogging {
  static final String USB_LOGS = "/U/logs";
  static final String SD_LOGS = "/home/lvuser/logs";
  static final long SD_KEEP_FREE_MB = 1000;
  static final long SD_MIN_FREE_MB = 300;
  static final int KEEP_NEWEST = 10;
  private static final long MB = 1_000_000L;
  private static final int SPACE_CHECK_LOOPS = 1500;
  private static final long LOW_SPACE_MB = 150;

  private static boolean started;
  private static String logFolder;
  private static int loops;
  private static boolean warnedLowSpace;
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
      String folder = chooseFolder(usb.isDirectory() && usb.canWrite(), RobotBase.getRuntimeType());
      if (USB_LOGS.equals(folder)) {
        where = "Logging every match to the USB stick (" + USB_LOGS + ") and streaming to AdvantageScope.";
      } else if (SD_LOGS.equals(folder)) {
        File dir = new File(SD_LOGS);
        dir.mkdirs();
        List<File> gone = pruneOldLogs(dir, SD_KEEP_FREE_MB * MB, KEEP_NEWEST, dir.getUsableSpace());
        for (File f : gone) {
          System.out.println("[swervetune] Deleted old log " + f.getName() + " to keep the SD card from filling.");
        }
        long freeMb = dir.getUsableSpace() / MB;
        if (freeMb >= SD_MIN_FREE_MB) {
          where = "No USB stick: logging every match to the roboRIO 2's SD card (" + SD_LOGS + ", "
              + freeMb + " MB free" + (gone.isEmpty() ? "" : ", " + gone.size() + " oldest logs deleted")
              + ") and streaming to AdvantageScope. To download them, set AdvantageScope's roboRIO log"
              + " folder to " + SD_LOGS + ".";
        } else {
          folder = null;
          where = "No USB stick, and the SD card has only " + freeMb + " MB free (logging needs "
              + SD_MIN_FREE_MB + " MB): streaming live to AdvantageScope, but no match log is kept."
              + " Insert a FAT32 USB stick to keep logs.";
          DriverStation.reportWarning("[AdvantageKit] " + where, false);
        }
      } else {
        where = "No USB stick in the roboRIO 1 (it has no SD card to log to): streaming live to"
            + " AdvantageScope, but no match log is kept. Insert a FAT32 USB stick to keep logs.";
        DriverStation.reportWarning("[AdvantageKit] " + where, false);
      }
      if (folder != null) {
        Logger.addDataReceiver(new WPILOGWriter(folder));
        logFolder = folder;
      }
    } else {
      // Off by default so simulation never fills a disk; set AKIT_SIM_LOG to a folder to keep logs
      // from a simulated run, e.g. to test the post-match summary.
      String simLog = System.getenv("AKIT_SIM_LOG");
      if (simLog != null && !simLog.isBlank()) {
        Logger.addDataReceiver(new WPILOGWriter(simLog));
        logFolder = simLog;
        where = "Simulation: logging to " + simLog + " and streaming to AdvantageScope.";
      } else {
        where = "Simulation: streaming live to AdvantageScope; nothing is saved.";
      }
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

  /**
   * Every PDH channel's current this loop, amps: the same snapshot AdvantageKit logs, read through
   * its Conduit layer, because a second {@code PowerDistribution} handle would be refused. Empty
   * before {@link #start}.
   */
  public static double[] pdhCurrents() {
    if (!started) {
      return new double[0];
    }
    ConduitApi c = ConduitApi.getInstance();
    double[] out = new double[Math.max(0, c.getPDPChannelCount())];
    for (int i = 0; i < out.length; i++) {
      out[i] = c.getPDPChannelCurrent(i);
    }
    return out;
  }

  /** The folder match logs are written to, or null when none are kept. */
  public static String logFolder() {
    return logFolder;
  }

  /**
   * Where to keep match logs: the USB stick if one is writable, else a roboRIO 2's SD card, else
   * nowhere (null) - a roboRIO 1's internal flash is too small to share with the operating system.
   */
  static String chooseFolder(boolean usbWritable, RuntimeType type) {
    if (usbWritable) {
      return USB_LOGS;
    }
    return type == RuntimeType.kRoboRIO2 ? SD_LOGS : null;
  }

  /**
   * Deletes the oldest {@code .wpilog} files in {@code dir} until {@code wantFreeBytes} are free,
   * always keeping the newest {@code keepNewest}: WPILib's DataLogManager rule, with a bigger
   * margin.
   *
   * @param usableBytes the free space now
   * @return the files deleted, oldest first
   */
  static List<File> pruneOldLogs(File dir, long wantFreeBytes, int keepNewest, long usableBytes) {
    List<File> deleted = new ArrayList<>();
    File[] logs = dir.listFiles((d, name) -> name.toLowerCase().endsWith(".wpilog"));
    if (logs == null || usableBytes >= wantFreeBytes) {
      return deleted;
    }
    Arrays.sort(logs, Comparator.comparingLong(File::lastModified));
    long free = usableBytes;
    for (int i = 0; i < logs.length - keepNewest && free < wantFreeBytes; i++) {
      long size = logs[i].length();
      if (logs[i].delete()) {
        deleted.add(logs[i]);
        free += size;
      }
    }
    return deleted;
  }

  /**
   * Every live gain, whenever one changes (and once at the start), so a match log says what the
   * robot was running. Under {@code RealOutputs/SwerveTune/Gains/}.
   */
  static void recordGains(Map<String, Double> gains) {
    if (!started) {
      return;
    }
    for (Map.Entry<String, Double> e : gains.entrySet()) {
      Logger.recordOutput("SwerveTune/Gains/" + e.getKey(), e.getValue());
    }
  }

  /** Warns once if the disk being logged to runs low during a long session. */
  private static void checkSpace() {
    if (logFolder == null || warnedLowSpace || ++loops < SPACE_CHECK_LOOPS) {
      return;
    }
    loops = 0;
    long freeMb = new File(logFolder).getUsableSpace() / MB;
    if (freeMb < LOW_SPACE_MB) {
      warnedLowSpace = true;
      DriverStation.reportWarning("[AdvantageKit] Only " + freeMb + " MB left where logs are kept ("
          + logFolder + "). Download and delete old logs; restarting the robot code also clears the"
          + " oldest on a roboRIO 2's SD card.", false);
    }
  }

  /** One loop's outputs. Called by {@link SwerveTune#periodic}. */
  static void record(DrivetrainIO io, List<MotorGuard.Motor> motors, String test) {
    if (!started) {
      return;
    }
    checkSpace();
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
            b + "BusVolts", b + "Flags", b + "Present", b + "Dropouts", b + "Resets", b + "Brownouts"};
      });
      Logger.recordOutput(k[0], m.stage().name());
      Logger.recordOutput(k[1], 100 * m.heatFraction());
      Logger.recordOutput(k[2], m.tempC());
      Logger.recordOutput(k[3], m.amps());
      Logger.recordOutput(k[4], m.activeLimitA());
      Logger.recordOutput(k[5], m.busVolts());
      Logger.recordOutput(k[6], m.flags());
      Logger.recordOutput(k[7], m.present());
      Logger.recordOutput(k[8], m.dropouts());
      Logger.recordOutput(k[9], m.resets());
      Logger.recordOutput(k[10], m.brownouts());
    }
    Logger.recordOutput("SwerveTune/Test", test);
  }
}
