"""Bounded, read-only runtime telemetry; observations never grant install access.

Only allowlisted classifications, Kodi version fields and local storage totals
leave the device. Resolved special paths and operating-system files stay local.
Writable flags describe the observed directory, not permission to replace Kodi.
"""
import json
import os
import platform
import re
import shutil
import struct

try:
    import xbmcvfs
except ImportError:  # Unit tests and tools outside Kodi do not have this module.
    xbmcvfs = None

NATIVE_METHODS = tuple('VideoLibrary.MKGA' + name for name in (
    'UpsertMovie', 'UpsertTVShow', 'UpsertEpisode',
    'RemoveMovie', 'RemoveTVShow', 'RemoveEpisode'))
KODI_VERSION_TAGS = frozenset(('prealpha', 'alpha', 'beta', 'releasecandidate', 'stable'))
LINUX_DISTRIBUTIONS = frozenset((
    'ubuntu', 'debian', 'raspbian', 'linuxmint', 'pop', 'fedora', 'rhel',
    'centos', 'rocky', 'almalinux', 'arch', 'manjaro', 'opensuse',
    'opensuse-leap', 'opensuse-tumbleweed', 'sles', 'alpine', 'gentoo',
    'void', 'nixos', 'osmc', 'libreelec', 'coreelec', 'openelec'))
INSTALLATION_METHODS = frozenset((
    'macos_app', 'windows_portable', 'windows_installer', 'linux_system',
    'linux_flatpak', 'linux_snap', 'linux_appimage', 'linux_appliance',
    'android_apk', 'unknown'))
MAX_SAFE_INTEGER = 9007199254740991
LINUX_BUILD_FIELDS = (
    ('ARCH', 'linuxBuildArchitecture'),
    ('PROJECT', 'linuxBuildProject'),
    ('DEVICE', 'linuxBuildDevice'))
LINUX_OS_RELEASE_FIELDS = frozenset(('ID', 'VERSION_ID', 'BUILD_ID')) | frozenset(
    prefix + field for prefix in ('DISTRO_', 'LIBREELEC_', 'COREELEC_')
    for field, _ in LINUX_BUILD_FIELDS)


def _rpc_result(xbmc, method, request_id, params=None, limit=4096):
    request = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
    if params is not None:
        request['params'] = params
    raw = xbmc.executeJSONRPC(json.dumps(request))
    if not isinstance(raw, str) or len(raw) > limit:
        return None
    value = json.loads(raw)
    if not isinstance(value, dict) or 'error' in value:
        return None
    result = value.get('result')
    return result if isinstance(result, dict) else None


def _native_inventory(xbmc):
    result = {'nativeLibraryApi': 'unknown'}
    try:
        namespace = _rpc_result(xbmc, 'JSONRPC.Introspect', 1, {
            'getdescriptions': False, 'getmetadata': False,
            'filter': {'id': 'VideoLibrary', 'type': 'namespace',
                       'getreferences': False}}, limit=1024 * 1024)
        methods = namespace.get('methods') if namespace else None
        if not isinstance(methods, dict):
            return result
        if not all(name in methods for name in NATIVE_METHODS):
            result['nativeLibraryApi'] = 'unavailable'
            return result
        capabilities = _rpc_result(xbmc, 'VideoLibrary.GetMKGACapabilities', 2)
        if (capabilities and type(capabilities.get('schema')) is int and
                capabilities['schema'] == 1 and
                type(capabilities.get('nativeLibraryApi')) is bool and
                type(capabilities.get('authorizationSupported')) is bool):
            result['nativeApiSchema'] = 1
            result['nativeAuthorizationSupported'] = capabilities['authorizationSupported']
            result['nativeLibraryApi'] = ('available' if capabilities['nativeLibraryApi'] and
                                         capabilities['authorizationSupported'] else 'unavailable')
    except Exception:
        pass
    return result


def _kodi_inventory(xbmc):
    result = {}
    try:
        properties = _rpc_result(xbmc, 'Application.GetProperties', 3, {'properties': ['version']})
        version = properties.get('version') if properties else None
        if not isinstance(version, dict):
            return result
        major, minor = version.get('major'), version.get('minor')
        if (type(major) is int and 0 <= major <= 999 and
                type(minor) is int and 0 <= minor <= 999):
            result['kodiVersion'] = '%d.%d' % (major, minor)
            tag = version.get('tag')
            result['kodiVersionTag'] = (tag if isinstance(tag, str) and tag in
                                        KODI_VERSION_TAGS else 'unknown')
        revision = version.get('revision')
        if (isinstance(revision, str) and len(revision) <= 55 and
                re.fullmatch(r'(?:[0-9]{8}-)?[0-9a-f]{7,40}(?:-dirty)?', revision.lower())):
            result['kodiBuildRevision'] = revision.lower()
    except Exception:
        pass
    return result


def _linux_build_inventory(values, distro):
    """Keep image target labels together; never infer targets from hardware IDs.

    Current LibreELEC writes DISTRO_ keys; LibreELEC 12 uses LIBREELEC_
    and CoreELEC 21.2 uses COREELEC_ (plus some LIBREELEC_ aliases).
    Sources are documented in README. No builder names or hardware serials
    are read. An invalid current key is not repaired from a legacy alias.
    """
    prefixes = ('DISTRO_',)
    if distro == 'libreelec':
        prefixes += ('LIBREELEC_',)
    elif distro == 'coreelec':
        prefixes += ('COREELEC_', 'LIBREELEC_')
    result = {}
    for prefix in prefixes:
        if not any(prefix + field in values for field, _ in LINUX_BUILD_FIELDS):
            continue
        for field, name in LINUX_BUILD_FIELDS:
            value = values.get(prefix + field, '')
            if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value):
                result[name] = value
        break
    build_id = values.get('BUILD_ID', '')
    if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', build_id):
        result['linuxBuildId'] = build_id
    return result


