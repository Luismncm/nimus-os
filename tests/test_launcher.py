import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import launch_windows as launcher


class LauncherTest(unittest.TestCase):
    def test_only_reuses_the_same_project(self):
        app = launcher.ROOT / 'app.py'
        instances = [{'port': 8502, 'command': f'python -m streamlit run "{app}" --server.port 8502'},
                     {'port': 8503, 'command': 'python -m streamlit run C:\\another_project\\app.py'}]
        self.assertEqual(launcher.existing_port(app, instances), 8502)
        self.assertIsNone(launcher.existing_port(Path('C:/different/app.py'), instances))

    def test_unrelated_occupied_port_uses_next_free_port(self):
        with patch.object(launcher, 'port_is_free', side_effect=lambda port: port == 8504):
            self.assertEqual(launcher.available_port(), 8504)
        with patch.object(launcher, 'port_is_free', return_value=False):
            with self.assertRaises(RuntimeError):
                launcher.available_port()

    def test_running_instance_opens_without_starting_duplicate(self):
        app = launcher.ROOT / 'app.py'
        with patch('sys.argv', ['launch_windows.py']), \
             patch.object(launcher, 'listening_instances', return_value=[{'port': 8502, 'command': f'python -m streamlit run "{app}"'}]), \
             patch.object(launcher, 'wait_ready', return_value=True), \
             patch.object(launcher.webbrowser, 'open') as browser, \
             patch.object(launcher.subprocess, 'Popen') as start:
            self.assertEqual(launcher.main(), 0)
            browser.assert_called_once_with('http://127.0.0.1:8502/')
            start.assert_not_called()

    def test_unresponsive_existing_instance_does_not_start_another(self):
        with patch('sys.argv', ['launch_windows.py']), \
             patch.object(launcher, 'listening_instances', return_value=[{'port': 8502, 'command': f'python -m streamlit run "{launcher.ROOT / "app.py"}"'}]), \
             patch.object(launcher, 'wait_ready', return_value=False), \
             patch.object(launcher.webbrowser, 'open') as browser, \
             patch.object(launcher.subprocess, 'Popen') as start:
            self.assertEqual(launcher.main(), 1)
            browser.assert_not_called()
            start.assert_not_called()
