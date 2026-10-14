package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** A mechanism's gains saved in slothtune.json: read, applied as the code declares each, and said. */
class SystemGainsTest {

  @Test
  void savedGainsAreReadPerSystem() {
    SlothTuneConfig c = SlothTuneConfig.parse("""
        {"systems": {"Elevator": {"min": 0, "max": 1.2, "gains": {"kP": 6.5, "kG": 0.45, "kD": "x"}},
                     "Shooter": {"maxVelocity": 600}}}""");
    assertEquals(Map.of("kP", 6.5, "kG", 0.45), c.systemGains.get("Elevator"), "a value that isn't a number is left out");
    assertTrue(!c.systemGains.containsKey("Shooter"));
  }

  @Test
  void aSavedGainIsSetAsTheCodeDeclaresItAndSaid() {
    double[] kP = {2.0};
    double[] kG = {0.0};
    List<String> said = new ArrayList<>();
    TunableSystem s = new TunableSystem("Elevator", TunableSystem.Kind.ELEVATOR);
    s.saved = Map.of("kP", 6.5, "kG", 20.0);
    s.report = said::add;
    s.gain("kP", () -> kP[0], v -> kP[0] = v, 0, 100).gain("kG", () -> kG[0], v -> kG[0] = v, -12, 12)
        .gain("kD", () -> 0, v -> { }, 0, 10);
    assertEquals(6.5, kP[0]);
    assertEquals(0.0, kG[0], "outside its range: not applied");
    assertEquals(List.of("Elevator: kP 6.5 from slothtune.json",
        "Elevator: kG 20 in slothtune.json is outside -12 to 12, so not applied"), said);
  }

  @Test
  void withNothingSavedTheCodesOwnGainsStand() {
    double[] kP = {2.0};
    TunableSystem s = new TunableSystem("Arm", TunableSystem.Kind.PIVOT);
    s.gain("kP", () -> kP[0], v -> kP[0] = v, 0, 100);
    assertEquals(2.0, kP[0]);
  }
}
