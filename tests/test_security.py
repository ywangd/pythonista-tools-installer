import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from unittest import mock
from contextlib import redirect_stderr
from urllib import parse

requests = types.ModuleType('requests')
requests.RequestException = Exception
sys.modules['requests'] = requests
six = types.ModuleType('six')
six.string_types = (str,)
moves = types.ModuleType('six.moves')
moves.urllib = types.ModuleType('six.moves.urllib')
moves.urllib.parse = parse
sys.modules['six'] = six
sys.modules['six.moves'] = moves
sys.modules['six.moves.urllib'] = moves.urllib
sys.modules['six.moves.urllib.parse'] = parse


ui = types.ModuleType('ui')
ui.in_background = lambda fn: fn
sys.modules['ui'] = ui
console = types.ModuleType('console')
console.hud_alert = lambda *args: None
sys.modules['console'] = console

import ptinstaller as p


def archive(members):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as zf:
        for name, content in members:
            zf.writestr(name, content)
    return out.getvalue()


class Button(object):
    category_name = 'Utilities'
    tool_name = 'Test Tool'
    tool_url = 'https://github.com/example/tool'

    def __init__(self):
        self.state = None

    def set_state_install(self):
        self.state = 'install'

    def set_state_uninstall(self):
        self.state = 'uninstall'


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.mkdir(os.path.join(self.tmp, 'Documents'))
        self.home = mock.patch.dict(os.environ, {'HOME': self.tmp})
        self.home.start()
        self.conf = mock.patch.object(p, 'CONF_FILE', os.path.join(self.tmp, 'missing.conf'))
        self.conf.start()
        self.app = p.PythonistaToolsInstaller.__new__(p.PythonistaToolsInstaller)
        self.app.activity_indicator = types.SimpleNamespace(start=lambda: None, stop=lambda: None)
        self.app.github_installer = p.GitHubRepoInstaller()
        self.app.gist_installer = p.GistInstaller()

    def tearDown(self):
        self.conf.stop()
        self.home.stop()
        shutil.rmtree(self.tmp)

    def test_catalog_names_cannot_escape(self):
        for value in ('../outside', '/outside', 'a/b', 'a\\b', '..'):
            with self.assertRaises(ValueError):
                p.PythonistaToolsInstaller.get_target_folder('Utilities', value)

    def test_strict_source_urls(self):
        self.assertIsNone(p.github_parts('http://github.com/example/tool'))
        self.assertIsNone(p.github_parts('https://github.com/example/tool/tree/main'))
        self.assertIsNone(p.github_parts('https://github.com.evil.test/example/tool'))
        self.assertIsNone(p.gist_id_from_url('http://gist.github.com/a/deadbeef'))

    def test_archive_traversal_rejected(self):
        data = archive([('tool-root/../escaped.txt', 'bad')])
        with mock.patch.object(p.GitHubRepoInstaller, 'download', return_value=(data, 'a' * 40)):
            with self.assertRaises(ValueError):
                self.app.github_installer.install(Button.tool_url, self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'escaped.txt')))

    def test_archive_symlink_rejected(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as zf:
            info = zipfile.ZipInfo('tool-root/link')
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, '../outside')
        with mock.patch.object(p.GitHubRepoInstaller, 'download',
                               return_value=(out.getvalue(), 'a' * 40)):
            with self.assertRaises(ValueError):
                self.app.github_installer.install(Button.tool_url, self.tmp)

    def test_archive_installs_regular_files(self):
        data = archive([('tool-root/src/main.py', 'print(1)')])
        with mock.patch.object(p.GitHubRepoInstaller, 'download', return_value=(data, 'a' * 40)):
            receipt = self.app.github_installer.install(Button.tool_url, self.tmp)
        self.assertEqual(receipt['revision'], 'a' * 40)
        with open(os.path.join(self.tmp, 'src', 'main.py')) as fp:
            self.assertEqual(fp.read(), 'print(1)')

    def test_failed_install_preserves_existing_directory(self):
        target = p.PythonistaToolsInstaller.get_target_folder('Utilities', 'Test Tool')
        os.makedirs(target)
        original = os.path.join(target, 'my-work.txt')
        with open(original, 'w') as fp:
            fp.write('keep')
        btn = Button()
        with redirect_stderr(io.StringIO()):
            self.app._install(btn)
        with open(original) as fp:
            self.assertEqual(fp.read(), 'keep')
        self.assertEqual(btn.state, 'install')

    def test_failed_staging_preserves_unrelated_files(self):
        category = os.path.join(self.tmp, 'Documents', 'bin', 'Utilities')
        os.makedirs(category)
        unrelated = os.path.join(category, 'unrelated.txt')
        with open(unrelated, 'w') as fp:
            fp.write('keep')
        with mock.patch.object(p.GitHubRepoInstaller, 'install', side_effect=ValueError('bad ZIP')):
            with redirect_stderr(io.StringIO()):
                self.app._install(Button())
        self.assertEqual(sorted(os.listdir(category)), ['unrelated.txt'])

    def test_uninstall_refuses_unmanaged_folder(self):
        target = p.PythonistaToolsInstaller.get_target_folder('Utilities', 'Test Tool')
        os.makedirs(target)
        btn = Button()
        with redirect_stderr(io.StringIO()):
            self.app.uninstall(btn, None)
        self.assertTrue(os.path.isdir(target))

    def test_hash_mismatch_preserves_unrelated_files(self):
        target = p.PythonistaToolsInstaller.get_target_folder('Utilities', 'Test Tool')
        category = os.path.dirname(target)
        os.makedirs(category)
        unrelated = os.path.join(category, 'unrelated.txt')
        with open(unrelated, 'w') as fp:
            fp.write('keep')
        with open(p.CONF_FILE, 'w') as fp:
            json.dump({'install_path': 'bin', 'trusted_sha256': {
                Button.tool_url: '0' * 64}}, fp)
        with mock.patch.object(p.GitHubRepoInstaller, 'install', return_value={
                'source': Button.tool_url, 'revision': 'a' * 40, 'sha256': '1' * 64}):
            with redirect_stderr(io.StringIO()):
                self.app._install(Button())
        self.assertFalse(os.path.exists(target))
        self.assertEqual(sorted(os.listdir(category)), ['unrelated.txt'])

    def test_missing_hash_refuses_install_without_download(self):
        btn = Button()
        with mock.patch.object(p.GitHubRepoInstaller, 'install') as install:
            with redirect_stderr(io.StringIO()):
                self.app._install(btn)
        install.assert_not_called()
        self.assertFalse(os.path.exists(p.PythonistaToolsInstaller.get_target_folder(
            btn.category_name, btn.tool_name)))

    def test_managed_install_and_uninstall(self):
        btn = Button()
        with open(p.CONF_FILE, 'w') as fp:
            json.dump({'install_path': 'bin', 'trusted_sha256': {
                btn.tool_url: '1' * 64}}, fp)
        with mock.patch.object(p.GitHubRepoInstaller, 'install', return_value={
                'source': btn.tool_url, 'revision': 'a' * 40, 'sha256': '1' * 64}):
            self.app._install(btn)
        target = p.PythonistaToolsInstaller.get_target_folder(btn.category_name, btn.tool_name)
        self.assertTrue(os.path.isfile(os.path.join(target, p.MARKER)))
        self.assertEqual(btn.state, 'uninstall')
        self.app.uninstall(btn, None)
        self.assertFalse(os.path.exists(target))


if __name__ == '__main__':
    unittest.main()
