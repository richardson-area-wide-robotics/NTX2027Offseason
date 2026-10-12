package frc.lib.swervetune;

import java.util.Locale;

/**
 * Where the robot physically is while a test runs.
 *
 * <p>This is not a formality. It decides which tests may run, and which sensors can be believed
 * while they do:
 *
 * <ul>
 *   <li>On {@link #BLOCKS} the wheels spin but the chassis must not move, so the gyro, the
 *       accelerometer and any camera will <b>disagree with the wheels by design</b>. Tests there
 *       never use those sensors as ground truth, and the safety supervisor turns the disagreement
 *       around into an interlock: if the gyro sees the chassis turning while the wheels are
 *       driven, the robot is not on blocks and the test stops.
 *   <li>On {@link #FIELD} the robot really moves. Every test that spins a wheel needs a held
 *       deadman, is sized to the clear floor you declared, and stops on impact, stall, overspeed or
 *       a driver touching the sticks.
 *   <li>In {@link #SIM} YAGSL simulates the modules with its own controllers, so <b>your gains have
 *       no effect</b>. Simulation proves the plumbing — commands, safety, telemetry, the laptop
 *       tools and an agent's loop — not the tuning.
 * </ul>
 */
public enum TestEnvironment {
  /** Not declared. Only tests that command no motion may run. */
  UNSET(false, false),
  /** Desktop simulation. */
  SIM(true, true),
  /** Frame on blocks, every wheel clear of the floor. */
  BLOCKS(true, false),
  /** On the floor, and it will move. */
  FIELD(true, true);

  /** Whether any test may command a motor at all. */
  public final boolean allowsActuation;

  /** Whether the chassis is expected to move when the wheels are driven. */
  public final boolean chassisCanMove;

  TestEnvironment(boolean allowsActuation, boolean chassisCanMove) {
    this.allowsActuation = allowsActuation;
    this.chassisCanMove = chassisCanMove;
  }

  /** Whether a motion test needs a deadman held for its whole duration. */
  public boolean needsDeadman() {
    return this == FIELD;
  }

  /**
   * Parses a name from the laptop. Anything unrecognised is {@link #UNSET}, never a guess: an
   * environment typed wrong must not silently become one that allows motion.
   */
  public static TestEnvironment parse(String text) {
    if (text == null) {
      return UNSET;
    }
    try {
      return valueOf(text.trim().toUpperCase(Locale.ROOT));
    } catch (IllegalArgumentException e) {
      return UNSET;
    }
  }
}
