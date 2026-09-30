# code: utf-8
"""
Installer program to help install tools registered on the Pythonista Tools GitHub repo.
"""
import os
import sys
import requests
import re
import functools
import shutil
import json
import zipfile
import tempfile
import stat
import hashlib
import io
import struct

from six.moves.urllib.parse import urlparse, urljoin
from six import string_types

try:
    import ui
    import console
    import webbrowser
except ImportError:
    import dummyui as ui
    import dummyconsole as console

__version__ = '1.1.0-security'

INSTALL_PATH_DEFAULT = 'bin'
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONF_FILE = os.path.join(SCRIPT_DIR, 'ptinstaller.conf')
MARKER = '.ptinstaller-installed.json'
MAX_DOWNLOAD = 50 * 1024 * 1024
MAX_FILE = 25 * 1024 * 1024
MAX_UNPACKED = 100 * 1024 * 1024
MAX_FILES = 2000
CHUNK = 64 * 1024


def safe_component(value):
    """A catalog name or a configuration directory is one path component."""
    if (not isinstance(value, string_types) or not value or value in ('.', '..') or
            '/' in value or '\\' in value or ':' in value or
            any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Unsafe path component: %r' % value)
    return value


def safe_child(root, name):
    """Reject traversal and existing symlinks in an archive-relative path."""
    if (not name or name.startswith('/') or '\\' in name or '\x00' in name or
            any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('Unsafe archive path: %r' % name)
    destination = os.path.join(root, *name.split('/'))
    current = root
    for part in name.split('/'):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ValueError('Symlink in destination: %r' % name)
    return destination


def checked_get(url, maximum=MAX_DOWNLOAD):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('HTTPS is required')
    response = requests.get(url, stream=True, timeout=(10, 30))
    try:
        response.raise_for_status()
        final = urlparse(response.url)
        if (final.scheme != 'https' or final.hostname not in
                ('api.github.com', 'raw.githubusercontent.com',
                 'github.com', 'codeload.github.com')):
            raise ValueError('Download redirected outside trusted HTTPS hosts')
        data = bytearray()
        for chunk in response.iter_content(CHUNK):
            if chunk:
                data.extend(chunk)
                if len(data) > maximum:
                    raise ValueError('Download exceeds size limit')
        return bytes(data)
    finally:
        response.close()


def github_parts(url):
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or
            parsed.query or parsed.fragment or len(parts) != 2):
        return None
    try:
        owner, repo = [safe_component(part) for part in parts]
    except ValueError:
        return None
    if not re.match(r'^[A-Za-z0-9][A-Za-z0-9-]*$', owner):
        return None
    if not re.match(r'^[A-Za-z0-9_.-]+$', repo):
        return None
    return owner, repo


def gist_id_from_url(url):
    parsed = urlparse(url)
    parts = parsed.path.strip('/').split('/')
    if (parsed.scheme != 'https' or parsed.netloc != 'gist.github.com' or
            parsed.query or parsed.fragment or len(parts) != 2 or
            not re.match(r'^[0-9a-fA-F]+$', parts[1])):
        return None
    return parts[1]

class InvalidGistURLError(Exception):
    pass


class NoFilesInGistError(Exception):
    pass


class GistDownloadError(Exception):
    pass


class NoActivityIndicator(object):
    """Keep the installer usable when this optional UI widget is unavailable."""

    def start(self):
        pass

    def stop(self):
        pass


class GitHubAPI(object):
    API_URL = 'https://api.github.com'

    @staticmethod
    def contents(owner, repo):
        url = '{}/repos/{}/{}/contents'.format(GitHubAPI.API_URL, owner, repo)
        return json.loads(checked_get(url, 2 * 1024 * 1024).decode('utf-8'))


class PythonistaToolsRepo(object):
    """
    Manage and gather information from the Pythonista Tools repo.
    """

    PATTERN_NAME_URL_DESCRIPTION = re.compile(r'^\| *\[([^]]+)\] *(\[([^]]*)\])?[^|]+\| *(.*) *\|', re.MULTILINE)
    PATTERN_NAME_URL = re.compile(r'^\[([^]]+)\]: *(.*)', re.MULTILINE)

    def __init__(self):
        self.owner = 'Pythonista-Tools'
        self.repo = 'Pythonista-Tools'

        self.cached_tools_dict = {}

    def get_categories(self):
        """
        Get URL of all the markdown files that list Pythonista tools of different categories.
        """
        categories = {}
        for content in GitHubAPI.contents(self.owner, self.repo):
            name = content['name']
            if name.endswith('.md') and name not in ['README.md']:
                categories[os.path.splitext(name)[0]] = {'url': content['download_url'],
                                                         'sha': content['sha']}
        return categories

    def get_tools_from_md(self, url_md):
        """
        Retrieve markdown file from the given URL and parse its content to build a dict
        of tools.
        :return:
        """
        # If results are available in the cache, avoid hitting the web
        if url_md not in self.cached_tools_dict:
            parsed = urlparse(url_md)
            if parsed.scheme != 'https' or parsed.netloc != 'raw.githubusercontent.com':
                raise ValueError('Unexpected catalog URL')
            md = checked_get(url_md, 2 * 1024 * 1024).decode('utf-8')
            # Find all script name and its url
            tools_dict = {}
            for name, _, url, description in self.PATTERN_NAME_URL_DESCRIPTION.findall(md):
                tools_dict[name] = {'url': url, 'description': description.strip()}

            for name, url in self.PATTERN_NAME_URL.findall(md):
                if name in tools_dict:
                    tools_dict[name]['url'] = url
                else:
                    for tool_name, tool_content in tools_dict.items():
                        if tool_content['url'] == name:
                            tool_content['url'] = url
                        if tool_content['description'] == '[%s]' % name:
                            tool_content['description'] = url

            # Filter out tools that has no download url
            self.cached_tools_dict[url_md] = {k: v for k, v in tools_dict.items() if v['url']}

        return self.cached_tools_dict[url_md]


class GitHubRepoInstaller(object):
    @staticmethod
    def get_github_user_repo(url):
        return github_parts(url)

    def download(self, url):
        parts = self.get_github_user_repo(url)
        if not parts:
            raise ValueError('Expected an HTTPS GitHub repository URL')
        owner, repo = parts
        api = 'https://api.github.com/repos/{}/{}'.format(owner, repo)
        metadata = json.loads(checked_get(api, 1024 * 1024).decode('utf-8'))
        branch = metadata['default_branch']
        # Resolve the mutable default branch once, then fetch that exact commit.
        from six.moves.urllib.parse import quote
        commit_url = api + '/commits/' + quote(branch, safe='')
        commit = json.loads(checked_get(commit_url, 1024 * 1024).decode('utf-8'))['sha']
        if not re.match(r'^[0-9a-f]{40}$', commit):
            raise ValueError('Invalid commit ID')
        archive_url = 'https://github.com/{}/{}/archive/{}.zip'.format(owner, repo, commit)
        return checked_get(archive_url), commit

    def install(self, url, target_folder):
        data, commit = self.download(url)
        total = 0
        seen = set()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES:
                raise ValueError('Too many archive members')
            roots = set(info.filename.split('/')[0] for info in members)
            if len(roots) != 1:
                raise ValueError('Archive must have one top-level directory')
            prefix = roots.pop() + '/'
            for info in members:
                name = info.filename
                if name.startswith('/') or '\\' in name or '\x00' in name:
                    raise ValueError('Unsafe archive member path')
                if not name.startswith(prefix):
                    raise ValueError('Archive path outside top-level directory')
                relative = name[len(prefix):].rstrip('/')
                if not relative:
                    continue
                mode = (info.external_attr >> 16) & 0xffff
                if stat.S_IFMT(mode) not in (0, stat.S_IFDIR, stat.S_IFREG):
                    raise ValueError('Unsupported archive entry type')
                if info.file_size > MAX_FILE:
                    raise ValueError('Archive member exceeds size limit')
                total += info.file_size
                if total > MAX_UNPACKED:
                    raise ValueError('Archive exceeds expanded size limit')
                destination = safe_child(target_folder, relative)
                if destination in seen:
                    raise ValueError('Duplicate archive path')
                seen.add(destination)
                if relative == MARKER:
                    raise ValueError('Reserved installer filename')
                if name.endswith('/'):
                    if not os.path.isdir(destination):
                        os.makedirs(destination)
                else:
                    parent = os.path.dirname(destination)
                    if not os.path.isdir(parent):
                        os.makedirs(parent)
                    count = 0
                    with archive.open(info) as source:
                        with open(destination, 'wb') as out:
                            while True:
                                chunk = source.read(CHUNK)
                                if not chunk:
                                    break
                                count += len(chunk)
                                if count > MAX_FILE or count > info.file_size:
                                    raise ValueError('Archive member exceeds declared size')
                                out.write(chunk)
        return {'source': url, 'revision': commit, 'sha256': hashlib.sha256(data).hexdigest()}


class GistInstaller(object):
    @staticmethod
    def get_gist_id(url):
        return gist_id_from_url(url)

    def download(self, url):
        gist_id = self.get_gist_id(url)
        if gist_id:
            json_url = 'https://api.github.com/gists/' + gist_id
            try:
                gist_info = json.loads(checked_get(json_url, MAX_DOWNLOAD).decode('utf-8'))
                files = gist_info['files']
            except (ValueError, KeyError, requests.RequestException):
                raise GistDownloadError()
            file_info_list = []
            for file_info in files.values():
                lang = file_info.get('language', None)
                if lang != 'Python' and not file_info['filename'].endswith('.pyui'):
                    continue
                file_info_list.append(file_info)
            if len(file_info_list) == 0:
                raise NoFilesInGistError()
            else:
                return file_info_list
        else:
            raise InvalidGistURLError()

    def install(self, url, target_folder):
        files = self.download(url)
        total = 0
        digest = hashlib.sha256()
        for file_info in sorted(files, key=lambda item: item['filename']):
            filename = safe_component(file_info['filename'])
            if filename == MARKER:
                raise ValueError('Reserved installer filename')
            content = file_info.get('content')
            if content is None or file_info.get('truncated'):
                raise ValueError('Gist content is incomplete')
            encoded = content.encode('utf-8')
            encoded_name = filename.encode('utf-8')
            digest.update(struct.pack('>Q', len(encoded_name)) + encoded_name)
            digest.update(struct.pack('>Q', len(encoded)) + encoded)
            total += len(encoded)
            if len(encoded) > MAX_FILE or total > MAX_UNPACKED:
                raise ValueError('Gist exceeds size limit')
            with open(safe_child(target_folder, filename), 'wb') as outs:
                outs.write(encoded)
        return {'source': url, 'revision': None, 'sha256': digest.hexdigest()}


class InstallButton(object):
    INSTALL = '  Install  '
    UNINSTALL = '  Uninstall  '
    LOADING = '  Loading  '

    def __init__(self, app, cell, category_name, tool_name, tool_url):
        self.app, self.cell = app, cell
        self.category_name, self.tool_name, self.tool_url = category_name, tool_name, tool_url

        self.btn = ui.Button()
        self.cell.content_view.add_subview(self.btn)
        self.btn.font = ('Helvetica', 12)
        self.btn.background_color = 'white'
        self.btn.border_width = 1
        self.btn.corner_radius = 5
        self.btn.size_to_fit()
        self.btn.width = 58
        self.btn.x = self.app.nav_view.width - self.btn.width - 8
        self.btn.y = (self.cell.height - self.btn.height) / 2

        if self.app.is_tool_installed(self.category_name, tool_name):
            self.set_state_uninstall()
        else:
            self.set_state_install()

    def set_state_loading(self):
        self.btn.title = self.LOADING
        self.btn.action = None
        self.btn.tint_color = 'green'
        self.btn.border_color = 'green'

    def set_state_install(self):
        self.btn.title = self.INSTALL
        self.btn.action = functools.partial(self.app.install, self)
        self.btn.tint_color = 'blue'
        self.btn.border_color = 'blue'

    def set_state_uninstall(self):
        self.btn.title = self.UNINSTALL
        self.btn.action = functools.partial(self.app.uninstall, self)
        self.btn.tint_color = (0, 0.478, 1)
        self.btn.border_color = (0, 0.478, 1)


class ToolsTable(object):
    def __init__(self, app, category_name, category_url):
        self.app = app
        self.category_name = category_name
        self.category_url = category_url
        self.view = ui.TableView(frame=(0, 0, 640, 640))
        self.view.name = category_name

        self.tools_dict = self.app.repo.get_tools_from_md(category_url)
        self.tool_names = sorted(self.tools_dict.keys())

        self.view.data_source = self
        self.view.delegate = self

    def tableview_number_of_sections(self, tableview):
        return 1

    def tableview_number_of_rows(self, tableview, section):
        return len(self.tools_dict)

    def tableview_cell_for_row(self, tableview, section, row):
        cell = ui.TableViewCell('subtitle')
        tool_name = self.tool_names[row]
        tool_url = self.tools_dict[tool_name]['url']
        cell.text_label.text = tool_name
        cell.detail_text_label.text = self.tools_dict[tool_name]['description']
        # TODO: Cell does not increase its height when label has multi lines of text
        # cell.detail_text_label.line_break_mode = ui.LB_WORD_WRAP
        # cell.detail_text_label.number_of_lines = 0

        InstallButton(self.app, cell, self.category_name, tool_name, tool_url)

        return cell

    def tableview_can_delete(self, tableview, section, row):
        return False

    def tableview_can_move(self, tableview, section, row):
        return False


class CategoriesTable(object):
    def __init__(self, app):
        self.app = app
        self.view = ui.TableView(frame=(0, 0, 640, 640))
        self.view.name = 'Categories'
        self.categories_dict = {}
        self.load()

    @ui.in_background
    def load(self):
        self.app.activity_indicator.start()
        try:
            self.categories_dict = self.app.repo.get_categories()
            categories_listdatasource = ui.ListDataSource(
                {'title': category_name, 'accessory_type': 'disclosure_indicator'}
                for category_name in sorted(self.categories_dict.keys())
            )
            categories_listdatasource.action = self.category_item_tapped
            categories_listdatasource.delete_enabled = False

            self.view.data_source = categories_listdatasource
            self.view.delegate = categories_listdatasource
            self.view.reload()
        except Exception as e:
            console.hud_alert('Failed to load Categories', 'error', 1.0)
        finally:
            self.app.activity_indicator.stop()

    @ui.in_background
    def category_item_tapped(self, sender):
        self.app.activity_indicator.start()
        try:
            category_name = sender.items[sender.selected_row]['title']
            category_url = self.categories_dict[category_name]['url']
            tools_table = ToolsTable(self.app, category_name, category_url)
            self.app.nav_view.push_view(tools_table.view)
        except Exception as e:
            console.hud_alert('Failed to load tools list', 'error', 1.0)
        finally:
            self.app.activity_indicator.stop()


class PythonistaToolsInstaller(object):

    def __init__(self):
        self.repo = PythonistaToolsRepo()
        self.github_installer = GitHubRepoInstaller()
        self.gist_installer = GistInstaller()

        indicator_class = getattr(ui, 'ActivityIndicator', None)
        if indicator_class is None:
            self.activity_indicator = NoActivityIndicator()
        else:
            self.activity_indicator = indicator_class(flex='LTRB')
            self.activity_indicator.style = 10

        categories_table = CategoriesTable(self)
        self.nav_view = ui.NavigationView(categories_table.view)
        self.nav_view.name = 'Pythonista Tools Installer'

        if indicator_class is not None:
            self.nav_view.add_subview(self.activity_indicator)
            self.activity_indicator.frame = (0, 0, self.nav_view.width, self.nav_view.height)
            self.activity_indicator.bring_to_front()
    
    @staticmethod
    def get_install_path():
        try:
            with open(CONF_FILE, 'r') as f:
                config = json.load(f)
        except IOError:
            config = {}
        return safe_component(config.get('install_path', INSTALL_PATH_DEFAULT))

    @staticmethod
    def expected_hash(url):
        try:
            with open(CONF_FILE, 'r') as fp:
                expected = json.load(fp).get('trusted_sha256', {}).get(url)
        except IOError:
            expected = None
        if expected is None:
            raise ValueError('No trusted SHA-256 configured for this tool')
        if (not isinstance(expected, string_types) or
                not re.match(r'^[0-9a-fA-F]{64}$', expected)):
            raise ValueError('Invalid SHA-256 in configuration')
        return expected.lower()

    @staticmethod
    def get_install_root():
        documents = os.path.expanduser('~/Documents')
        root = os.path.join(documents, PythonistaToolsInstaller.get_install_path())
        if os.path.islink(documents) or os.path.islink(root):
            raise ValueError('Install root must not be a symlink')
        return root

    @staticmethod
    def get_target_folder(category_name, tool_name):
        install_root = PythonistaToolsInstaller.get_install_root()
        category = os.path.join(install_root, safe_component(category_name))
        target = os.path.join(category, safe_component(tool_name))
        if os.path.islink(category) or os.path.islink(target):
            raise ValueError('Install path must not contain a symlink')
        return target

    @staticmethod
    def is_tool_installed(category_name, tool_name):
        try:
            target = PythonistaToolsInstaller.get_target_folder(category_name, tool_name)
            return os.path.isfile(os.path.join(target, MARKER))
        except ValueError:
            return False

    def install(self, btn, sender):
        btn.set_state_loading()
        self._install(btn)

    @ui.in_background
    def _install(self, btn):
        self.activity_indicator.start()
        staging = None
        try:
            install_path = PythonistaToolsInstaller.get_install_path()
            target_folder = PythonistaToolsInstaller.get_target_folder(btn.category_name,
                                                                       btn.tool_name)
            if self.gist_installer.get_gist_id(btn.tool_url):
                installer = self.gist_installer
            elif self.github_installer.get_github_user_repo(btn.tool_url):
                installer = self.github_installer
            else:  # any other url types, including iTunes
                external = urlparse(btn.tool_url)
                if external.scheme != 'https' or not external.hostname:
                    raise ValueError('External links must use HTTPS')
                webbrowser.open(btn.tool_url)
                btn.set_state_install()
                return
            if os.path.lexists(target_folder):
                raise ValueError('Install target already exists; existing files were preserved')
            expected = self.expected_hash(btn.tool_url)
            category = os.path.dirname(target_folder)
            if not os.path.isdir(category):
                os.makedirs(category)
            staging = tempfile.mkdtemp(prefix='.ptinstaller-', dir=category)
            receipt = installer.install(btn.tool_url, staging)
            if receipt['sha256'] != expected:
                raise ValueError('SHA-256 does not match trusted configuration')
            receipt['tool'] = btn.tool_name
            with open(os.path.join(staging, MARKER), 'w') as marker:
                json.dump(receipt, marker)
            if os.path.lexists(target_folder):
                raise ValueError('Install target appeared while downloading')
            os.rename(staging, target_folder)
            staging = None
            btn.set_state_uninstall()
            console.hud_alert('%s installed at %s' % (btn.tool_name, install_path), 'success', 1.0)
        except Exception as e:
            btn.set_state_install()  # revert the state
            # Display some debug messages
            etype, evalue, tb = sys.exc_info()
            sys.stderr.write('%s\n' % repr(e))
            import traceback
            traceback.print_exception(etype, evalue, tb)
            console.hud_alert('Installation refused: %s' % str(e)[:70], 'error', 2.0)
        finally:
            if staging is not None and os.path.isdir(staging) and not os.path.islink(staging):
                shutil.rmtree(staging)
            self.activity_indicator.stop()

    def uninstall(self, btn, sender):
        try:
            target_folder = PythonistaToolsInstaller.get_target_folder(btn.category_name,
                                                                       btn.tool_name)
            marker = os.path.join(target_folder, MARKER)
            if (not os.path.isdir(target_folder) or os.path.islink(target_folder) or
                    not os.path.isfile(marker) or os.path.islink(marker)):
                raise ValueError('Folder is not a managed installation')
            with open(marker) as fp:
                receipt = json.load(fp)
            if receipt.get('tool') != btn.tool_name or receipt.get('source') != btn.tool_url:
                raise ValueError('Installation marker does not match the selected tool')
            for directory, dirs, files in os.walk(target_folder):
                if any(os.path.islink(os.path.join(directory, name)) for name in dirs + files):
                    raise ValueError('Installation contains a symlink; refusing to remove it')
            shutil.rmtree(target_folder)
            btn.set_state_install()
            console.hud_alert('%s uninstalled' % btn.tool_name, 'success', 1.0)
        except Exception as e:
            sys.stderr.write('%s\n' % repr(e))
            console.hud_alert('Uninstall refused: check installation folder', 'error', 2.0)

    def launch(self):
        self.nav_view.present('fullscreen')


if __name__ == '__main__':
    ptinstaller = PythonistaToolsInstaller()
    ptinstaller.launch()
