"""The page loads with no script error, every tab paints, and every lesson opens with its drawings.

A lesson's text is JavaScript: a stray name in it (a variable from the script that wrote it) throws
when the file loads, and every lesson, tip and tab that uses them breaks with it. The syntax check
can't see that; only loading the page can. Runs the tool's own server on a free port and opens it
in headless Chromium (skipped where Playwright isn't installed).
"""

import os
import socket
import subprocess
import sys
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - not every machine has it
    sync_playwright = None

TOOLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class PageSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        # The server with a scratch checklist file, so the test never touches the real one.
        code = ("import os, runpy, sys, tempfile\n"
                "from slothtune import progress\n"
                "progress.PATH = os.path.join(tempfile.mkdtemp(prefix='slothtune-smoke-'), 'guide_progress.json')\n"
                f"sys.argv = ['slothtune', 'gui', '--port', '{cls.port}', '--no-browser', '--project', 'Peashooter']\n"
                "runpy.run_module('slothtune', run_name='__main__')\n")
        cls.proc = subprocess.Popen([sys.executable, "-c", code], cwd=TOOLS, env=dict(os.environ, PYTHONPATH=TOOLS),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.time() + 30
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.2)
        cls.proc.kill()
        raise unittest.SkipTest("the tool's server didn't start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait(10)

    def test_the_page_tabs_and_lessons_load_clean(self):
        with sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as e:  # noqa: BLE001 - no browser downloaded
                self.skipTest(f"no Chromium for Playwright: {e}")
            pg = b.new_page(viewport={"width": 1536, "height": 740})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/")
            pg.wait_for_timeout(2000)
            self.assertEqual(errors, [], "the page threw while loading")
            self.assertEqual(pg.evaluate("typeof Learn"), "object")
            pg.evaluate("document.getElementById('modal') && App.closeModal()")
            for tab in pg.evaluate("[...document.querySelectorAll('.tabs button[data-tab]')].map(b => b.dataset.tab)"):
                pg.evaluate(f"App.show('{tab}')")
                pg.wait_for_timeout(150)
            self.assertEqual(errors, [], "a tab threw as it painted")
            # Every input box, drop-down and text area says what it is: a tip on it or around it.
            bare = pg.evaluate("""[...document.querySelectorAll('main input, main select, main textarea')]
              .filter(e => !['checkbox', 'radio', 'hidden', 'file', 'range'].includes((e.type || '').toLowerCase()))
              .filter(e => !e.closest('[data-tip], [data-learn]'))
              .map(e => (e.closest('.tab') || {}).id + ' ' + (e.id || e.name || e.getAttribute('data-ph') || e.getAttribute('data-g') || e.outerHTML.slice(0, 60)))""")
            self.assertEqual(bare, [], "input boxes with no tip")
            keys = pg.evaluate("Object.keys(Learn.L)")
            self.assertGreater(len(keys), 100)
            broken = []
            for k in keys:
                pg.evaluate(f"Learn.open({k!r})")
                srcs = pg.evaluate("[...document.querySelectorAll('.learn-drawer img')].map(i => i.getAttribute('src'))")
                if srcs:
                    pg.wait_for_function("[...document.querySelectorAll('.learn-drawer img')].every(i => i.complete)", timeout=10000)
                    broken += [f"{k}: {s}" for s in pg.evaluate(
                        "[...document.querySelectorAll('.learn-drawer img')].filter(i => !i.naturalWidth).map(i => i.getAttribute('src'))")]
            self.assertEqual(errors, [], "a lesson threw as it opened")
            self.assertEqual(broken, [], "lesson drawings that didn't load")
            b.close()


if __name__ == "__main__":
    unittest.main()
