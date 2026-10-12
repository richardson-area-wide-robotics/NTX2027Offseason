package frc.lib.swervetune;

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
    public boolean controllerDeadman() {
      return deadmanButton > 0
          && DriverStation.isJoystickConnected(deadmanPort)
          && deadmanButton <= DriverStation.getStickButtonCount(deadmanPort)
          && DriverStation.getStickButton(deadmanPort, deadmanButton);
    }
  }
}
