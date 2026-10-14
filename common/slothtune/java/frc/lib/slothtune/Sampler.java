package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.DoubleSupplier;

/**
 * Records named channels at a fixed rate, faster than the 50 Hz robot loop.
 *
 * <p>A steering module settles in roughly a tenth of a second, which is five robot loops. Five
 * points cannot show overshoot or ringing, so a step test sampled at the loop rate would hide the
 * very thing it is there to measure. {@link SlothTune} calls {@link #sampleNow} from its own
 * timer thread, by default at 200 Hz, and every row is timestamped.
 *
 * <p>Nothing in here touches WPILib, so it survives the 2027 package rename untouched and the unit
 * tests drive it directly.
 *
 * <p>Setpoints are still changed from the robot loop. The procedures keep their current setpoint
 * in a {@code volatile} field that a channel reads, so a setpoint change appears in the recording
 * on the first sample after it happened — the timing is recorded rather than assumed.
 *
 * <p>Angle channels are unwrapped as they are recorded: 359 followed by 1 is stored as 359, 361.
 * A step through the wrap point would otherwise read as a 358 degree error.
 */
public final class Sampler {
  private record Channel(String name, DoubleSupplier source, boolean angle) {}

  private final List<Channel> channels = new ArrayList<>();
  private final int capacity;
  private double[][] data = new double[0][];
  private double[] lastRaw = new double[0];
  private double[] turns = new double[0];
  private int count;
  private double startS;
  private DoubleSupplier clock;
  private volatile boolean recording;

  /** Use {@link #create}, which puts the time channel first where {@link #sampleNow} expects it. */
  private Sampler(int capacity) {
    this.capacity = Math.max(16, capacity);
  }

  /** Adds a plain channel. Must be called before {@link #start}. */
  public Sampler channel(String name, DoubleSupplier source) {
    channels.add(new Channel(name, source, false));
    return this;
  }

  /** Adds an angle channel, in degrees, unwrapped as it is recorded. */
  public Sampler angle(String name, DoubleSupplier sourceDegrees) {
    channels.add(new Channel(name, sourceDegrees, true));
    return this;
  }

  /**
   * Starts recording. Rows are taken each time {@link #sampleNow} is called.
   *
   * @param clock seconds, monotonic; the robot's FPGA clock in practice
   */
  public synchronized void start(DoubleSupplier clock) {
    this.clock = clock;
    int n = channels.size();
    data = new double[n][capacity];
    lastRaw = new double[n];
    turns = new double[n];
    count = 0;
    startS = clock.getAsDouble();
    recording = true;
  }

  /** Records one row now. Called from the harness's timer thread, or directly by tests. */
  public synchronized void sampleNow() {
    if (!recording || count >= capacity) {
      return;
    }
    int row = count;
    data[0][row] = clock.getAsDouble() - startS;
    for (int c = 1; c < channels.size(); c++) {
      Channel ch = channels.get(c);
      double v;
      try {
        v = ch.source.getAsDouble();
      } catch (RuntimeException e) {
        v = Double.NaN;
      }
      if (ch.angle && Double.isFinite(v)) {
        if (row > 0 && Double.isFinite(lastRaw[c])) {
          double delta = v - lastRaw[c];
          if (delta > 180) {
            turns[c] -= 1;
          } else if (delta < -180) {
            turns[c] += 1;
          }
        }
        lastRaw[c] = v;
        v += 360.0 * turns[c];
      }
      data[c][row] = v;
    }
    count++;
  }

  /** Stops recording. Data stays readable. */
  public synchronized void stop() {
    recording = false;
  }

  public synchronized int rows() {
    return count;
  }

  public synchronized boolean overflowed() {
    return count >= capacity;
  }

  /** Channel names, {@code t} first. */
  public List<String> names() {
    List<String> names = new ArrayList<>();
    for (Channel c : channels) {
      names.add(c.name);
    }
    return names;
  }

  /** Copies of every channel trimmed to the rows recorded. */
  public synchronized Map<String, double[]> snapshot() {
    Map<String, double[]> out = new LinkedHashMap<>();
    for (int c = 0; c < channels.size(); c++) {
      double[] col = new double[count];
      System.arraycopy(data[c], 0, col, 0, count);
      out.put(channels.get(c).name, col);
    }
    return out;
  }

  /** Clears channels so the sampler can be reused for another test. */
  public synchronized void reset() {
    stop();
    channels.clear();
    channels.add(new Channel("t", () -> 0.0, false));
    count = 0;
  }

  /** A sampler with the time channel already in place. */
  public static Sampler create(int capacity) {
    Sampler s = new Sampler(capacity);
    s.channels.add(new Channel("t", () -> 0.0, false));
    return s;
  }
}
