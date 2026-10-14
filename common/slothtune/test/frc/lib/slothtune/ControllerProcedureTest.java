package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ControllerProcedureTest {
  @Test
  void theLiveLineNamesEveryButtonHeldAndTheDpad() {
    assertEquals("Pressed now: nothing", ControllerProcedure.pressedNow(0, -1));
    assertEquals("Pressed now: A, Right bumper", ControllerProcedure.pressedNow(0b100001, -1));
    assertEquals("Pressed now: D-pad up", ControllerProcedure.pressedNow(0, 0));
    assertEquals("Pressed now: D-pad up, D-pad right", ControllerProcedure.pressedNow(0, 45));
    assertEquals("Pressed now: Back, D-pad left", ControllerProcedure.pressedNow(1 << 6, 270));
  }
}
