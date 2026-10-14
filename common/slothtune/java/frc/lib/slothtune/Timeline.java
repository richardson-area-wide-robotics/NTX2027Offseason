package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.List;

/** A test written as a list of timed segments, each with a label the laptop can plot. */
final class Timeline {
  record Segment(String label, double durationS, double value) {}

  private final List<Segment> segments = new ArrayList<>();
  private final List<Double> starts = new ArrayList<>();
  private double total;

  Timeline add(String label, double durationS, double value) {
    starts.add(total);
    segments.add(new Segment(label, durationS, value));
    total += durationS;
    return this;
  }

  double totalS() {
    return total;
  }

  int size() {
    return segments.size();
  }

  /** Index of the segment running at {@code t}, or {@link #size()} once it has all run. */
  int indexAt(double t) {
    for (int i = segments.size() - 1; i >= 0; i--) {
      if (t >= starts.get(i)) {
        return t < starts.get(i) + segments.get(i).durationS() ? i : i + 1;
      }
    }
    return 0;
  }

  Segment get(int index) {
    return segments.get(index);
  }

  double startOf(int index) {
    return starts.get(index);
  }

  /** Seconds into the segment running at {@code t}. */
  double timeInto(int index, double t) {
    return t - starts.get(index);
  }
}