def _linux_inventory():
    """Read two standard bounded files without evaluating os-release shell text."""
    for path in ('/etc/os-release', '/usr/lib/os-release'):
        try:
            if not os.path.isfile(path):
                continue
            with open(path, 'r', encoding='utf-8') as handle:
                text = handle.read(16385)
            if len(text) > 16384:
                continue
            values = {}
            for line in text.splitlines():
                key, separator, value = line.partition('=')
                if key not in LINUX_OS_RELEASE_FIELDS or not separator:
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values[key] = value
            distro = values.get('ID', '')
            if not re.fullmatch(r'[a-z0-9_-]{1,40}', distro):
                continue
            result = {'linuxDistribution': distro if distro in LINUX_DISTRIBUTIONS else 'other'}
            version = values.get('VERSION_ID', '')
            if re.fullmatch(r'[0-9][0-9.-]{0,39}', version):
                result['linuxDistributionVersion'] = version
            result.update(_linux_build_inventory(values, distro))
            return result
        except (OSError, ValueError, UnicodeError):
            continue
    return {'linuxDistribution': 'unknown'}


def _local_special_path(vfs, special_path):
    if vfs is None:
        return None
    try:
        path = vfs.translatePath(special_path)
        if (not isinstance(path, str) or not path or len(path) > 4096 or
                '\x00' in path or '://' in path or path.startswith(('//', '\\\\')) or
                not os.path.isabs(path)):
            return None
        path = os.path.realpath(path)
        return path if os.path.isdir(path) else None
    except Exception:
        return None


def _storage_inventory(path, prefix):
    if path is None:
        return {}
    result = {}
    try:
        free = shutil.disk_usage(path).free
        if type(free) is int and 0 <= free <= MAX_SAFE_INTEGER:
            result[prefix + 'FreeBytes'] = free
    except (OSError, ValueError, OverflowError):
        pass
    try:
        result[prefix + 'Writable'] = bool(os.access(path, os.W_OK))
    except (OSError, ValueError):
        pass
    return result


def _installation_method(system, runtime_path, profile_path, distro):
    if system == 'android':
        return 'android_apk'
    if system == 'linux' and distro in ('libreelec', 'coreelec', 'openelec'):
        return 'linux_appliance'
    if runtime_path is None:
        return 'unknown'
    normalized = runtime_path.replace('\\', '/').rstrip('/')
    if system == 'macos' and re.search(r'\.app/Contents/(?:Resources|MacOS)(?:/|$)', normalized):
        return 'macos_app'
    if system == 'windows':
        portable = os.path.join(runtime_path, 'portable_data')
        if profile_path is not None and os.path.normcase(profile_path) == os.path.normcase(portable):
            return 'windows_portable'
        # A directory name alone does not prove Windows installer registration.
        return 'unknown'
    if system == 'linux':
        if normalized.startswith('/app/') and os.path.isfile('/.flatpak-info'):
            return 'linux_flatpak'
        if normalized.startswith('/snap/kodi/'):
            return 'linux_snap'
        if re.search(r'/(?:\.mount_[^/]+)/(?:usr/)?(?:share|lib)/kodi(?:/|$)', normalized):
            return 'linux_appimage'
        if re.fullmatch(r'/usr/(?:local/)?(?:share|lib|lib64)(?:/[^/]+)?/kodi', normalized):
            return 'linux_system'
    return 'unknown'


def collect(xbmc, vfs=None):
    system = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}.get(platform.system(), 'unknown')
    try:
        if xbmc.getCondVisibility('System.Platform.Android'):
            system = 'android'
    except Exception:
        pass
    architecture = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64',
                    'amd64': 'x64', 'i386': 'x86', 'i686': 'x86',
                    'armv7l': 'armv7'}.get(platform.machine().lower(), 'unknown')
    result = {'system': system, 'architecture': architecture}
    process_bits = struct.calcsize('P') * 8
    if process_bits in (32, 64):
        result['processBits'] = process_bits
        if process_bits == 32 and architecture == 'x64':
            result['architecture'] = 'x86'
        elif process_bits == 32 and architecture == 'arm64':
            # A 64-bit ARM kernel does not identify a 32-bit process's ISA
            # (ARMv6 and ARMv7 are different targets). Do not guess ARMv7.
            result['architecture'] = 'unknown'
    result.update(_native_inventory(xbmc))
    result.update(_kodi_inventory(xbmc))
    if system == 'linux':
        result.update(_linux_inventory())
    vfs = xbmcvfs if vfs is None else vfs
    runtime_path = _local_special_path(vfs, 'special://xbmc')
    profile_path = _local_special_path(vfs, 'special://home')
    result['installationMethod'] = _installation_method(
        system, runtime_path, profile_path, result.get('linuxDistribution'))
    result.update(_storage_inventory(profile_path, 'profile'))
    result.update(_storage_inventory(runtime_path, 'runtime'))
    return result
