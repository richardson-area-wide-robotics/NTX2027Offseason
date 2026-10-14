package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

/** The CAN load test: quiet, loaded, quiet again, and the status frames always put back. */
class CanLoadProcedureTest {
  /** A bus whose status the test sets: {utilization, busOff, txFull, rxErrors, txErrors}. */
  static final class Bus implements RobotSignals {
    double[] status = {0.3, 0, 0, 0, 0};

    @Override public boolean enabled() { return false; }
    @Override public boolean autonomous() { return false; }
    @Override public boolean testMode() { return false; }
    @Override public boolean eStopped() { return false; }
    @Override public boolean fmsAttached() { return false; }
    @Override public double driverStickMax() { return 0; }
    @Override public boolean controllerDeadman() { return false; }
    @Override public double[] canStatus() { return status.clone(); }
  }

  final FakeDrivetrain io = new FakeDrivetrain();
  final Bus bus = new Bus();

  TestContext ctx() {
    TestContext c = new TestContext(io, TestArgs.of(new String[] {}, new double[] {}), TestEnvironment.UNSET,
        new int[] {0, 1, 2, 3}, 1.0, 1.0, 1.0, false, Sampler.create(2000), false, () -> false, () -> null);
    c.signals = bus;
    return c;
  }

  @Test
  void itMovesNothingAndNeedsTheBusStatus() {
    CanLoadProcedure p = new CanLoadProcedure();
    assertFalse(p.spinsWheels());
    assertFalse(p.needsEnabled());
    assertNull(p.validate(ctx()));
    TestContext c = ctx();
    c.signals = null;
    assertNotNull(p.validate(c));
  }

  @Test
  void quietThenLoadedThenQuietAndTheFramesPutBack() {
    CanLoadProcedure p = new CanLoadProcedure();
    TestContext c = ctx();
    p.start(c);
    c.sampler.start(() -> 0);
    double t = 0;
    for (; t < CanLoadProcedure.QUIET_S; t += 0.02) {
      assertFalse(p.execute(c, t));
    }
    assertTrue(p.liveMessage(c, t).startsWith("Quiet: 30% busy, no errors now"), p.liveMessage(c, t));
    p.execute(c, t);
    assertEquals(List.of(true), io.fastTelemetry, "loaded: the status frames sped up");
    bus.status = new double[] {0.72, 0, 0, 3, 0};
    assertTrue(p.liveMessage(c, t).startsWith("Loaded: 72% busy, errors now (3 receive"), p.liveMessage(c, t));
    boolean done = false;
    for (t += 0.02; !done && t < 20; t += 0.02) {
      done = p.execute(c, t);
    }
    assertTrue(done);
    assertEquals(List.of(true, false), io.fastTelemetry, "and put back before the end");
    p.end(c, false);
    assertEquals(List.of(true, false), io.fastTelemetry, "not twice");
    assertEquals(1.0, c.meta().get("fast_ok"));
  }

  @Test
  void anAbortStillPutsTheFramesBack() {
    CanLoadProcedure p = new CanLoadProcedure();
    TestContext c = ctx();
    p.start(c);
    p.execute(c, CanLoadProcedure.QUIET_S + 0.1);
    p.end(c, true);
    assertEquals(List.of(true, false), io.fastTelemetry);
  }
}
