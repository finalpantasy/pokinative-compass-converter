"""Compass Converter for PokiNative: turns your own download of the Pokemon Compass fan mod into a PokiNative mod pack.

    python compass_to_pokinative.py --compass "path/to/Pokemon_Compass_v2.1.1.1_VIOLET" --pokinative "path/to/PokiNative"

It ships no part of Compass. Everything happens on your PC with the files you downloaded:

  1. checks your PokiNative install (a build with the exefs plugin loader, PokiNative 0.4.6.3 or newer), the game
     version, and that the Compass download is for the edition you built;
  2. runs PokiNative's own tools/mod_plugin.py on it: the RomFS overlay (tools/mod_overlay.py), then the plugin
     (exefs/subsdkN) is lifted, its hooks are captured and the game is rebuilt with them;
  3. checks the result and makes a shortcut that starts the game with --mod compass.

Compass then runs as the mod pack "compass": start karpur.exe --mod compass. It keeps its own saves (save-compass in
your profile), so your normal Violet saves are left alone. Without --mod the game runs unchanged.

Only the Python standard library is used. Run it with the Python inside your PokiNative install (Convert-Compass.cmd
does that for you).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = '1.0.0'
PACK = 'compass'

# Title ids of the base games (from main.npdm).
TITLES = {0x01008F6008C5E000: 'Violet', 0x0100A3D008C5C000: 'Scarlet'}

# SHA-256 of the game's exefs/main for each update PokiNative supports. A hash, not game data.
KNOWN_MAIN = {
    'f05bd7fedaf6f0ba1481005cb48b1e43067966aa12c28e6932eab9e7bc5750a4': 'Violet 4.0.0',
}

# SHA-256 of Compass plugin builds that were converted and played in a lab run. Others still convert (PokiNative's
# hook check is the real version gate), with a warning.
TESTED_PLUGINS = {
    '4e6f913d2298f2057686d1e76e2d7b1880d82c5d79d9f4937df5ab641e396664': 'Compass v2.1.1.1 Violet (subsdk9)',
}

STAMP = 'converter.json'
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL = 0x00004000


class ConvertError(Exception):
    pass


def say(msg=''):
    print(msg, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def program_id(npdm):
    """The program id in an NPDM's ACI0 section."""
    b = Path(npdm).read_bytes()
    if b[:4] != b'META' or len(b) < 0x80:
        raise ConvertError(f'{npdm} is not an NPDM file')
    off, size = struct.unpack_from('<II', b, 0x70)
    if b[off:off + 4] != b'ACI0' or size < 0x18:
        raise ConvertError(f'{npdm} has no ACI0 section')
    return struct.unpack_from('<Q', b, off + 0x10)[0]


def title_name(tid):
    return TITLES.get(tid, f'title {tid:016x}')


# ---------------------------------------------------------------- PokiNative install

def find_install(path):
    """The PokiNative folder (the one with tools/mod_plugin.py). Accepts it, its parent (the launcher's target folder)
    or the build/game folder inside it."""
    path = Path(path).expanduser().resolve()
    if not path.is_dir():
        raise ConvertError(f'PokiNative folder not found: {path}')
    candidates = [path, *path.parents[:3]] + sorted(p for p in path.iterdir() if p.is_dir())
    for c in candidates:
        if (c / 'tools' / 'mod_plugin.py').is_file() and (c / 'recomp').is_dir():
            return c
    for c in candidates:
        if (c / 'tools' / 'setup_build.py').is_file():
            raise ConvertError(f'{c} is a PokiNative build without the exefs plugin loader (tools/mod_plugin.py). '
                               'Update PokiNative to 0.4.6.3 or newer in the launcher, then run this again.')
    raise ConvertError(f'{path} is not a PokiNative install (no tools/mod_plugin.py found here or one level down)')


def install_python(root):
    for p in (root / 'python' / 'python.exe', root / 'python' / 'bin' / 'python3'):
        if p.is_file():
            return p
    return Path(sys.executable)


