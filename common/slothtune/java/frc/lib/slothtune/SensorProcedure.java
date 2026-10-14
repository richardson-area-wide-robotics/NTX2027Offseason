package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Bring-up's live sensor readout: every sensor's value, live, while a person trips each one by hand
 * (blocks the beam, presses the switch, turns the encoder), and whether it has changed yet.
 *
 * <p>Sensors are those the robot code registers ({@link SlothTune#watchSensor}) and those in the
 * deployed design file that it doesn't, opened from their ports for the readout only. Runs disabled
 * or enabled, commands nothing, and ends when asked (the laptop's Stop) or after {@code duration_s}.
 *
 * <p>Live line, for the laptop to light each sensor: {@code Sensors now: Intake beam = true
 * (changed)}, one sensor after another, separated by middle dots. Channels {@code s0..sN}; notes
 * {@code sensor i: name (how it is read)}; meta {@code sI.changes}, {@code sI.changed}, {@code
 * sI.min}, {@code sI.max}, counted from every sample.
 */
final class SensorProcedure implements Procedure {
  static final double RATE_HZ = 50;
  private volatile boolean stopRequested;
  private double durationS;
  private final List<Slot> slots = new ArrayList<>();

  /** One sensor in the readout: how to read it, how much is a change, and what it has done. */
  static final class Slot {
    final String name;
    /** digital, analog, dutycycle, encoder (from the design); switch, number (from the code). */
    final String kind;
    final String how;
    final Sensors.Reader reader;
    /** Why it can't be read; null when it can. */
    final String problem;
    final boolean opened;
    private volatile boolean closed;
    private volatile double first = Double.NaN;
    private volatile double last = Double.NaN;
    private volatile double min = Double.NaN;
    private volatile double max = Double.NaN;
    /** Farthest from the first reading so far (around the turn, for an absolute encoder). */
    private volatile double farthest;
    private volatile int changes;

    Slot(String name, String kind, String how, Sensors.Reader reader, String problem, boolean opened) {
      this.name = name;
      this.kind = kind;
      this.how = how;
      this.reader = reader;
      this.problem = problem;
      this.opened = opened;
    }

    boolean isSwitch() {
      return kind.equals("digital") || kind.equals("switch");
    }

    /** How far a number must move from its first reading to count as changed. */
    double threshold() {
      switch (kind) {
        case "analog":
          return 0.1;    // volts: above an analog input's noise
        case "dutycycle":
          return 0.02;   // turns: about 7 degrees
        case "encoder":
          return 8;      // counts
        default:
          return Math.max(1e-3, 0.02 * Math.abs(first));
      }
    }

    /** One reading, on the sampler's thread; NaN when it can't be read. */
    double sample() {
      if (reader == null || closed) {
        return Double.NaN;
      }
      double v;
      try {
        v = reader.read();
      } catch (RuntimeException e) {
        return Double.NaN;
      }
      if (!Double.isFinite(v)) {
        return v;
      }
      if (Double.isNaN(first)) {
        first = v;
        min = v;
        max = v;
      } else {
        if (isSwitch() && v != last) {
          changes++;
        }
        min = Math.min(min, v);
        max = Math.max(max, v);
        double d = v - first;
        if (kind.equals("dutycycle")) {
          d -= Math.rint(d);  // 0.99 to 0.01 is a small move
        }
        farthest = Math.max(farthest, Math.abs(d));
      }
      last = v;
      return v;
    }

    boolean changed() {
      if (isSwitch()) {
        return changes > 0;
      }
      return !Double.isNaN(first) && farthest > threshold();
    }

    String valueText() {
      if (problem != null) {
        return "can't read";
      }
      double v = last;
      if (Double.isNaN(v)) {
        return "no reading yet";
      }
      switch (kind) {
        case "digital":
        case "switch":
          return v != 0 ? "true" : "false";
        case "analog":
          return String.format(Locale.ROOT, "%.2f V", v);
        case "dutycycle":
          return String.format(Locale.ROOT, "%.3f turns", v);
        case "encoder":
          return String.format(Locale.ROOT, "%.0f counts", v);
        default:
          return String.format(Locale.ROOT, "%.4g", v);
      }
    }

    void close() {
      closed = true;
      if (opened && reader != null) {
        try {
          reader.close();
        } catch (Exception e) {
          // Closing a port that failed half-way: nothing more to do.
        }
      }
    }
  }

  @Override
  public String name() {
    return "sensors";
  }

  @Override
  public boolean spinsWheels() {
    return false;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  @Override
  public boolean needsEnabled() {
    return false;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return true;
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.sensors.isEmpty() && ctx.designedSensors.isEmpty()) {
      return "No sensors to read: none registered by the robot code (watchSensor) and none in the"
          + " deployed design file (deploy/design/devices.json).";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return ctx.args.get("duration_s", 120, 5, 300) + 2;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return RATE_HZ;
  }

  @Override
  public void start(TestContext ctx) {
    stopRequested = false;
    durationS = ctx.args.get("duration_s", 120, 5, 300);
    slots.clear();
    Set<String> registered = new HashSet<>();
    for (Sensors.Registered r : ctx.sensors) {
      registered.add(r.name());
      slots.add(new Slot(r.name(), r.isSwitch() ? "switch" : "number",
          "registered by the robot code, " + (r.isSwitch() ? "a switch" : "a number"), r.read()::getAsDouble, null, false));
    }
    for (Sensors.Designed d : ctx.designedSensors) {
      if (registered.contains(d.name())) {
        continue;  // the code's own reading is the one that matters
      }
      String how = d.type() + " " + portsText(d.ports());
      if (ctx.sensorPorts == null) {
        slots.add(new Slot(d.name(), d.type(), how, null, "this robot code can't open ports for the readout", false));
        continue;
      }
      try {
        slots.add(new Slot(d.name(), d.type(), how + ", opened for the readout", ctx.sensorPorts.open(d.type(), d.ports()), null, true));
      } catch (RuntimeException e) {
        slots.add(new Slot(d.name(), d.type(), how, null, whyNot(e), false));
      }
    }
    for (int i = 0; i < slots.size(); i++) {
      Slot s = slots.get(i);
      ctx.sampler.channel("s" + i, s::sample);
      ctx.note("sensor " + i + ": " + s.name + " (" + s.how + ")" + (s.problem != null ? ": not read: " + s.problem : ""));
    }
    ctx.meta("count", slots.size());
    ctx.meta("duration_s", durationS);
    ctx.meta("rate_hz", RATE_HZ);
  }

  static String portsText(int[] ports) {
    StringBuilder b = new StringBuilder();
    for (int p : ports) {
      b.append(b.length() == 0 ? "" : ",").append(p);
    }
    return b.length() == 0 ? "(no port)" : b.toString();
  }

  /** In words: a port the code already uses, or what WPILib said. */
  static String whyNot(RuntimeException e) {
    String m = String.valueOf(e.getMessage());
    if (e.getClass().getSimpleName().contains("Allocation") || m.toLowerCase(Locale.ROOT).contains("allocated")) {
      return "the robot code already uses this port; register the sensor with watchSensor to see it here";
    }
    return m;
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    return stopRequested || t >= durationS;
  }

  /** "Sensors now: Intake beam = true (changed)", each sensor after a middle dot. */
  String liveLine() {
    StringBuilder b = new StringBuilder("Sensors now: ");
    for (int i = 0; i < slots.size(); i++) {
      Slot s = slots.get(i);
      b.append(i == 0 ? "" : " \u00b7 ").append(s.name).append(" = ").append(s.valueText())
          .append(s.changed() ? " (changed)" : "");
    }
    return b.toString();
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    return liveLine();
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    for (int i = 0; i < slots.size(); i++) {
      Slot s = slots.get(i);
      ctx.meta("s" + i + ".changes", s.changes);
      ctx.meta("s" + i + ".changed", s.changed() ? 1 : 0);
      if (!Double.isNaN(s.min)) {
        ctx.meta("s" + i + ".min", s.min);
        ctx.meta("s" + i + ".max", s.max);
      }
      s.close();
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1.0, t / Math.max(0.1, durationS));
  }

  @Override
  public void requestStop() {
    stopRequested = true;
  }

  /** For tests. */
  List<Slot> slots() {
    return slots;
  }
}
