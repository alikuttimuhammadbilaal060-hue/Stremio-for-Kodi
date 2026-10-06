# Connector 0.3.9

This release candidate adds bounded, read-only runtime inventory: Kodi version
and revision, MKGA API schema and authorization support, Linux distribution,
version and image build target, observed installation method, available profile/runtime storage and
directory write access. Android is classified separately from Linux. Unknown or
unreliable observations remain unknown or omitted. Directory write access and
advertised API capabilities do not grant installation or account access.

The inventory never sends resolved local paths, raw build labels, environment
variables, operating-system file contents, logs or credentials. It runs no
commands or package-manager probes. Existing system, architecture and
nativeLibraryApi fields remain compatible with older consumers.

Process bitness distinguishes a 32-bit Kodi from its 64-bit host kernel. A
32-bit process on an x64 kernel is reported as x86; a 32-bit ARM process on an
ARM64 kernel remains unknown when its precise ARM instruction set is unproven.
Linux image target labels and build ID are optional bounded software metadata,
not hardware identifiers. Missing or invalid target labels are not guessed.

The target key names are verified against the official image builders:
[current LibreELEC DISTRO_ keys](https://raw.githubusercontent.com/LibreELEC/LibreELEC.tv/master/scripts/image),
[LibreELEC 12.0.2 LIBREELEC_ keys](https://raw.githubusercontent.com/LibreELEC/LibreELEC.tv/12.0.2/scripts/image),
and [CoreELEC 21.2 COREELEC_ keys](https://raw.githubusercontent.com/CoreELEC/CoreELEC/21.2-Omega/scripts/image).
Each target uses one coherent prefix family; individual fields are not combined
across current and legacy keys.

Adds optional protected pairing using the Mac application-owned Secure Enclave
helper. Pairing returns an explicit deviceProofRequired acknowledgement. Once
protected, every agent request signs a short-lived, one-time challenge bound to
method/path/body. Missing keys/helpers stop the request. Private key material is
not stored in Kodi settings or backups.

Opening a paired Connector offers Refresh connection and Pair again with a new
code. Canceling leaves existing pairing unchanged. Protected pairing requires the
updated backend and application helper; ordinary clients remain compatible.
Admin MKGA Build prepare/apply requires registered device protection. These Build
options are owner-only and are not exposed in customer My Kodi.

This is local development source, not a published Connector release. Final
platform packaging, signing, complete pairing inside Kodi and offline Build
entitlement enforcement remain open. Do not infer full copied-install protection
from the presence of this addon or a local settings flag.


Whole Mac app lifecycle can be selected by a local
`special://home/mkga-installer/runtime.json` with `mode: clean-macos-app`.
It requires absolute local `python`, `installer`, `stagingRoot`, `app` and `home`
paths. The configured app must match the currently executing Kodi application.
Installer, staging root, app and profile must be separate roots; the external
installer must contain the complete helper bundle and `trusted-public.pem`.
Admin commands supply only package/signature URLs or a prepared stage ID.
Readiness, prepare/apply routing and stage/job inventory use this local config.
The Connector itself does not bootstrap replacement of the Kodi application.
The external MKGA installer must provision its local configuration and trust
key, complete the pairing handoff, and report the post-install result. Platform
runtime availability and production authorization must be verified separately
before offering a complete MKGA installation.