def check_install(root):
    """Facts about the install; raises ConvertError when it cannot take the mod."""
    exefs = root / 'game' / 'extracted' / 'update' / 'exefs'
    exe = root / 'build' / 'game' / 'karpur.exe'
    if not (exefs / 'main.npdm').is_file() or not (exefs / 'main').is_file():
        raise ConvertError(f'{root} has no extracted game ({exefs}). Build the game in the PokiNative launcher first.')
    if not exe.is_file():
        raise ConvertError(f'{exe} is missing. Build the game in the PokiNative launcher first.')
    if not (root / 'game' / 'romfs').is_dir():
        raise ConvertError(f'{root / "game" / "romfs"} is missing. Build the game in the PokiNative launcher first.')
    tid = program_id(exefs / 'main.npdm')
    main_sha = sha256(exefs / 'main')
    return {'root': root, 'exefs': exefs, 'exe': exe, 'title': tid, 'main_sha': main_sha,
            'game': KNOWN_MAIN.get(main_sha)}


def exe_locked(exe):
    if not exe.is_file():
        return False
    try:
        with open(exe, 'r+b'):
            return False
    except PermissionError:
        return True


# ---------------------------------------------------------------- Compass download

def unpack_zip(zpath, dest_root):
    """Extracts a .zip download into dest_root/<zip name>, once per zip (keyed by its SHA-256)."""
    digest = sha256(zpath)
    dest = dest_root / re.sub(r'[^A-Za-z0-9._-]+', '_', zpath.stem)
    mark = dest / '.zip-sha256'
    if mark.is_file() and mark.read_text().strip() == digest:
        say(f'Using the files already unpacked from {zpath.name}: {dest}')
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    say(f'Unpacking {zpath.name} to {dest} ...')
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if dest.resolve() not in target.parents and target != dest.resolve():
                raise ConvertError(f'{zpath.name}: unsafe path in the archive: {info.filename}')
        z.extractall(dest)
    mark.write_text(digest + '\n')
    return dest


def find_mod_root(path, max_depth=6):
    """The folder holding exefs/ (with a subsdkN plugin and main.npdm) and romfs/. Searches the layouts mods ship in,
    e.g. the folder itself, Pokemon_Compass_x/, or atmosphere/contents/<title id>/."""
    path = Path(path)

    def is_root(p):
        ex = p / 'exefs'
        return ex.is_dir() and (ex / 'main.npdm').is_file() and any(
            re.fullmatch(r'subsdk[1-9]', c.name) for c in ex.iterdir())

    found = []
    stack = [(path, 0)]
    while stack:
        p, d = stack.pop()
        if is_root(p):
            found.append(p)
            continue
        if d < max_depth:
            try:
                stack.extend((c, d + 1) for c in p.iterdir() if c.is_dir())
            except OSError:
                pass
    if not found:
        raise ConvertError(f'no Compass files found in {path}: expected a folder with exefs/subsdk9, exefs/main.npdm '
                           'and romfs/. Point this at the folder you unpacked from the Compass download.')
    if len(found) > 1:
        raise ConvertError('more than one mod folder found; point at one of them:\n  ' +
                           '\n  '.join(str(f) for f in sorted(found)))
    return found[0]


def read_info(mod):
    """display_name and version from the mod's info.toml, if it has one (simple key="value" lines)."""
    info = {}
    f = mod / 'info.toml'
    if f.is_file():
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            m = re.match(r'\s*(display_name|version)\s*=\s*"([^"]*)"', line)
            if m:
                info[m.group(1)] = m.group(2)
    if 'version' not in info:
        m = re.search(r'v?(\d+(?:\.\d+){1,3})', mod.name)
        if m:
            info['version'] = 'v' + m.group(1)
    return info


def check_mod(mod, inst):
    ex = mod / 'exefs'
    plugins = sorted(c for c in ex.iterdir() if re.fullmatch(r'subsdk[1-9]', c.name))
    if len(plugins) != 1:
        raise ConvertError(f'{ex} has {len(plugins)} plugins; expected one subsdkN')
    plugin = plugins[0]
    if plugin.read_bytes()[:4] != b'NSO0':
        raise ConvertError(f'{plugin} is not an NSO file; the download may be damaged')
    for game_module in ('main', 'sdk', 'subsdk0', 'rtld'):
        if (ex / game_module).exists():
            raise ConvertError(f'{ex} replaces the game module {game_module}; that is not a Compass download')
    tid = program_id(ex / 'main.npdm')
    if tid != inst['title']:
        raise ConvertError(f'this Compass download is for {title_name(tid)}, your PokiNative build is '
                           f'{title_name(inst["title"])}. Download the {title_name(inst["title"])} edition of Compass.')
    if not (mod / 'romfs').is_dir():
        raise ConvertError(f'{mod} has no romfs folder; the download is incomplete')
    info = read_info(mod)
    digest = sha256(plugin)
    return {'root': mod, 'plugin': plugin, 'plugin_sha': digest, 'title': tid, 'info': info,
            'tested': TESTED_PLUGINS.get(digest)}


