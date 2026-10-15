package frc.lib.slothtune;

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
  boolean present = true;
  boolean resetFlag;
  boolean brownout;
  int canId = 7;
  String model = "";
  String codeClass = "";
  /** The last test output a bring-up test asked for; NaN until one did. */
  /** Its idle mode: true coast; and every change asked of it, in order. */
  boolean coastNow;
  final java.util.List<Boolean> coastCalls = new java.util.ArrayList<>();
  double testDuty = Double.NaN;
  int testDutyCalls;
  /** The last volts an identification test asked for; NaN until one did. */
  double testVolts = Double.NaN;
  int testVoltsCalls;
  boolean follower;
  /** A controller a test can't run by voltage. */
  boolean noVolts;
  /** Every status-rate change asked of it, in order (0 puts back what it had). */
  final java.util.List<Integer> signalCalls = new java.util.ArrayList<>();
  double feedbackPos = Double.NaN;
  double feedbackVel = Double.NaN;

  FakeMotorChannel(int configuredLimitA) {
    this.configured = configuredLimitA;
    this.limit = configuredLimitA;
  }

  void advance(double dt) {
    rotations += rpm / 60 * dt;
  }

  @Override
  public Boolean coast() {
    return coastNow;
  }

  @Override
  public boolean setCoast(boolean coast) {
    coastNow = coast;
    coastCalls.add(coast);
    return true;
  }

  @Override
  public boolean testVolts(double v) {
    testVolts = v;
    testVoltsCalls++;
    return !noVolts;
  }

  @Override
  public boolean follower() {
    return follower;
  }

  @Override
  public double feedbackPosition() {
    return feedbackPos;
  }

  @Override
  public double feedbackVelocity() {
    return feedbackVel;
  }

  @Override
  public boolean fastSignals(int ms) {
    signalCalls.add(ms);
    return true;
  }

  @Override
  public boolean testDuty(double d) {
    testDuty = d;
    testDutyCalls++;
    return true;
  }

  @Override
  public String controllerModel() {
    return model;
  }

  @Override
  public String controllerClass() {
    return codeClass;
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

  /** Times Clear sticky faults reached it; and its settings as a SPARK reports them. */
  int clears;
  String settingsText = "";

  @Override
  public boolean clearStickyFaults() {
    sticky = "";
    clears++;
    return true;
  }

  @Override
  public String settings() {
    return settingsText;
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
  public boolean canPresent() {
    return present;
  }

  @Override
  public boolean resetSeen() {
    return resetFlag;
  }

  @Override
  public void clearResetFlag() {
    resetFlag = false;
  }

  @Override
  public boolean brownoutWarning() {
    return brownout;
  }

  @Override
  public int canId() {
    return canId;
  }

  @Override
  public boolean simulated() {
    return simulated;
  }
}
