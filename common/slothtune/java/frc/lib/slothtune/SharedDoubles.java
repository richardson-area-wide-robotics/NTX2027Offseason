package frc.lib.slothtune;

import java.util.concurrent.atomic.AtomicLongArray;

/**
 * Doubles written by the robot loop and read by the {@link Sampler} thread.
 *
 * <p>A plain {@code double[]} written on one thread is not guaranteed to be seen on another, so a
 * setpoint change could appear in the recording late, or never. That would put a fake delay into
 * every step response measured from it.
 */
final class SharedDoubles {
  private final AtomicLongArray bits;

  SharedDoubles(int size) {
    bits = new AtomicLongArray(size);
  }

  void set(int i, double v) {
    bits.set(i, Double.doubleToRawLongBits(v));
  }

  double get(int i) {
    return Double.longBitsToDouble(bits.get(i));
  }
}
