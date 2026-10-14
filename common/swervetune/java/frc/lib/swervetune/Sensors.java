package frc.lib.swervetune;

import edu.wpi.first.wpilibj.AnalogInput;
import edu.wpi.first.wpilibj.DigitalInput;
import edu.wpi.first.wpilibj.DutyCycleEncoder;
import edu.wpi.first.wpilibj.Encoder;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.DoubleSupplier;

/**
 * The sensors bring-up's live readout can see: those the robot code registers with
 * {@link SwerveTune#watchSensor}, and those in the deployed design file ({@code
 * deploy/design/devices.json}) that the code doesn't read yet, opened from their ports for the
 * readout only and closed after it.
 *
 * <p>A port the robot code already opened can't be opened twice (WPILib refuses), so such a sensor
 * is seen only once the code registers it.
 */
final class Sensors {
  private Sensors() {}

  /** One sensor read during the readout. Read from the sampler's thread. */
  interface Reader extends AutoCloseable {
    double read();

    @Override
    default void close() {}
  }

  /** Opens a designed sensor's ports. Throws when a port is taken, doesn't exist, or reads nothing. */
  interface Opener {
    Reader open(String type, int[] ports);
  }

  /** A sensor in the design file: its type ({@code digital}, {@code analog}, ...) and ports. */
  record Designed(String name, String type, int[] ports) {}

  /** A sensor the robot code registered: a switch reads 1 or 0, a number anything. */
  record Registered(String name, boolean isSwitch, DoubleSupplier read) {}

  /** The deployed design file's sensors; none if there is no file or it can't be read. */
  static List<Designed> loadDesign(Path file) {
    try {
      return Files.exists(file) ? parseDesign(Files.readString(file)) : List.of();
    } catch (IOException | RuntimeException e) {
      return List.of();
    }
  }

  static List<Designed> parseDesign(String text) {
    List<Designed> out = new ArrayList<>();
    if (!(MiniJson.parse(text) instanceof Map<?, ?> root) || !(root.get("sensors") instanceof List<?> list)) {
      return out;
    }
    for (Object o : list) {
      if (!(o instanceof Map<?, ?> s) || !(s.get("name") instanceof String name)) {
        continue;
      }
      String type = s.get("type") instanceof String t ? t.toLowerCase(java.util.Locale.ROOT) : "";
      List<Integer> ports = new ArrayList<>();
      Object p = s.get("port");
      for (Object q : p instanceof List<?> l ? l : java.util.Collections.singletonList(p)) {
        if (q instanceof Number n) {
          ports.add(n.intValue());
        }
      }
      out.add(new Designed(name, type, ports.stream().mapToInt(Integer::intValue).toArray()));
    }
    return out;
  }

  /**
   * Opens roboRIO ports with WPILib's own classes: a digital input reads 1 or 0 as {@code get()}
   * returns it, an analog input volts, a duty-cycle encoder its absolute position in turns, a
   * quadrature encoder counts. A PWM port drives something and has nothing to read.
   *
   * <p>2027: SystemCore's ports are opened differently; see docs/MIGRATION_2027.md.
   */
  static final class Wpilib implements Opener {
    @Override
    public Reader open(String type, int[] ports) {
      if (ports.length == 0) {
        throw new IllegalArgumentException("no port in the design file");
      }
      switch (type) {
        case "digital": {
          DigitalInput d = new DigitalInput(ports[0]);
          return reader(() -> d.get() ? 1 : 0, d::close);
        }
        case "analog": {
          AnalogInput a = new AnalogInput(ports[0]);
          return reader(a::getVoltage, a::close);
        }
        case "dutycycle": {
          DutyCycleEncoder e = new DutyCycleEncoder(ports[0]);
          return reader(e::get, e::close);
        }
        case "encoder": {
          if (ports.length < 2) {
            throw new IllegalArgumentException("a quadrature encoder needs two ports (A and B)");
          }
          Encoder e = new Encoder(ports[0], ports[1]);
          return reader(e::get, e::close);
        }
        default:
          throw new IllegalArgumentException("a " + type + " port drives something; there is nothing to read");
      }
    }

    private static Reader reader(DoubleSupplier read, Runnable close) {
      return new Reader() {
        @Override
        public double read() {
          return read.getAsDouble();
        }

        @Override
        public void close() {
          close.run();
        }
      };
    }
  }
}
