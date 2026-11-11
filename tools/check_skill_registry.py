#!/usr/bin/env python3
"""Check every Skill and its optional workspace template."""
import argparse
import re
from pathlib import Path
import yaml


def registry(root):
    data = yaml.safe_load((root / 'shared/skill-registry.yaml').read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('skills'), list):
        raise ValueError('invalid registry schema')
    return data


def relative(root, value):
    if not isinstance(value, str) or not value or '\\' in value or Path(value).is_absolute() or '..' in Path(value).parts:
        raise ValueError(f'invalid relative path: {value!r}')
    result = (root / value).resolve()
    if not result.is_relative_to(root.resolve()): raise ValueError(f'path escapes root: {value}')
    return result


def check(root):
    errors, ids, directories, templates = [], set(), set(), set()
    data = registry(root)
    framework = data.get('framework', {})
    router_id = framework.get('router_id')
    router_folder = framework.get('router_package_directory')
    member_prefix = framework.get('member_id_prefix')
    if router_id != 'future2046' or router_folder != 'Future2046-router' or member_prefix != 'future2046-':
        errors.append('invalid fixed framework routing contract')
    entries = data['skills']
    for entry in entries:
        sid, folder = entry.get('id'), entry.get('package_directory')
        if not isinstance(sid, str) or (sid != router_id and not re.fullmatch(rf'{re.escape(member_prefix)}[a-z0-9]+(?:-[a-z0-9]+)*', sid)):
            errors.append(f'invalid id: {sid!r}'); continue
        if sid in ids: errors.append(f'duplicate id: {sid}')
        ids.add(sid)
        if not isinstance(folder, str) or not re.fullmatch(r'Future2046-[a-z0-9]+(?:-[a-z0-9]+)*', folder):
            errors.append(f'{sid}: invalid package_directory'); continue
        if sid == router_id and folder != router_folder: errors.append('router package_directory mismatch')
        if folder in directories: errors.append(f'duplicate directory: {folder}')
        directories.add(folder)
        if entry.get('package_path') != f'skills/{folder}': errors.append(f'{sid}: package_path mismatch')
        pkg = root / 'skills' / folder
        if not pkg.is_dir(): errors.append(f'{sid}: package missing'); continue
        try:
            meta = yaml.safe_load((pkg / 'skill.yaml').read_text(encoding='utf-8'))
            skill = (pkg / entry.get('entrypoint', 'SKILL.md')).read_text(encoding='utf-8')
            front = yaml.safe_load(skill.split('---', 2)[1]) if skill.startswith('---') else {}
            agent = yaml.safe_load((pkg / 'agents/openai.yaml').read_text(encoding='utf-8'))
            for key in ('id','package_directory','display_name','version','entrypoint','workspace_template','supported_agents','runtime','distribution'):
                if meta.get(key) != entry.get(key): errors.append(f'{sid}: skill.yaml {key} mismatch')
            if front.get('name') != sid or not front.get('description'): errors.append(f'{sid}: invalid SKILL.md frontmatter')
            if agent.get('interface', {}).get('display_name') != entry.get('display_name'): errors.append(f'{sid}: openai display_name mismatch')
            if not (pkg / 'README.md').is_file(): errors.append(f'{sid}: README missing')
            agents = entry.get('supported_agents')
            if not isinstance(agents, list) or not agents or len(agents) != len(set(agents)):
                errors.append(f'{sid}: invalid supported_agents')
            for test in entry.get('tests', []):
                if not relative(pkg, test).is_file(): errors.append(f'{sid}: test missing: {test}')
            template_name = entry.get('workspace_template', '')
            if template_name:
                template = relative(root, template_name)
                if template.parent != root / 'workspaces' or not template.is_dir():
                    errors.append(f'{sid}: template missing or misplaced')
                else:
                    templates.add(template.name)
                    config = yaml.safe_load((template / 'workspace.yaml').read_text(encoding='utf-8'))
                    if config.get('technical_skill_name') != folder: errors.append(f'{sid}: template skill name mismatch')
                    if not (template / 'README.md').is_file(): errors.append(f'{sid}: template README missing')
                    roots = [key for key in config if key.endswith('_root')]
                    if not roots: errors.append(f'{sid}: template has no directory fields')
                    for key in roots:
                        target = relative(template, config.get(key))
                        if target.parent != template or not target.is_dir(): errors.append(f'{sid}: workspace directory {key} missing')
        except (OSError, TypeError, ValueError, yaml.YAMLError, KeyError) as exc:
            errors.append(f'{sid}: {exc}')
    for folder in sorted({p.name for p in (root / 'skills').iterdir() if p.is_dir() and (p / 'SKILL.md').exists()} - directories):
        errors.append(f'unregistered Skill: {folder}')
    for folder in sorted({p.name for p in (root / 'workspaces').iterdir() if p.is_dir() and (p / 'workspace.yaml').is_file()} - templates):
        errors.append(f'unregistered workspace source: {folder}')
    if router_id not in ids: errors.append('unregistered Future2046 router')
    return errors


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True)
    try: errors = check(Path(ap.parse_args().root).resolve())
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc: errors = [str(exc)]
    if errors:
        print('FAIL'); [print('- ' + x) for x in errors]; return 1
    print('PASS: all registered Skills and templates'); return 0


if __name__ == '__main__': raise SystemExit(main())
