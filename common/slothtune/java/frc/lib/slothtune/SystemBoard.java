package frc.lib.slothtune;

import edu.wpi.first.networktables.DoubleArrayPublisher;
import edu.wpi.first.networktables.DoubleEntry;
import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.IntegerSubscriber;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import edu.wpi.first.networktables.StringPublisher;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The registered systems on NetworkTables: what each is, its live position, speed and goal, its
 * limits, and its live gains. A gain change follows LiveGains' rules: applied together when the
 * laptop bumps the sequence, out-of-range values refused, never during a match or a test, and
 * the echo always shows what is really running.
 */
final class SystemBoard {
  private final NetworkTableInstance nt;
  private final long bootId;
  private final List<TunableSystem> systems;
  private int publishedCount = -1;
  private final StringArrayPublisher names;
  private final StringArrayPublisher kinds;
  private final StringArrayPublisher units;
  private final StringArrayPublisher motors;
  private final StringArrayPublisher gainNames;
  private final StringArrayPublisher limitsFrom;
  private final StringArrayPublisher control;
  private int loops;
  private final DoubleArrayPublisher position;
  private final DoubleArrayPublisher velocity;
  private final DoubleArrayPublisher goal;
  private final DoubleArrayPublisher limits;
  private final Map<String, DoubleEntry> requested = new LinkedHashMap<>();
  private final Map<String, DoublePublisher> applied = new LinkedHashMap<>();
  private final IntegerSubscriber applySeq;
  private final IntegerSubscriber applyBoot;
  private final IntegerPublisher appliedSeq;
  private final StringPublisher status;
  private long lastSeq;

