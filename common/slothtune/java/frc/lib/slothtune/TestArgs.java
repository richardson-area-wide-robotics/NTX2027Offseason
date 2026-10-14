package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Named numeric arguments for a test, sent from the laptop as two parallel arrays.
 *
 * <p>Lists are spelled {@code s0, s1, s2...}, which keeps the wire format to plain numbers that
 * any NetworkTables client can write without a JSON library on the robot.
 */
public final class TestArgs {
  private final Map<String, Double> values = new LinkedHashMap<>();

  public static TestArgs of(String[] keys, double[] values) {
    TestArgs args = new TestArgs();
    if (keys == null || values == null) {
      return args;
    }
    int n = Math.min(keys.length, values.length);
    for (int i = 0; i < n; i++) {
      if (keys[i] != null && Double.isFinite(values[i])) {
        args.values.put(keys[i].trim(), values[i]);
      }
    }
    return args;
  }

  public static TestArgs empty() {
    return new TestArgs();
  }

  public TestArgs with(String key, double value) {
    values.put(key, value);
    return this;
  }

  public boolean has(String key) {
    return values.containsKey(key);
  }

  public double get(String key, double fallback) {
    Double v = values.get(key);
    return v == null ? fallback : v;
  }

  /** {@code get} clamped to a range, so a typo on the laptop cannot ask for something absurd. */
  public double get(String key, double fallback, double min, double max) {
    return Math.max(min, Math.min(max, get(key, fallback)));
  }

  public boolean flag(String key, boolean fallback) {
    Double v = values.get(key);
    return v == null ? fallback : v != 0.0;
  }

  /** {@code prefix0, prefix1, ...} up to the first gap, or null if {@code prefix0} is absent. */
  public double[] list(String prefix) {
    List<Double> out = new ArrayList<>();
    for (int i = 0; values.containsKey(prefix + i); i++) {
      out.add(values.get(prefix + i));
    }
    if (out.isEmpty()) {
      return null;
    }
    double[] arr = new double[out.size()];
    for (int i = 0; i < arr.length; i++) {
      arr[i] = out.get(i);
    }
    return arr;
  }

  public Map<String, Double> asMap() {
    return Map.copyOf(values);
  }
}
