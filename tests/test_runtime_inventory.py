import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, mock_open, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service.mkga.connector'))
from runtime_inventory import collect, NATIVE_METHODS, _linux_inventory, _installation_method


class RuntimeInventoryTests(unittest.TestCase):
    def setUp(self):
        # Tests never depend on the machine running the suite's os-release/VFS.
        self.distro_patch = patch('runtime_inventory._linux_inventory', return_value={'linuxDistribution': 'unknown'})
        self.distro_patch.start()
        self.addCleanup(self.distro_patch.stop)
        self.vfs_patch = patch('runtime_inventory.xbmcvfs', None)
        self.vfs_patch.start()
        self.addCleanup(self.vfs_patch.stop)

    def fixture(self, methods, version=None, capability=None):
        if version is None:
            version = {'major': 21, 'minor': 2, 'revision': '20261005-83dbb4b-dirty', 'tag': 'stable'}
        if capability is None:
            capability = {'schema': 1, 'nativeLibraryApi': True, 'authorizationSupported': True}
        def response(raw):
            method = json.loads(raw)['method']
            if method == 'VideoLibrary.GetMKGACapabilities':
                return json.dumps({'result': capability})
            if method == 'Application.GetProperties':
                return json.dumps({'result': {'version': version}})
            return json.dumps({'result': {'methods': methods}})
        return Mock(getCondVisibility=Mock(return_value=False), executeJSONRPC=Mock(side_effect=response))

    def test_platforms_and_android_override(self):
        for system, expected in [('Darwin', 'macos'), ('Windows', 'windows'), ('Linux', 'linux'), ('Other', 'unknown')]:
            with self.subTest(system=system), patch('runtime_inventory.platform.system', return_value=system), patch('runtime_inventory.platform.machine', return_value='AMD64'):
                xbmc = self.fixture({})
                runtime = collect(xbmc)
                self.assertEqual({key: runtime[key] for key in ('system', 'architecture', 'nativeLibraryApi')},
                                 {'system': expected, 'architecture': 'x64', 'nativeLibraryApi': 'unavailable'})
                self.assertEqual(runtime['installationMethod'], 'unknown')
                xbmc.getCondVisibility.return_value = True
                runtime = collect(xbmc)
                self.assertEqual(runtime['system'], 'android')
                self.assertEqual(runtime['installationMethod'], 'android_apk')
                self.assertNotIn('linuxDistribution', runtime)

    def test_native_api_requires_complete_set_and_only_reads(self):
        xbmc = self.fixture({name: {} for name in NATIVE_METHODS})
        runtime = collect(xbmc)
        self.assertEqual(runtime['nativeLibraryApi'], 'available')
        self.assertEqual(runtime['nativeApiSchema'], 1)
        self.assertIs(runtime['nativeAuthorizationSupported'], True)
        request = json.loads(xbmc.executeJSONRPC.call_args_list[0].args[0])
        self.assertEqual(request['method'], 'JSONRPC.Introspect')
        self.assertEqual(request['params']['filter']['id'], 'VideoLibrary')
        requests = [json.loads(call.args[0]) for call in xbmc.executeJSONRPC.call_args_list]
        self.assertEqual([request['method'] for request in requests],
                         ['JSONRPC.Introspect', 'VideoLibrary.GetMKGACapabilities', 'Application.GetProperties'])
        self.assertEqual(requests[-1]['params'], {'properties': ['version']})
        for absent in NATIVE_METHODS:
            xbmc = self.fixture({name: {} for name in NATIVE_METHODS if name != absent})
            runtime = collect(xbmc)
            self.assertEqual(runtime['nativeLibraryApi'], 'unavailable')
            self.assertNotIn('nativeApiSchema', runtime)
            self.assertNotIn('nativeAuthorizationSupported', runtime)

    def test_invalid_failed_and_oversize_probes_are_unknown(self):
        for raw in ('bad json', '[]', '{"error":{"code":-32601}}', 'x' * (1024 * 1024 + 1)):
            xbmc = self.fixture({})
            xbmc.executeJSONRPC.side_effect = None
            xbmc.executeJSONRPC.return_value = raw
            runtime = collect(xbmc)
            self.assertEqual(runtime['nativeLibraryApi'], 'unknown')
            self.assertNotIn('kodiVersion', runtime)
        xbmc.executeJSONRPC.side_effect = RuntimeError('offline')
        self.assertEqual(collect(xbmc)['nativeLibraryApi'], 'unknown')

    def test_advertised_methods_without_supported_authorization_are_not_available(self):
        methods = {name: {} for name in NATIVE_METHODS}
        for capability, expected in [({'schema': 1, 'nativeLibraryApi': True, 'authorizationSupported': False}, 'unavailable'), ({'schema': 1, 'nativeLibraryApi': True, 'authorizationSupported': True}, 'available'), ({'schema': True, 'nativeLibraryApi': True, 'authorizationSupported': True}, 'unknown'), ({}, 'unknown'), ({'schema': 2, 'nativeLibraryApi': True, 'authorizationSupported': True}, 'unknown')]:
            xbmc = self.fixture(methods, capability=capability)
            self.assertEqual(collect(xbmc)['nativeLibraryApi'], expected)
        xbmc = self.fixture({})
        xbmc.executeJSONRPC.side_effect = [json.dumps({'result': {'methods': methods}}), json.dumps({'error': {'code': -32601}})]
        self.assertEqual(collect(xbmc)['nativeLibraryApi'], 'unknown')

    def test_architecture_allowlist_does_not_send_arbitrary_values(self):
        for machine, expected in [('aarch64', 'arm64'), ('armv7l', 'armv7'), ('i686', 'x86'), ('private-device-string', 'unknown')]:
            with patch('runtime_inventory.platform.machine', return_value=machine):
                self.assertEqual(collect(self.fixture({}))['architecture'], expected)

    def test_process_bits_distinguish_32_bit_kodi_from_64_bit_kernel(self):
        cases = [('AMD64', 4, 'x86'), ('x86_64', 4, 'x86'),
                 ('aarch64', 4, 'unknown'), ('arm64', 4, 'unknown'),
                 ('armv7l', 4, 'armv7'), ('i686', 4, 'x86'),
                 ('AMD64', 8, 'x64'), ('aarch64', 8, 'arm64')]
        for machine, pointer_size, expected in cases:
            with self.subTest(machine=machine, bits=pointer_size * 8), patch('runtime_inventory.platform.machine', return_value=machine), patch('runtime_inventory.struct.calcsize', return_value=pointer_size) as size:
                runtime = collect(self.fixture({}))
            self.assertEqual(runtime['architecture'], expected)
            self.assertEqual(runtime['processBits'], pointer_size * 8)
            size.assert_called_once_with('P')
        with patch('runtime_inventory.struct.calcsize', return_value=2):
            self.assertNotIn('processBits', collect(self.fixture({})))

    def test_canonical_kodi_version_and_build(self):
        runtime = collect(self.fixture({}))
        self.assertEqual(runtime['kodiVersion'], '21.2')
        self.assertEqual(runtime['kodiVersionTag'], 'stable')
        self.assertEqual(runtime['kodiBuildRevision'], '20261005-83dbb4b-dirty')
        for revision in ('2712E77', 'a' * 40, '20261006-2712e77'):
            version = {'major': 22, 'minor': 0, 'revision': revision, 'tag': 'beta'}
            runtime = collect(self.fixture({}, version=version))
            self.assertEqual(runtime['kodiBuildRevision'], revision.lower())
            self.assertEqual(runtime['kodiVersionTag'], 'beta')

    def test_malformed_kodi_version_cannot_leak_raw_labels(self):
        for version in ([], '21.2 secret', {}, {'major': True, 'minor': 0},
                        {'major': 1000, 'minor': 0}, {'major': 21, 'minor': -1}):
            runtime = collect(self.fixture({}, version=version))
            self.assertNotIn('kodiVersion', runtime)
            self.assertNotIn('kodiVersionTag', runtime)
        for tag in ('my-private-host', ['stable'], None):
            runtime = collect(self.fixture({}, version={'major': 21, 'minor': 2,
                'tag': tag, 'revision': 'private-host /Users/name/secret'}))
            self.assertEqual(runtime['kodiVersionTag'], 'unknown')
            self.assertNotIn('kodiBuildRevision', runtime)
            self.assertNotIn('private', json.dumps(runtime))

    def test_failed_kodi_probe_does_not_erase_valid_capability(self):
        xbmc = self.fixture({})
        xbmc.executeJSONRPC.side_effect = [json.dumps({'result': {'methods': {name: {} for name in NATIVE_METHODS}}}),
            json.dumps({'result': {'schema': 1, 'nativeLibraryApi': True, 'authorizationSupported': True}}),
            'x' * 4097]
        runtime = collect(xbmc)
        self.assertEqual(runtime['nativeLibraryApi'], 'available')
        self.assertNotIn('kodiVersion', runtime)

    def test_linux_distro_and_appliance_classification(self):
        for distro in ('libreelec', 'coreelec', 'ubuntu', 'debian'):
            with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data='ID="%s"\nVERSION_ID="12.0.2"\nPRETTY_NAME="private host"\n' % distro)):
                identity = _linux_inventory()
            self.assertEqual(identity, {'linuxDistribution': distro, 'linuxDistributionVersion': '12.0.2'})
            with patch('runtime_inventory.platform.system', return_value='Linux'), patch('runtime_inventory._linux_inventory', return_value=identity):
                runtime = collect(self.fixture({}))
            self.assertEqual(runtime['installationMethod'], 'linux_appliance' if distro in ('libreelec', 'coreelec') else 'unknown')
            self.assertNotIn('private host', json.dumps(runtime))

    def test_os_release_unknown_invalid_oversize_and_fallback_are_bounded(self):
        cases = [('ID=customerbox\nVERSION_ID=2.3\n', {'linuxDistribution': 'other', 'linuxDistributionVersion': '2.3'}),
                 ('ID=ubuntu\nVERSION_ID="$(private-token)"\n', {'linuxDistribution': 'ubuntu'}),
                 ('ID="$(private-token)"\n', {'linuxDistribution': 'unknown'}),
                 ('ID=ubuntu\n' + 'x' * 16385, {'linuxDistribution': 'unknown'})]
        for text, expected in cases:
            with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data=text)) as reader:
                self.assertEqual(_linux_inventory(), expected)
                for handle in reader.return_value.__enter__.return_value.read.call_args_list:
                    self.assertEqual(handle.args, (16385,))
        reader = mock_open(read_data='ID=debian\nVERSION_ID=12\n')
        with patch('runtime_inventory.os.path.isfile', side_effect=[False, True]), patch('builtins.open', reader):
            self.assertEqual(_linux_inventory(), {'linuxDistribution': 'debian', 'linuxDistributionVersion': '12'})
        self.assertEqual(reader.call_args.args[0], '/usr/lib/os-release')

    def test_current_libreelec_image_target_keeps_build_labels_only(self):
        text = ('ID=libreelec\nVERSION_ID=12.2\nDISTRO_ARCH="Generic.x86_64"\n'
                'DISTRO_PROJECT="Generic"\nDISTRO_DEVICE="Generic-legacy"\n'
                'BUILD_ID="6209f5a0123456789abcdef0123456789abcdef0123"\n'
                'BUILDER_NAME="private builder"\nSERIAL="private serial"\n')
        with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data=text)):
            identity = _linux_inventory()
        self.assertEqual(identity, {'linuxDistribution': 'libreelec', 'linuxDistributionVersion': '12.2',
            'linuxBuildArchitecture': 'Generic.x86_64', 'linuxBuildProject': 'Generic',
            'linuxBuildDevice': 'Generic-legacy',
            'linuxBuildId': '6209f5a0123456789abcdef0123456789abcdef0123'})
        with patch('runtime_inventory.platform.system', return_value='Linux'), patch('runtime_inventory.platform.machine', return_value='x86_64'), patch('runtime_inventory.struct.calcsize', return_value=4), patch('runtime_inventory._linux_inventory', return_value=identity):
            runtime = collect(self.fixture({}))
        self.assertEqual(runtime['architecture'], 'x86')
        self.assertEqual(runtime['processBits'], 32)
        self.assertEqual(runtime['linuxBuildArchitecture'], 'Generic.x86_64')
        self.assertEqual(runtime['installationMethod'], 'linux_appliance')
        self.assertNotIn('private', json.dumps(runtime))

    def test_verified_legacy_libreelec_and_coreelec_target_prefixes(self):
        cases = [('libreelec', 'LIBREELEC', 'RPi4.arm', 'RPi', 'RPi4'),
                 ('coreelec', 'COREELEC', 'Amlogic-ng.arm', 'Amlogic', 'Amlogic-ng')]
        for distro, prefix, architecture, project, device in cases:
            text = 'ID=%s\n%s_ARCH="%s"\n%s_PROJECT="%s"\n%s_DEVICE="%s"\n' % (
                distro, prefix, architecture, prefix, project, prefix, device)
            with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data=text)):
                identity = _linux_inventory()
            self.assertEqual(identity, {'linuxDistribution': distro, 'linuxBuildArchitecture': architecture,
                'linuxBuildProject': project, 'linuxBuildDevice': device})

    def test_image_target_prefixes_never_mix_or_repair_invalid_current_keys(self):
        cases = [('ID=libreelec\nDISTRO_ARCH=Generic.x86_64\nLIBREELEC_PROJECT=RPi\nLIBREELEC_DEVICE=RPi4\n',
                  {'linuxDistribution': 'libreelec', 'linuxBuildArchitecture': 'Generic.x86_64'}),
                 ('ID=libreelec\nDISTRO_ARCH="/private/path"\nLIBREELEC_ARCH=RPi4.arm\n',
                  {'linuxDistribution': 'libreelec'}),
                 ('ID=coreelec\nCOREELEC_ARCH=Amlogic-ng.arm\nCOREELEC_PROJECT=Amlogic\nLIBREELEC_ARCH=RPi4.arm\nLIBREELEC_DEVICE=RPi4\n',
                  {'linuxDistribution': 'coreelec', 'linuxBuildArchitecture': 'Amlogic-ng.arm', 'linuxBuildProject': 'Amlogic'}),
                 ('ID=ubuntu\nLIBREELEC_ARCH=RPi4.arm\nCOREELEC_PROJECT=Amlogic\n',
                  {'linuxDistribution': 'ubuntu'})]
        for text, expected in cases:
            with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data=text)):
                self.assertEqual(_linux_inventory(), expected)

    def test_missing_invalid_and_oversize_image_target_values_are_not_guessed(self):
        fields = ('DISTRO_ARCH', 'DISTRO_PROJECT', 'DISTRO_DEVICE', 'BUILD_ID')
        for value in ('', '/path/private', '../Generic.x86_64', 'target with spaces',
                      '{"private":"value"}', '$(private-token)', '\\private', 'x' * 81, 'tärgét'):
            text = 'ID=libreelec\n' + '\n'.join(field + '=' + value for field in fields)
            with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data=text)):
                self.assertEqual(_linux_inventory(), {'linuxDistribution': 'libreelec'})
        text = 'ID=libreelec\nDISTRO_ARCH=Generic.x86_64\nDISTRO_PROJECT=Generic\nBUILD_ID=' + 'a' * 80
        with patch('runtime_inventory.os.path.isfile', return_value=True), patch('builtins.open', mock_open(read_data=text)):
            identity = _linux_inventory()
        self.assertEqual(identity['linuxBuildId'], 'a' * 80)
        self.assertNotIn('linuxBuildDevice', identity)

    def test_android_excludes_host_os_release_build_targets(self):
        xbmc = self.fixture({})
        xbmc.getCondVisibility.return_value = True
        with patch('runtime_inventory.platform.system', return_value='Linux'), patch('runtime_inventory._linux_inventory') as linux:
            runtime = collect(xbmc)
        linux.assert_not_called()
        self.assertEqual(runtime['system'], 'android')
        self.assertFalse(any(key.startswith('linux') for key in runtime))

    def test_local_special_storage_uses_existing_directories_and_emits_no_paths(self):
        with tempfile.TemporaryDirectory(prefix='mkga-inventory-private-') as root:
            profile = Path(root) / 'profile'
            runtime_dir = Path(root) / 'MKGA.app' / 'Contents' / 'Resources' / 'Kodi'
            profile.mkdir()
            runtime_dir.mkdir(parents=True)
            vfs = Mock(translatePath=Mock(side_effect=lambda value: str(profile) if value == 'special://home' else str(runtime_dir)))
            with patch('runtime_inventory.platform.system', return_value='Darwin'), patch('runtime_inventory.shutil.disk_usage', return_value=types.SimpleNamespace(free=12345678)) as disk, patch('runtime_inventory.os.access', return_value=True):
                runtime = collect(self.fixture({}), vfs)
            self.assertEqual(runtime['installationMethod'], 'macos_app')
            self.assertEqual(runtime['profileFreeBytes'], 12345678)
            self.assertEqual(runtime['runtimeFreeBytes'], 12345678)
            self.assertIs(runtime['profileWritable'], True)
            self.assertIs(runtime['runtimeWritable'], True)
            self.assertEqual({call.args[0] for call in disk.call_args_list}, {str(profile.resolve()), str(runtime_dir.resolve())})
            self.assertNotIn(root, json.dumps(runtime))
            self.assertEqual({call.args[0] for call in vfs.translatePath.call_args_list}, {'special://xbmc', 'special://home'})

    def test_nonlocal_special_paths_and_errors_never_probe_storage(self):
        for path in ('special://home', 'smb://host/private', '//host/share', '\\\\host\\share', 'relative/path', '/path\x00secret', '/nonexistent-mkga-dir'):
            vfs = Mock(translatePath=Mock(return_value=path))
            with patch('runtime_inventory.shutil.disk_usage') as disk:
                runtime = collect(self.fixture({}), vfs)
            disk.assert_not_called()
            for key in ('profileFreeBytes', 'runtimeFreeBytes', 'profileWritable', 'runtimeWritable'):
                self.assertNotIn(key, runtime)
        vfs = Mock(translatePath=Mock(side_effect=RuntimeError('no vfs')))
        self.assertEqual(collect(self.fixture({}), vfs)['installationMethod'], 'unknown')

    def test_storage_values_are_safe_integers_and_failure_is_independent(self):
        with tempfile.TemporaryDirectory() as root:
            vfs = Mock(translatePath=Mock(return_value=root))
            for free in (True, -1, 9007199254740992, '123'):
                with patch('runtime_inventory.shutil.disk_usage', return_value=types.SimpleNamespace(free=free)), patch('runtime_inventory.os.access', return_value=False):
                    runtime = collect(self.fixture({}), vfs)
                self.assertNotIn('profileFreeBytes', runtime)
                self.assertIs(runtime['profileWritable'], False)
            with patch('runtime_inventory.shutil.disk_usage', side_effect=OSError('no disk')), patch('runtime_inventory.os.access', return_value=False):
                runtime = collect(self.fixture({}), vfs)
            self.assertNotIn('runtimeFreeBytes', runtime)
            self.assertIs(runtime['runtimeWritable'], False)

    def test_installation_method_uses_bounded_evidence(self):
        self.assertEqual(_installation_method('windows', '/kodi', '/kodi/portable_data', None), 'windows_portable')
        self.assertEqual(_installation_method('windows', '/Program Files/Kodi', '/profile', None), 'unknown')
        with patch('runtime_inventory.os.path.isfile', return_value=True):
            self.assertEqual(_installation_method('linux', '/app/share/kodi', '/profile', 'ubuntu'), 'linux_flatpak')
        with patch('runtime_inventory.os.path.isfile', return_value=False):
            self.assertEqual(_installation_method('linux', '/app/share/kodi', '/profile', 'ubuntu'), 'unknown')
        for path, expected in [('/snap/kodi/123/usr/share/kodi', 'linux_snap'),
                               ('/tmp/.mount_kodiABC/usr/share/kodi', 'linux_appimage'),
                               ('/usr/share/kodi', 'linux_system'),
                               ('/usr/lib/x86_64-linux-gnu/kodi', 'linux_system'),
                               ('/home/customer/kodi', 'unknown')]:
            self.assertEqual(_installation_method('linux', path, '/profile', 'ubuntu'), expected)


if __name__ == '__main__':
    unittest.main()
