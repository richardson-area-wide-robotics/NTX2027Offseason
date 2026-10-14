package frc.lib.slothtune;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The roboRIO's image version, as GradleRIO reads it before a deploy: the {@code IMAGEVERSION} line
 * of {@code /etc/natinst/share/scs_imagemetadata.ini}, e.g. {@code FRC_roboRIO2_2026_v2.0}. The
 * laptop compares its year with the Driver Station's and the robot code's. Empty anywhere else (the
 * simulator; SystemCore keeps no such file).
 */
public final class RobotImage {
  static final Path FILE = Path.of("/etc/natinst/share/scs_imagemetadata.ini");
  private static final Pattern LINE = Pattern.compile("(?m)^\\s*IMAGEVERSION\\s*=\\s*\"([^\"]*)\"");

  private RobotImage() {}

  /** The image version, or "" when there is no roboRIO image file to read. */
  public static String version() {
    try {
      return Files.exists(FILE) ? parse(Files.readString(FILE, StandardCharsets.UTF_8)) : "";
    } catch (IOException | RuntimeException e) {
      return "";
    }
  }

  /** The {@code IMAGEVERSION} value in the file's text, or "". */
  static String parse(String ini) {
    Matcher m = LINE.matcher(ini == null ? "" : ini);
    return m.find() ? m.group(1) : "";
  }
}
