"""Read-only prerequisite inventory; no installs, network calls, or credential reads."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path)
    args = parser.parse_args()
    project = args.project.expanduser().resolve() if args.project else None
    flutter = bool(project and (project / 'pubspec.yaml').is_file())
    android = project / 'android' if flutter else project
    try:
        version = importlib.metadata.version('playflow')
    except importlib.metadata.PackageNotFoundError:
        version = None
    binaries = {name: shutil.which(name) for name in ('java', 'keytool', 'jarsigner', 'firefox')}
    if flutter:
        binaries['flutter'] = shutil.which('flutter')
    required = ['java', 'keytool', 'jarsigner'] + (['flutter'] if flutter else [])
    missing = [name for name in required if not binaries[name]]
    if not version:
        missing.append('playflow distribution')
    if project and not project.is_dir():
        missing.append('project directory')
    wrapper = android / ('gradlew.bat' if os.name == 'nt' else 'gradlew') if android else None
    if wrapper and not wrapper.is_file():
        missing.append('Android Gradle wrapper')
    target = platform.system()
    report = {
        'python': platform.python_version(),
        'platform': target,
        'product_target': target in {'Linux', 'Windows'},
        'windows_live_integration_verified': False,
        'playflow_version': version,
        'project': str(project) if project else None,
        'project_kind': 'flutter' if flutter else 'native_or_unspecified',
        'binaries': binaries,
        'gradle_wrapper': str(wrapper) if wrapper else None,
        'bundletool_present': (Path.home() / '.cache/playflow/tools/bundletool-all-1.18.3.jar').is_file(),
        'missing': missing,
        'browser_note': 'Firefox may be installed outside PATH; select the existing signed-in profile.',
        'scope': 'Availability only; does not verify versions, Android SDK, ACLs, signing, or Console access.',
    }
    print(json.dumps(report, indent=2))
    return 2 if missing or not report['product_target'] or sys.version_info < (3, 11) else 0


if __name__ == '__main__':
    raise SystemExit(main())
