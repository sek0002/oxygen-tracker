"""Test the actual embedded unit generator without root or systemd."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class ServiceUnitTests(unittest.TestCase):
    def generate(self, app_dir):
        script = Path(__file__).with_name('install-service.sh').read_text()
        generator = script.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'oxygen-tracker.service'
            subprocess.run([sys.executable, '-', app_dir, 'oxygen', str(target)],
                           input=generator, text=True, check=True)
            return target.read_text().splitlines()

    def test_reported_opt_checkout(self):
        lines = self.generate('/opt/oxygen-tracker')
        self.assertIn('User=oxygen', lines)
        self.assertIn('WorkingDirectory=/opt/oxygen-tracker', lines)
        self.assertIn('ExecStart="/opt/oxygen-tracker/.venv/bin/python" "/opt/oxygen-tracker/server.py"', lines)
        self.assertNotIn('User="oxygen"', lines)

    def test_scalar_path_is_not_shell_quoted(self):
        lines = self.generate('/opt/oxygen tracker%test')
        self.assertIn('WorkingDirectory=/opt/oxygen tracker%%test', lines)
        self.assertIn('ExecStart="/opt/oxygen tracker%%test/.venv/bin/python" "/opt/oxygen tracker%%test/server.py"', lines)

if __name__ == '__main__':
    unittest.main()
