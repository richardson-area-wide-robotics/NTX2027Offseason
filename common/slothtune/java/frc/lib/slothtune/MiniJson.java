package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A small, strict JSON reader for {@code slothtune.json}.
 *
 * <p>Hand-written rather than borrowed because the borrowable one moves under us: WPILib 2026
 * ships Jackson, WPILib 2027 replaces it with Avaje Jsonb. A config reader that depends on neither
 * keeps working across that change. It reads objects, arrays, strings, numbers, true, false and
 * null into {@link Map}, {@link List}, {@link String}, {@link Double}, {@link Boolean} and null.
 */
final class MiniJson {
  private final String s;
  private int i;

  private MiniJson(String s) {
    this.s = s;
  }

  static Object parse(String text) {
    MiniJson p = new MiniJson(text);
    p.ws();
    Object v = p.value();
    p.ws();
    if (p.i != p.s.length()) {
      throw p.error("trailing characters");
    }
    return v;
  }

  private IllegalArgumentException error(String what) {
    int line = 1;
    for (int k = 0; k < Math.min(i, s.length()); k++) {
      if (s.charAt(k) == '\n') {
        line++;
      }
    }
    return new IllegalArgumentException("JSON " + what + " at line " + line);
  }

  private void ws() {
    while (i < s.length() && Character.isWhitespace(s.charAt(i))) {
      i++;
    }
  }

  private Object value() {
    if (i >= s.length()) {
      throw error("unexpected end");
    }
    char c = s.charAt(i);
    return switch (c) {
      case '{' -> object();
      case '[' -> array();
      case '"' -> string();
      case 't' -> literal("true", Boolean.TRUE);
      case 'f' -> literal("false", Boolean.FALSE);
      case 'n' -> literal("null", null);
      default -> number();
    };
  }

  private Object literal(String word, Object v) {
    if (!s.startsWith(word, i)) {
      throw error("unexpected token");
    }
    i += word.length();
    return v;
  }

  private Map<String, Object> object() {
    Map<String, Object> m = new LinkedHashMap<>();
    i++;
    ws();
    if (peek('}')) {
      i++;
      return m;
    }
    while (true) {
      ws();
      if (!peek('"')) {
        throw error("expected a key");
      }
      String k = string();
      ws();
      expect(':');
      ws();
      m.put(k, value());
      ws();
      if (peek(',')) {
        i++;
        continue;
      }
      expect('}');
      return m;
    }
  }

  private List<Object> array() {
    List<Object> a = new ArrayList<>();
    i++;
    ws();
    if (peek(']')) {
      i++;
      return a;
    }
    while (true) {
      ws();
      a.add(value());
      ws();
      if (peek(',')) {
        i++;
        continue;
      }
      expect(']');
      return a;
    }
  }

  private String string() {
    expect('"');
    StringBuilder b = new StringBuilder();
    while (i < s.length()) {
      char c = s.charAt(i++);
      if (c == '"') {
        return b.toString();
      }
      if (c == '\\') {
        if (i >= s.length()) {
          break;
        }
        char e = s.charAt(i++);
        switch (e) {
          case 'n' -> b.append('\n');
          case 't' -> b.append('\t');
          case 'r' -> b.append('\r');
          case 'b' -> b.append('\b');
          case 'f' -> b.append('\f');
          case 'u' -> {
            if (i + 4 > s.length()) {
              throw error("bad escape");
            }
            b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
            i += 4;
          }
          default -> b.append(e);
        }
      } else {
        b.append(c);
      }
    }
    throw error("unterminated string");
  }

  private Double number() {
    int start = i;
    while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) {
      i++;
    }
    if (start == i) {
      throw error("unexpected character '" + s.charAt(i) + "'");
    }
    try {
      return Double.parseDouble(s.substring(start, i));
    } catch (NumberFormatException e) {
      throw error("bad number");
    }
  }

  private boolean peek(char c) {
    return i < s.length() && s.charAt(i) == c;
  }

  private void expect(char c) {
    if (!peek(c)) {
      throw error("expected '" + c + "'");
    }
    i++;
  }
}