# ---------------------------------------------------------------- conversion

def pack_dir(inst):
    return inst['root'] / 'build' / 'game' / 'mods' / PACK


def retire_hand_port(inst):
    """An older hand-made Compass setup put prelude.lua and patch-sets.txt (naming a code patch set "compass") into
    the pack. With the plugin running natively they would run the same hooks twice, so they are set aside."""
    moved = []
    for name in ('prelude.lua', 'patch-sets.txt'):
        f = pack_dir(inst) / name
        if f.is_file():
            dst = f.with_name(name + '.off')
            if dst.exists():
                dst.unlink()
            f.rename(dst)
            moved.append(dst)
    return moved


def old_stamp(inst):
    try:
        return json.loads((pack_dir(inst) / STAMP).read_text())
    except (OSError, ValueError):
        return {}


def run_mod_plugin(inst, mod, refresh, force):
    root = inst['root']
    cmd = [str(install_python(root)), '-u', str(root / 'tools' / 'mod_plugin.py'), str(mod['root']), '--name', PACK]
    if refresh:
        cmd.append('--romfs-refresh')
    if force:
        cmd.append('--force')
    say('> ' + ' '.join(f'"{c}"' if ' ' in c else c for c in cmd))
    kw = {'creationflags': BELOW_NORMAL} if os.name == 'nt' else {}
    r = subprocess.run(cmd, cwd=root, **kw)
    if r.returncode:
        raise ConvertError(f'PokiNative\'s mod_plugin.py stopped (exit code {r.returncode}); its message is above')


def verify(inst, mod):
    """Checks the pack and the plugin entry that mod_plugin.py wrote. Returns a short summary."""
    root = inst['root']
    pack = pack_dir(inst)
    problems = []
    manifest = pack / 'romfs' / 'manifest.tsv'
    files = 0
    if manifest.is_file():
        files = sum(1 for ln in manifest.read_text(encoding='utf-8', errors='replace').splitlines()
                    if ln and not ln.startswith('#'))
    else:
        problems.append(f'no RomFS overlay ({manifest})')
    nso = pack / 'exefs' / mod['plugin'].name
    if not nso.is_file() or sha256(nso) != mod['plugin_sha']:
        problems.append(f'the plugin copy {nso} is missing or differs from the download')
    try:
        entries = json.loads((root / 'build' / 'plugins.json').read_text()).get('plugins', [])
    except (OSError, ValueError):
        entries = []
    entry = next((e for e in entries if e.get('mod') == PACK), None)
    sites = 0
    if not entry:
        problems.append('no "compass" entry in build/plugins.json')
    elif not entry.get('hooks'):
        problems.append('the plugin entry has no hooks (the hook step did not finish)')
    else:
        hooks = Path(entry['hooks'])
        hooks = hooks if hooks.is_absolute() else root / hooks
        if hooks.is_file():
            sites = sum(1 for ln in hooks.read_text().splitlines() if ln.startswith('site '))
        if not sites:
            problems.append(f'no hooked sites in {hooks}')
    for name in ('prelude.lua', 'patch-sets.txt'):
        if (pack / name).exists():
            problems.append(f'{pack / name} is still there (hand-port leftover)')
    if problems:
        raise ConvertError('the conversion is incomplete:\n  ' + '\n  '.join(problems))
    return {'romfs_files': files, 'hook_sites': sites}


def make_shortcut(inst, edition):
    """Pokemon <edition> Compass (PokiNative).lnk next to the launcher's own shortcut (the install's parent folder)."""
    if os.name != 'nt':
        return None
    root = inst['root']
    exe = inst['exe']
    lnk = root.parent / f'Pokémon {edition} Compass (PokiNative).lnk'
    ps = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CC_LNK); '
          '$s.TargetPath = $env:CC_EXE; $s.Arguments = "--mod compass"; $s.WorkingDirectory = $env:CC_DIR; '
          '$s.IconLocation = $env:CC_EXE + ",0"; $s.Description = "Pokemon Compass in PokiNative"; $s.Save()')
    env = dict(os.environ, CC_LNK=str(lnk), CC_EXE=str(exe), CC_DIR=str(root))
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], env=env,
                       capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    return lnk if r.returncode == 0 and lnk.is_file() else None


