package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.wpilibj.RuntimeType;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AkLoggingTest {

  @Test
  void aUsbStickWinsThenARoboRio2sSdCardAndARoboRio1KeepsNoLog() {
    assertEquals(AkLogging.USB_LOGS, AkLogging.chooseFolder(true, RuntimeType.kRoboRIO));
    assertEquals(AkLogging.USB_LOGS, AkLogging.chooseFolder(true, RuntimeType.kRoboRIO2));
    assertEquals(AkLogging.SD_LOGS, AkLogging.chooseFolder(false, RuntimeType.kRoboRIO2));
    assertNull(AkLogging.chooseFolder(false, RuntimeType.kRoboRIO), "a roboRIO 1 has no SD card");
  }

  private static File log(Path dir, String name, int bytes, long modified) throws IOException {
    File f = dir.resolve(name).toFile();
    Files.write(f.toPath(), new byte[bytes]);
    assertTrue(f.setLastModified(modified));
    return f;
  }

  @Test
  void theOldestLogsGoFirstAndTheNewestTenAlwaysStay(@TempDir Path dir) throws IOException {
    for (int i = 0; i < 14; i++) {
      log(dir, "akit_" + i + ".wpilog", 100, 1_000_000L * (i + 1));
    }
    File notALog = log(dir, "notes.txt", 100, 1_000L);
    List<File> gone = AkLogging.pruneOldLogs(dir.toFile(), 1000, 10, 850);
    assertEquals(List.of("akit_0.wpilog", "akit_1.wpilog"), gone.stream().map(File::getName).toList(),
        "deletes oldest first, and only until enough is free");
    assertTrue(notALog.exists(), "only .wpilog files are touched");

    gone = AkLogging.pruneOldLogs(dir.toFile(), 1_000_000, 10, 0);
    assertEquals(2, gone.size(), "never below the newest ten, even when still short of space");
    assertEquals(10, dir.toFile().listFiles((d, n) -> n.endsWith(".wpilog")).length);
    assertTrue(dir.resolve("akit_13.wpilog").toFile().exists());
  }

  @Test
  void nothingIsDeletedWhenThereIsRoom(@TempDir Path dir) throws IOException {
    for (int i = 0; i < 14; i++) {
      log(dir, "akit_" + i + ".wpilog", 100, 1_000_000L * (i + 1));
    }
    assertEquals(List.of(), AkLogging.pruneOldLogs(dir.toFile(), 1000, 10, 1000));
  }
}
