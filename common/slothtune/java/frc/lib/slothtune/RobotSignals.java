package frc.lib.slothtune;

import edu.wpi.first.wpilibj.DriverStation;

/**
 * What the harness needs to know from the Driver Station.
 *
 * <p>An interface so the unit tests can play the Driver Station, and so the 2027 change —
 * {@code DriverStation} splitting into {@code MatchState} and {@code RobotState}, and Test mode
 * becoming Utility mode — is confined to {@link Wpilib}.
 */
public interface RobotSignals {
  boolean enabled();

  boolean autonomous();

  boolean testMode();

  boolean eStopped();

  boolean fmsAttached();

  /** Largest absolute deflection of the driver's override axes, 0..1. */
  double driverStickMax();

  /** Whether the driver is holding the deadman button. */
  boolean controllerDeadman();

  /**
   * The CAN bus: {@code {utilization 0-1, busOffCount, txFullCount, receiveErrors, transmitErrors}}.
   * The error numbers are the CAN controller's live error counters, not totals: above zero means
   * errors are happening now. Bus-off and TX-full are counts since power-on. Empty if unknown.
   */
  default double[] canStatus() {
    return new double[0];
  }

  /** A Driver Station port's axes as the robot code receives them; empty with no joystick there. */
  default double[] stickAxes(int port) {
    return new double[0];
  }

  /** A port's buttons pressed now: bit 0 is button 1. */
  default int stickButtons(int port) {
    return 0;
  }

  /** A port's first D-pad (POV) in degrees, -1 when released or missing. */
  default int stickPov(int port) {
    return -1;
  }

  /** The joystick's name as the Driver Station reports it. */
  default String stickName(int port) {
    return "";
  }

  default boolean stickIsXbox(int port) {
    return false;
  }

  /** WPILib 2026 Driver Station implementation. */
  final class Wpilib implements RobotSignals {
    private final int port;
    private final int[] axes;
    private final int deadmanPort;
    private final int deadmanButton;

    public Wpilib(int driverPort, int[] overrideAxes, int deadmanPort, int deadmanButton) {
      this.port = driverPort;
      this.axes = overrideAxes.clone();
      this.deadmanPort = deadmanPort;
      this.deadmanButton = deadmanButton;
    }

    @Override
    public boolean enabled() {
      return DriverStation.isEnabled();
    }

    @Override
    public boolean autonomous() {
      return DriverStation.isAutonomous();
    }

    @Override
    public boolean testMode() {
      return DriverStation.isTest();
    }

    @Override
    public boolean eStopped() {
      return DriverStation.isEStopped();
    }

    @Override
    public boolean fmsAttached() {
      return DriverStation.isFMSAttached();
    }

    @Override
    public double driverStickMax() {
      if (!DriverStation.isJoystickConnected(port)) {
        return 0;
      }
      double max = 0;
      int count = DriverStation.getStickAxisCount(port);
      for (int a : axes) {
        if (a >= 0 && a < count) {
          max = Math.max(max, Math.abs(DriverStation.getStickAxis(port, a)));
        }
      }
      return max;
    }

    @Override
    public double[] canStatus() {
      edu.wpi.first.hal.can.CANStatus s = edu.wpi.first.wpilibj.RobotController.getCANStatus();
      return new double[] {s.percentBusUtilization, s.busOffCount, s.txFullCount,
          s.receiveErrorCount, s.transmitErrorCount};
    }

    @Override
    public boolean controllerDeadman() {
      return deadmanButton > 0
          && DriverStation.isJoystickConnected(deadmanPort)
          && deadmanButton <= DriverStation.getStickButtonCount(deadmanPort)
          && DriverStation.getStickButton(deadmanPort, deadmanButton);
    }

    @Override
    public double[] stickAxes(int p) {
      // Only axes the joystick has: asking for more makes the Driver Station print a warning.
      int n = DriverStation.getStickAxisCount(p);
      double[] out = new double[Math.max(0, n)];
      for (int i = 0; i < out.length; i++) {
        out[i] = DriverStation.getStickAxis(p, i);
      }
      return out;
    }

    @Override
    public int stickButtons(int p) {
      return DriverStation.getStickButtons(p);
    }

    @Override
    public int stickPov(int p) {
      return DriverStation.getStickPOVCount(p) > 0 ? DriverStation.getStickPOV(p, 0) : -1;
    }

    @Override
    public String stickName(int p) {
      return DriverStation.getJoystickName(p);
    }

    @Override
    public boolean stickIsXbox(int p) {
      return DriverStation.getJoystickIsXbox(p);
    }
  }
}