def convert(a):
    inst = check_install(find_install(a.pokinative))
    edition = TITLES.get(inst['title'], 'Violet')
    say(f'PokiNative: {inst["root"]}')
    say(f'  game: {title_name(inst["title"])}, ' +
        (inst['game'] if inst['game'] else f'unknown update (main {inst["main_sha"][:12]}...)'))
    if not inst['game']:
        say('  warning: this game version was not tested with the converter. PokiNative supports update 4.0.0.')

    src = Path(a.compass).expanduser().resolve()
    if src.is_file() and src.suffix.lower() == '.zip':
        src = unpack_zip(src, inst['root'] / 'build' / 'compass-download')
    elif src.is_file():
        raise ConvertError(f'{src.name}: unpack it first (this tool reads a folder or a .zip)')
    elif not src.is_dir():
        raise ConvertError(f'Compass download not found: {src}')
    mod = check_mod(find_mod_root(src), inst)
    info = mod['info']
    say(f'Compass: {mod["root"]}')
    say(f'  {info.get("display_name", "mod")} {info.get("version", "(no version)")}, {title_name(mod["title"])}, '
        f'plugin {mod["plugin"].name} {mod["plugin_sha"][:12]}...')
    if 'compass' not in info.get('display_name', '').lower() and 'compass' not in mod['root'].name.lower():
        say('  warning: this does not look like Pokemon Compass; it converts any single-plugin mod the same way.')
    if mod['tested']:
        say(f'  tested build: {mod["tested"]}')
    else:
        say('  warning: this Compass build was not tested with the converter yet. PokiNative stops at the hook step if')
        say('  the plugin was made for another game version.')
    if a.check:
        say('Check passed. Run without --check to convert.')
        return 0

    if exe_locked(inst['exe']):
        raise ConvertError('the game is running. Close PokiNative and run this again.')

    moved = retire_hand_port(inst)
    for f in moved:
        say(f'Set aside an older hand-made setup file: {f}')

    stamp = old_stamp(inst)
    refresh = a.refresh or stamp.get('plugin_sha') != mod['plugin_sha'] or stamp.get('mod_root') != str(mod['root'])
    say()
    say('Converting. PokiNative lifts the plugin, captures its hooks, then lifts the game again with them.')
    say('This takes 10-45 minutes and keeps the PC busy (it runs at low priority).')
    say()
    run_mod_plugin(inst, mod, refresh, a.force)

    result = verify(inst, mod)
    (pack_dir(inst) / STAMP).write_text(json.dumps({
        'converter': VERSION, 'compass_version': info.get('version'), 'plugin_sha': mod['plugin_sha'],
        'mod_root': str(mod['root']), 'main_sha': inst['main_sha']}, indent=1) + '\n')
    lnk = None if a.no_shortcut else make_shortcut(inst, edition)
    say()
    say(f'Done: Compass {info.get("version", "")} is the mod pack "compass" '
        f'({result["romfs_files"]} RomFS files, {result["hook_sites"]} plugin hooks).')
    if lnk:
        say(f'Start it with the shortcut {lnk}')
        say(f'or run: "{inst["exe"]}" --mod compass')
    else:
        say(f'Start it with: "{inst["exe"]}" --mod compass')
    say('Compass keeps its own saves (save-compass in your profile). Compass 2.1 needs a new game save.')
    say('After a PokiNative or Compass update, run this converter again.')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='compass_to_pokinative',
                                 description='Convert your own Pokemon Compass download into a PokiNative mod pack.')
    ap.add_argument('--compass', required=True, help='the unpacked Compass download (folder) or its .zip')
    ap.add_argument('--pokinative', required=True, help='your PokiNative folder (the launcher\'s target folder works)')
    ap.add_argument('--check', action='store_true', help='only check the files, convert nothing')
    ap.add_argument('--refresh', action='store_true', help='make the RomFS overlay again')
    ap.add_argument('--force', action='store_true', help='capture the hooks and lift again even when cached')
    ap.add_argument('--no-shortcut', action='store_true', help='do not create the desktop-style shortcut')
    ap.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')
    a = ap.parse_args(argv)
    try:
        return convert(a)
    except ConvertError as e:
        say(f'\nStopped: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