  SystemBoard(NetworkTableInstance nt, long bootId, List<TunableSystem> systems) {
    this.nt = nt;
    this.bootId = bootId;
    this.systems = systems;
    names = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_NAMES).publish();
    kinds = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_KINDS).publish();
    units = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_UNITS).publish();
    motors = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_MOTORS).publish();
    gainNames = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_GAIN_NAMES).publish();
    limitsFrom = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_LIMITS_FROM).publish();
    control = nt.getStringArrayTopic(SlothTuneTopics.SYSTEMS_CONTROL).publish();
    position = nt.getDoubleArrayTopic(SlothTuneTopics.SYSTEMS_POSITION).publish();
    velocity = nt.getDoubleArrayTopic(SlothTuneTopics.SYSTEMS_VELOCITY).publish();
    goal = nt.getDoubleArrayTopic(SlothTuneTopics.SYSTEMS_GOAL).publish();
    limits = nt.getDoubleArrayTopic(SlothTuneTopics.SYSTEMS_LIMITS).publish();
    applySeq = nt.getIntegerTopic(SlothTuneTopics.SYSTEMS_APPLY_SEQ).subscribe(0);
    applyBoot = nt.getIntegerTopic(SlothTuneTopics.SYSTEMS_APPLY_BOOT_ID).subscribe(0);
    appliedSeq = nt.getIntegerTopic(SlothTuneTopics.SYSTEMS_APPLIED_SEQ).publish();
    status = nt.getStringTopic(SlothTuneTopics.SYSTEMS_APPLY_STATUS).publish();
    lastSeq = applySeq.get();
    appliedSeq.set(lastSeq);
    status.set("");
  }

  private static String key(TunableSystem s, String gain) {
    return s.name + "/" + gain;
  }

  /** What each system is, published again whenever one is registered. */
  private void describe() {
    int n = systems.size();
    String[] nm = new String[n];
    String[] kd = new String[n];
    String[] un = new String[n];
    String[] mo = new String[n];
    List<String> gn = new ArrayList<>();
    for (int i = 0; i < n; i++) {
      TunableSystem s = systems.get(i);
      nm[i] = s.name;
      kd[i] = s.kind.name();
      un[i] = s.units;
      mo[i] = String.join(",", s.motors);
      for (TunableSystem.Gain g : s.gains.values()) {
        String k = key(s, g.name());
        gn.add(k + "|" + g.min() + "|" + g.max());
        if (!requested.containsKey(k)) {
          double v = read(g);
          DoubleEntry e = nt.getDoubleTopic(SlothTuneTopics.SYSTEMS_GAINS + k).getEntry(v);
          e.set(v);
          requested.put(k, e);
          DoublePublisher p = nt.getDoubleTopic(SlothTuneTopics.SYSTEMS_GAINS_APPLIED + k).publish();
          p.set(v);
          applied.put(k, p);
        }
      }
    }
    names.set(nm);
    kinds.set(kd);
    units.set(un);
    motors.set(mo);
    gainNames.set(gn.toArray(new String[0]));
    publishedCount = n;
  }

  private static double read(TunableSystem.Gain g) {
    try {
      return g.get().getAsDouble();
    } catch (RuntimeException e) {
      return Double.NaN;
    }
  }

  /** Every robot loop: the live state, and any gain change the laptop asked for. */
  void periodic(String gainsBlocked) {
    if (publishedCount != systems.size()) {
      describe();
    }
    int n = systems.size();
    double[] pos = new double[n];
    double[] vel = new double[n];
    double[] gl = new double[n];
    double[] lim = new double[4 * n];
    String[] from = new String[n];
    for (int i = 0; i < n; i++) {
      TunableSystem s = systems.get(i);
      pos[i] = safe(s.position::getAsDouble);
      vel[i] = safe(s.velocity::getAsDouble);
      gl[i] = s.lastGoal;
      lim[4 * i] = s.min;
      lim[4 * i + 1] = s.max;
      lim[4 * i + 2] = s.maxVelocity;
      lim[4 * i + 3] = s.maxAccel;
      from[i] = s.limitsFrom;
    }
    position.set(pos);
    velocity.set(vel);
    goal.set(gl);
    limits.set(lim);
    limitsFrom.set(from);
    if (loops++ % 25 == 0) {
      // Twice a second: the mode each SPARK's code runs it in. Not while a test runs it by voltage
      // (gains are blocked then), which would hide the code's own mode.
      String[] ctl = new String[n];
      for (int i = 0; i < n; i++) {
        TunableSystem s = systems.get(i);
        if (gainsBlocked == null) {
          s.noteControl();
        }
        ctl[i] = s.control;
      }
      control.set(ctl);
    }
    long seq = applySeq.get();
    if (seq != lastSeq) {
      lastSeq = seq;
      if (applyBoot.get() != bootId) {
        status.set("Refused: those gain values are from before the robot code restarted.");
      } else if (gainsBlocked != null) {
        status.set("Refused: " + gainsBlocked + ".");
      } else {
        status.set(apply());
      }
      sync();
      appliedSeq.set(seq);
    }
  }

  private static double safe(java.util.function.DoubleSupplier s) {
    try {
      return s.getAsDouble();
    } catch (RuntimeException e) {
      return Double.NaN;
    }
  }

  /** Every gain whose requested value differs, within its range; the sentence for a person. */
  String apply() {
    List<String> done = new ArrayList<>();
    List<String> refused = new ArrayList<>();
    for (TunableSystem s : systems) {
      for (TunableSystem.Gain g : s.gains.values()) {
        String k = key(s, g.name());
        DoubleEntry e = requested.get(k);
        if (e == null) {
          continue;
        }
        double want = e.get();
        double now = read(g);
        if (Double.compare(want, now) == 0) {
          continue;
        }
        if (!Double.isFinite(want) || want < g.min() || want > g.max()) {
          refused.add(String.format("%s=%s is outside [%s, %s]", k, want, g.min(), g.max()));
          continue;
        }
        try {
          g.set().accept(want);
          done.add(String.format("%s %s -> %s", k, now, want));
        } catch (RuntimeException ex) {
          refused.add(k + ": " + ex.getMessage());
        }
      }
    }
    String msg = done.isEmpty() ? "Nothing changed." : "Applied: " + String.join("; ", done) + ".";
    if (!refused.isEmpty()) {
      msg += " REFUSED: " + String.join("; ", refused) + ".";
    }
    return msg + " Live only: put a value to keep into the code.";
  }

  /** What is really running, on the request and the echo alike. */
  private void sync() {
    for (TunableSystem s : systems) {
      for (TunableSystem.Gain g : s.gains.values()) {
        String k = key(s, g.name());
        double v = read(g);
        if (requested.containsKey(k)) {
          requested.get(k).set(v);
          applied.get(k).set(v);
        }
      }
    }
  }
}
