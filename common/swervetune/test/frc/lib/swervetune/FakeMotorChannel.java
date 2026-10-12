package frc.lib.swervetune;

/**
 * A motor for the {@link MotorGuard} tests. Current is what is asked for, capped by the limit in
 * force (unless {@link #ignoresLimit}, a controller that is not obeying); {@link #advance} turns
 * the shaft.
 */
final class FakeMotorChannel implements MotorGuard.MotorChannel {
  final int configured;
  int limit;
  double demandA;
  double tempC = 25;
  double duty;
  double rpm;
  double rotations;
  boolean ignoresLimit;
  boolean refuses;
  boolean simulated;
  String faults = "";
  String sticky = "";
  int sends;

  FakeMotorChannel(int configuredLimitA) {
    this.configured = configuredLimitA;
    this.limit = configuredLimitA;
  }

  void advance(double dt) {
    rotations += rpm / 60 * dt;
  }

  @Override
  public double amps() {
    return ignoresLimit ? demandA : Math.min(demandA, limit);
  }

  @Override
  public double tempC() {
    return tempC;
  }

  @Override
  public double appliedDuty() {
    return duty;
  }

  @Override
  public double motorRotations() {
    return rotations;
  }

  @Override
  public String activeFaults() {
    return faults;
  }

  @Override
  public String stickyFaults() {
    return sticky;
  }

  @Override
  public int configuredLimitA() {
    return configured;
  }

  @Override
  public boolean setCurrentLimit(int amps) {
    sends++;
    if (refuses) {
      return false;
    }
    limit = amps;
    return true;
  }

  @Override
  public boolean simulated() {
    return simulated;
  }
}
