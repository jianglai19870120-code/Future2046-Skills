#!/usr/bin/env python3
"""Check release and package versions for every registered Skill."""
import argparse
import re
from pathlib import Path
import yaml
from check_skill_registry import registry


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True)
    root = Path(ap.parse_args().root).resolve()
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    errors = []
    if not re.fullmatch(r'\d+\.\d+\.\d+', version): errors.append('VERSION is not semver')
    data = registry(root)
    if data.get('release_version') != version: errors.append('registry release_version differs')
    for entry in data['skills']:
        if entry.get('version') != version: errors.append(f"{entry.get('id')}: registry version differs")
        pkg = root / entry['package_path']
        if yaml.safe_load((pkg / 'skill.yaml').read_text(encoding='utf-8')).get('version') != version:
            errors.append(f"{entry['id']}: skill.yaml version differs")
    if not re.search(rf'^##\s+{re.escape(version)}\s+-', (root / 'CHANGELOG.md').read_text(encoding='utf-8'), re.M):
        errors.append('CHANGELOG version heading missing')
    if errors:
        print('FAIL'); [print('- ' + x) for x in errors]; return 1
    print('PASS: version ' + version); return 0


if __name__ == '__main__': raise SystemExit(main())
