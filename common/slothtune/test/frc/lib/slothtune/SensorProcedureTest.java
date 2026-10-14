package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** Bring-up's live sensor readout: what it reads, what counts as a change, and what it gives back. */
class SensorProcedureTest {
  /** Ports a test sets by hand; port 3 is the robot code's, so it can't be opened. */
  static final class FakePorts implements Sensors.Opener {
    final Map<Integer, double[]> value = new HashMap<>();
    final List<Integer> closed = new ArrayList<>();

    @Override
    public Sensors.Reader open(String type, int[] ports) {
      int p = ports[0];
      if (p == 3) {
        throw new IllegalStateException("Code: -1029. HAL: Resource already allocated");
      }
      double[] v = value.computeIfAbsent(p, k -> new double[1]);
      return new Sensors.Reader() {
        @Override
        public double read() {
          return v[0];
        }

        @Override
        public void close() {
          closed.add(p);
        }
      };
    }
  }

  final FakePorts ports = new FakePorts();
  final boolean[] beam = {true};

  TestContext ctx() {
    TestContext c = new TestContext(new FakeDrivetrain(), TestArgs.of(new String[] {"duration_s"}, new double[] {10}),
        TestEnvironment.UNSET, new int[] {0, 1, 2, 3}, 1.0, 1.0, 1.0, false, Sampler.create(2000), false, () -> false,
        () -> null);
    c.sensors = List.of(new Sensors.Registered("Intake beam", true, () -> beam[0] ? 1 : 0));
    c.designedSensors = List.of(
        new Sensors.Designed("Intake beam", "digital", new int[] {0}),   // the code reads it: not opened
        new Sensors.Designed("Arm absolute", "dutycycle", new int[] {1}),
        new Sensors.Designed("Climber bottom", "digital", new int[] {3}));
    c.sensorPorts = ports;
    return c;
  }

  @Test
  void itMovesNothingAndRunsDisabledAnywhere() {
    SensorProcedure p = new SensorProcedure();
    assertFalse(p.spinsWheels());
    assertFalse(p.needsEnabled());
    assertTrue(p.allowedIn(TestEnvironment.UNSET) && p.allowedIn(TestEnvironment.FIELD));
  }

  @Test
  void itRefusesWhenThereIsNothingToRead() {
    SensorProcedure p = new SensorProcedure();
    TestContext c = ctx();
    assertNull(p.validate(c));
    c.sensors = List.of();
    c.designedSensors = List.of();
    assertNotNull(p.validate(c));
  }

  @Test
  void eachSensorLiveWithWhetherItChanged() {
    SensorProcedure p = new SensorProcedure();
    TestContext c = ctx();
    p.start(c);
    c.sampler.start(() -> 0);
    assertEquals(3, p.slots().size(), "the code's beam once, the encoder, the switch on a taken port");
    assertFalse(ports.value.containsKey(0), "a port the code reads is never opened a second time");
    ports.value.get(1)[0] = 0.98;
    c.sampler.sampleNow();
    String line = p.liveMessage(c, 0.02);
    assertTrue(line.startsWith("Sensors now: Intake beam = true \u00b7 Arm absolute = 0.980 turns"), line);
    assertTrue(line.contains("Climber bottom = can't read"), line);
    // The beam blocked and cleared; the encoder turned across its zero, 0.98 to 0.03: 0.05 of a turn.
    beam[0] = false;
    ports.value.get(1)[0] = 0.03;
    c.sampler.sampleNow();
    beam[0] = true;
    c.sampler.sampleNow();
    line = p.liveMessage(c, 0.06);
    assertTrue(line.contains("Intake beam = true (changed)"), line);
    assertTrue(line.contains("Arm absolute = 0.030 turns (changed)"), "0.05 of a turn, not 0.95: " + line);
    assertFalse(p.execute(c, 1.0));
    p.requestStop();
    assertTrue(p.execute(c, 1.1), "the laptop's Stop ends it");
    p.end(c, false);
    assertEquals(List.of(1), ports.closed, "the port it opened is closed again");
    assertEquals(2.0, c.meta().get("s0.changes"), "blocked, then clear");
    assertEquals(1.0, c.meta().get("s1.changed"));
    assertEquals(0.0, c.meta().get("s2.changed"));
    assertTrue(c.notes().get(0).startsWith("sensor 0: Intake beam (registered by the robot code"), c.notes().get(0));
    assertTrue(c.notes().get(2).contains("not read: the robot code already uses this port"), c.notes().get(2));
  }

  @Test
  void noiseIsNotAChange() {
    SensorProcedure p = new SensorProcedure();
    TestContext c = ctx();
    c.designedSensors = List.of(new Sensors.Designed("Elevator height", "analog", new int[] {2}));
    c.sensors = List.of();
    p.start(c);
    c.sampler.start(() -> 0);
    for (double v : new double[] {2.50, 2.53, 2.48, 2.55}) {
      ports.value.get(2)[0] = v;
      c.sampler.sampleNow();
    }
    assertFalse(p.slots().get(0).changed(), "a few hundredths of a volt is noise");
    ports.value.get(2)[0] = 3.1;
    c.sampler.sampleNow();
    assertTrue(p.slots().get(0).changed());
  }

  @Test
  void theDesignFileIsReadForItsSensors() {
    List<Sensors.Designed> d = Sensors.parseDesign("{\"motors\": [], \"sensors\": ["
        + "{\"name\": \"Intake beam\", \"type\": \"Digital\", \"port\": 0},"
        + "{\"name\": \"Turret\", \"type\": \"encoder\", \"port\": [4, 5]},"
        + "{\"type\": \"analog\", \"port\": 1}]}");
    assertEquals(2, d.size(), "a sensor without a name is skipped");
    assertEquals("digital", d.get(0).type());
    assertEquals(5, d.get(1).ports()[1]);
  }
}
