package frc.lib.slothtune;

import com.revrobotics.spark.SparkBase;

/**
 * Lets a subsystem list its motors for the {@link MotorGuard} without depending on the tuning
 * tools. {@code tune::watchMotor} is one:
 *
 * <pre>
 *   // in the subsystem
 *   public void watchMotors(MotorWatcher w) {
 *     w.watch("Shooter leader", leader, MotorKind.VORTEX);
 *   }
 *   // in Robot
 *   shooter.watchMotors(tune::watchMotor);
 * </pre>
 */
@FunctionalInterface
public interface MotorWatcher {
  void watch(String name, SparkBase spark, MotorKind kind);
}
