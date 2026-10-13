"""An <svg> has no `hidden` property: only HTML elements reflect it. `svg.hidden = false` set a plain
JavaScript property and left the attribute, so the Live tab's drawing from above never showed. An
<svg> written hidden is shown and hidden through the attribute itself."""

import os
import re
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class SvgHiddenTest(unittest.TestCase):
    def test_a_hidden_svg_is_shown_through_its_attribute(self):
        checked = 0
        for name in sorted(os.listdir(WEB)):
            if not name.endswith(".js"):
                continue
            with open(os.path.join(WEB, name), encoding="utf-8") as fh:
                js = fh.read()
            for sid in re.findall(r'<svg id="([\w-]+)"[^>]*\bhidden\b', js):
                checked += 1
                names = re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*\$\("#' + re.escape(sid) + r'"', js)
                for var in names + [r'\$\("#' + re.escape(sid) + r'"[^)]*\)']:
                    self.assertIsNone(re.search(var + r"\.hidden\s*=", js),
                                      f"{name}: #{sid} is an <svg>; use toggleAttribute(\"hidden\", ...)")
        self.assertGreater(checked, 0, "the Live tab's drawing is one")

    def test_no_svg_variable_sets_the_hidden_property(self):
        for name in sorted(os.listdir(WEB)):
            if name.endswith(".js"):
                with open(os.path.join(WEB, name), encoding="utf-8") as fh:
                    self.assertNotRegex(fh.read(), r"\bsvg\.hidden\s*=", name)


if __name__ == "__main__":
    unittest.main()
