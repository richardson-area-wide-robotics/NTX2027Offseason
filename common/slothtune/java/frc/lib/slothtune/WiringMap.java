package frc.lib.slothtune;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The robot's wiring, as the laptop's Wiring tab saved it to {@code deploy/wiring.json}: which PDH
 * port feeds each motor, and the order devices sit along each CAN cable. Robot Health alerts use it
 * to say where to look: a power fault names the PDH port, a CAN fault the devices either side on the
 * cable. A chain whose order nobody has confirmed on the robot is the code's guess (sorted by CAN
 * ID), so its neighbors are never named.
 */
final class WiringMap {
  static final WiringMap NONE = new WiringMap(Map.of(), List.of());

  private final Map<String, Integer> pdhPorts;
  /** Confirmed chains only, each from the roboRIO end. */
  private final List<List<String>> chains;

  private WiringMap(Map<String, Integer> pdhPorts, List<List<String>> chains) {
    this.pdhPorts = pdhPorts;
    this.chains = chains;
  }

  /** The deployed map, or {@link #NONE} if there isn't one or it can't be read. */
  static WiringMap load(Path file) {
    try {
      return Files.exists(file) ? parse(Files.readString(file)) : NONE;
    } catch (IOException | RuntimeException e) {
      return NONE;
    }
  }

  @SuppressWarnings("unchecked")
  static WiringMap parse(String text) {
    Object root;
    try {
      root = MiniJson.parse(text);
    } catch (IllegalArgumentException e) {
      return NONE;  // a map that can't be read is no map: the alerts just don't say where
    }
    if (!(root instanceof Map)) {
      return NONE;
    }
    Map<String, Object> m = (Map<String, Object>) root;
    Map<String, Integer> ports = new HashMap<>();
    if (m.get("pdhPorts") instanceof Map<?, ?> p) {
      for (Map.Entry<?, ?> e : p.entrySet()) {
        if (e.getValue() instanceof Number n) {
          ports.put(String.valueOf(e.getKey()), n.intValue());
        }
      }
    }
    List<List<String>> chains = new ArrayList<>();
    if (m.get("buses") instanceof List<?> buses) {
      for (Object b : buses) {
        if (b instanceof Map<?, ?> bus && Boolean.TRUE.equals(bus.get("orderConfirmed"))
            && bus.get("chain") instanceof List<?> chain) {
          List<String> names = new ArrayList<>();
          chain.forEach(x -> names.add(String.valueOf(x)));
          chains.add(names);
        }
      }
    }
    return new WiringMap(ports, chains);
  }

  /** " (PDH port 7)", or "" if the port isn't mapped. */
  String power(String name) {
    Integer port = pdhPorts.get(name);
    return port == null ? "" : " (PDH port " + port + ")";
  }

  /** " (on the CAN cable between A and B)", or "" if the order isn't confirmed. */
  String can(String name) {
    for (List<String> chain : chains) {
      int i = chain.indexOf(name);
      if (i < 0) {
        continue;
      }
      String before = i > 0 ? chain.get(i - 1) : null;
      String after = i + 1 < chain.size() ? chain.get(i + 1) : null;
      if (before != null && after != null) {
        return " (on the CAN cable between " + before + " and " + after + ")";
      }
      return before != null ? " (on the CAN cable after " + before + ", at the far end)"
          : after != null ? " (first on the CAN cable, before " + after + ")" : "";
    }
    return "";
  }
}
