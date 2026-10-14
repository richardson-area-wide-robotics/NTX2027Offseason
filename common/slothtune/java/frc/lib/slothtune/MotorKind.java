package frc.lib.slothtune;

/**
 * Every REV motor on the robot, with the team's current-limit policy and the thermal numbers the
 * {@link MotorGuard} protects it with.
 *
 * <p><b>Why a heat model and not just the temperature sensor.</b> On the NEO 550 and NEO V1.1 the
 * sensor sits on the hall-sensor board, not in the windings, and lags them by tens of seconds. In
 * REV's own locked-rotor tests a NEO 550 at 40 A burnt out after about 27 s while its sensor still
 * read about 40 &deg;C (docs.revrobotics.com/brushless/neo/locked-rotor-testing). A guard that waits
 * for the sensor protects nothing. So the guard also integrates a first-order heat model driven by
 * current, {@code rise' = (k*I^2 - rise) / tau}, fitted to REV's failure times:
 *
 * <ul>
 *   <li>NEO 550: fails ~27 s at 40 A, ~5.5 s at 60 A, ~2 s at 80 A, survives 220 s at 20 A. Fits
 *       tau = 10 s, k = 0.082 &deg;C/A^2 to a ~115 &deg;C winding rise (REV: enamel fails near 140
 *       &deg;C).
 *   <li>NEO V1.1: ~105 s at 60 A, ~43 s at 80 A, survives 180 s at 50 A. Fits tau = 100 s, k = 0.050.
 *   <li>NEO 2.0 and Vortex: REV publishes no locked-rotor data. The NEO 2.0 uses the V1.1 model
 *       (its published stall figures are the V1.1's theoretical ones). The Vortex model scales the
 *       NEO's by winding resistance (stall 211 A against 105 A): <b>an estimate</b>.
 * </ul>
 *
 * <p>Sensor thresholds and stall times are the researched conservative choices; REV publishes no
 * temperature limits. Current limits are the team's policy: Vortex 80 A, NEO 1.1 60 A, NEO 2.0
 * 80 A, NEO 550 20 A. A NEO 1.1 and a NEO 2.0 cannot be told apart electrically, so a NEO of unknown
 * version gets the stricter of each number until the inventory says which it is.
 */
public enum MotorKind {
  // label, policy amps, free rpm, sensor warn/derate/shutoff C, tau s, k C/A^2, stall cut s
  NEO_550("NEO 550", 20, 11000, 45, 55, 65, 10.0, 0.082, 30),
  NEO_V1_1("NEO V1.1", 60, 5676, 70, 80, 90, 100.0, 0.050, 30),
  NEO_2_0("NEO 2.0", 80, 5676, 70, 80, 90, 100.0, 0.050, 10),
  NEO_UNKNOWN("NEO (1.1 or 2.0?)", 60, 5676, 70, 80, 90, 100.0, 0.050, 10),
  VORTEX("NEO Vortex", 80, 6784, 85, 100, 110, 100.0, 0.025, 10);

  /** Winding temperature rise, above ambient, that the heat model treats as failure. */
  public static final double FAILURE_RISE_C = 115.0;

  public final String label;
  public final int policyAmps;
  public final double freeRpm;
  public final double warnC;
  public final double derateC;
  public final double shutoffC;
  public final double tauS;
  public final double kRisePerAmp2;
  public final double stallCutS;

  MotorKind(String label, int policyAmps, double freeRpm, double warnC, double derateC,
      double shutoffC, double tauS, double kRisePerAmp2, double stallCutS) {
    this.label = label;
    this.policyAmps = policyAmps;
    this.freeRpm = freeRpm;
    this.warnC = warnC;
    this.derateC = derateC;
    this.shutoffC = shutoffC;
    this.tauS = tauS;
    this.kRisePerAmp2 = kRisePerAmp2;
    this.stallCutS = stallCutS;
  }

  /** From an inventory name or a YAGSL motor type, e.g. {@code neo550}, {@code sparkflex_vortex}. */
  public static MotorKind parse(String text) {
    String t = text == null ? "" : text.toLowerCase(java.util.Locale.ROOT).replace(" ", "").replace(".", "");
    if (t.contains("550")) {
      return NEO_550;
    }
    if (t.contains("vortex") || t.contains("sparkflex")) {
      return VORTEX;
    }
    if (t.contains("neo20") || t.contains("neo2_0") || t.contains("neo_2_0") || t.equals("neo2")) {
      return NEO_2_0;
    }
    if (t.contains("neo11") || t.contains("neov11") || t.contains("neo_v1_1") || t.contains("neo1_1")) {
      return NEO_V1_1;
    }
    return NEO_UNKNOWN;
  }
}
