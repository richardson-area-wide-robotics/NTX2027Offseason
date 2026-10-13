package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringPublisher;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class BatteryPickerTest {
  private NetworkTableInstance nt;
  private StringPublisher dashboard;

  @BeforeEach
  void setUp() {
    nt = NetworkTableInstance.create();
    dashboard = nt.getStringTopic(SwerveTuneTopics.BATTERY_SELECTED).publish();
  }

  @AfterEach
  void tearDown() {
    nt.close();
  }

  private String str(String topic) {
    return nt.getStringTopic(topic).subscribe("?").get();
  }

  private double num(String topic) {
    return nt.getDoubleTopic(topic).subscribe(-1).get();
  }

  @Test
  void startsEmptyAndOffersOneToTwelveByDefault() {
    BatteryPicker p = new BatteryPicker(nt, List.of());
    assertEquals("", p.update(0, 0, 12.7, true));
    assertEquals("String Chooser", str(SwerveTuneTopics.BATTERY_CHOOSER + ".type"));
    String[] options = nt.getStringArrayTopic(SwerveTuneTopics.BATTERY_OPTIONS).subscribe(new String[0]).get();
    assertEquals(13, options.length, "1 to 12, then Borrowed");
    assertEquals("1", options[0]);
    assertEquals("Borrowed", options[12]);
    assertEquals("", str(SwerveTuneTopics.BATTERY_ID));
  }

  @Test
  void aPickIsTakenWithItsRestingVoltage() {
    BatteryPicker p = new BatteryPicker(nt, List.of("2024-1", "2025-3"));
    p.update(0, 1, 12.8, true);
    dashboard.set("2025-3");
    assertEquals("2025-3", p.update(10, 1, 12.81, true));
    assertEquals("2025-3", str(SwerveTuneTopics.BATTERY_ID));
    assertEquals("2025-3", str(SwerveTuneTopics.BATTERY_ACTIVE));
    assertEquals(12.81, num(SwerveTuneTopics.BATTERY_REST_VOLTS), 1e-9);
    assertEquals("Battery 2025-3: 12.81 V at rest, charged", str(SwerveTuneTopics.BATTERY_CHECK));
  }

  @Test
  void theCheckLineSaysWhatToDo() {
    assertEquals("Pick the battery number", BatteryPicker.checkText("", Double.NaN));
    assertEquals("Battery 4: 12.45 V at rest, partly charged", BatteryPicker.checkText("4", 12.45));
    assertEquals("Battery 4: 12.10 V at rest, CHARGE IT before a match", BatteryPicker.checkText("4", 12.1));
    assertTrue(BatteryPicker.checkText("4", Double.NaN).contains("read once the robot is disabled"));
  }

  @Test
  void aPickMadeWhileDrivingIsReadOnceTheRobotRests() {
    BatteryPicker p = new BatteryPicker(nt, List.of());
    p.update(0, 1, 11.2, false);
    dashboard.set("4");
    p.update(10, 1, 11.2, false);
    p.update(11, 1, 12.4, true);
    assertTrue(Double.isNaN(num(SwerveTuneTopics.BATTERY_REST_VOLTS)), "just disabled: still recovering");
    p.update(13.5, 1, 12.62, true);
    assertEquals(12.62, num(SwerveTuneTopics.BATTERY_REST_VOLTS), 1e-9, "no second pick needed");
    assertEquals("Battery 4: 12.62 V at rest, partly charged", str(SwerveTuneTopics.BATTERY_CHECK));
    p.update(30, 1, 12.75, true);
    assertEquals(12.62, num(SwerveTuneTopics.BATTERY_REST_VOLTS), 1e-9, "read once per pick");
  }

  @Test
  void aNewConnectionAfterThePickNeverBlanksIt() {
    BatteryPicker p = new BatteryPicker(nt, List.of(), true);
    p.update(0, 1, 12.7, true);
    dashboard.set("5");
    assertEquals("5", p.update(5, 1, 12.7, true));
    // A laptop command connects (every CLI command is one), and the student re-picks right then.
    p.update(6, 2, 12.7, true);
    dashboard.set("8");
    assertEquals("8", p.update(6.5, 2, 12.7, true), "the restore window is only for the first pick");
    assertEquals("8", str(SwerveTuneTopics.BATTERY_SELECTED));
  }

  @Test
  void aPickMadeWhileDrivingHasNoRestingVoltage() {
    BatteryPicker p = new BatteryPicker(nt, List.of());
    p.update(0, 1, 11.2, false);
    dashboard.set("4");
    p.update(10, 1, 11.2, false);
    assertTrue(Double.isNaN(num(SwerveTuneTopics.BATTERY_REST_VOLTS)), "11.2 V under load is not a rest voltage");
  }

  @Test
  void aDashboardPuttingBackItsOldPickAfterARebootIsAskedAgain() {
    BatteryPicker p = new BatteryPicker(nt, List.of());
    p.update(0, 0, 12.7, true);
    // The dashboard reconnects to the rebooted robot and sends what it had: the old battery.
    dashboard.set("7");
    assertEquals("", p.update(0.5, 1, 12.7, true), "not taken: it may be the battery from before the swap");
    assertEquals("", str(SwerveTuneTopics.BATTERY_SELECTED), "cleared, so the drop-down shows nothing picked");
    // The drive team picks, even the same number.
    dashboard.set("7");
    assertEquals("7", p.update(6, 1, 12.7, true));
  }

  @Test
  void aDashboardAlreadyConnectedAtTheFirstLoopIsAskedAgainAfterAPowerOn() {
    // The usual order: the NT server starts first, Elastic reconnects while the robot code is still
    // building the drivetrain, and its old pick is waiting at the first loop.
    BatteryPicker p = new BatteryPicker(nt, List.of(), true);
    dashboard.set("7");
    assertEquals("", p.update(0.2, 1, 12.7, true), "maybe the battery from before the swap");
    assertEquals("", str(SwerveTuneTopics.BATTERY_SELECTED));
  }

  @Test
  void aCodeRestartKeepsThePickTheDashboardPutsBack() {
    BatteryPicker p = new BatteryPicker(nt, List.of(), false);
    dashboard.set("7");
    assertEquals("7", p.update(0.2, 1, 12.7, true), "the roboRIO stayed on, so the battery did too");
  }

  @Test
  void theRosterComesFromTheConfigWithoutDuplicates() {
    SwerveTuneConfig c = SwerveTuneConfig.parse("{\"batteries\": [1, \"2024-3\", 1, \" \", 2.0]}");
    assertEquals(List.of("1", "2024-3", "2"), c.batteries);
    BatteryPicker p = new BatteryPicker(nt, c.batteries);
    assertArrayEquals(new String[] {"1", "2024-3", "2", "Borrowed"},
        nt.getStringArrayTopic(SwerveTuneTopics.BATTERY_OPTIONS).subscribe(new String[0]).get(),
        "the team's list, then Borrowed for a battery without a team number");
    assertEquals(c.batteries, p.roster());
  }
}
