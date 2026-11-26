"""Unit tests with made-up files only (fake NPDM/NSO headers); no game or mod data. python -m unittest discover tests"""
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compass_to_pokinative as cc  # noqa: E402

VIOLET, SCARLET = 0x01008F6008C5E000, 0x0100A3D008C5C000


def npdm(tid):
    b = bytearray(0x100)
    b[:4] = b'META'
    struct.pack_into('<II', b, 0x70, 0x80, 0x40)
    b[0x80:0x84] = b'ACI0'
    struct.pack_into('<Q', b, 0x90, tid)
    return bytes(b)


def make_mod(base, tid=VIOLET, plugin=b'NSO0' + b'\0' * 60, version='v9.9.9'):
    (base / 'exefs').mkdir(parents=True)
    (base / 'romfs' / 'arc').mkdir(parents=True)
    (base / 'exefs' / 'main.npdm').write_bytes(npdm(tid))
    (base / 'exefs' / 'subsdk9').write_bytes(plugin)
    (base / 'romfs' / 'arc' / 'x.bin').write_bytes(b'x')
    (base / 'info.toml').write_text(f'display_name="Test Compass"\nversion="{version}"\n')
    return base


def make_install(base, tid=VIOLET):
    ex = base / 'game' / 'extracted' / 'update' / 'exefs'
    ex.mkdir(parents=True)
    (ex / 'main.npdm').write_bytes(npdm(tid))
    (ex / 'main').write_bytes(b'main')
    (base / 'game' / 'romfs').mkdir()
    (base / 'tools').mkdir()
    (base / 'tools' / 'mod_plugin.py').write_text('')
    (base / 'recomp').mkdir()
    (base / 'build' / 'game').mkdir(parents=True)
    (base / 'build' / 'game' / 'karpur.exe').write_bytes(b'MZ')
    return base


class Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.t = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()


class FindTests(Tmp):
    def test_mod_root_nested_atmosphere_layout(self):
        root = make_mod(self.t / 'dl' / 'atmosphere' / 'contents' / '01008F6008C5E000')
        self.assertEqual(cc.find_mod_root(self.t / 'dl'), root)

    def test_mod_root_missing(self):
        (self.t / 'empty').mkdir()
        with self.assertRaises(cc.ConvertError):
            cc.find_mod_root(self.t / 'empty')

    def test_two_mod_roots_is_an_error(self):
        make_mod(self.t / 'a' / 'one')
        make_mod(self.t / 'a' / 'two')
        with self.assertRaisesRegex(cc.ConvertError, 'more than one'):
            cc.find_mod_root(self.t / 'a')

    def test_install_from_parent_folder(self):
        inst = make_install(self.t / 'target' / 'KarPur')
        self.assertEqual(cc.find_install(self.t / 'target'), inst.resolve())

    def test_install_from_build_game(self):
        inst = make_install(self.t / 'KarPur')
        self.assertEqual(cc.find_install(inst / 'build' / 'game'), inst.resolve())

    def test_old_install_without_loader(self):
        base = self.t / 'old'
        (base / 'tools').mkdir(parents=True)
        (base / 'tools' / 'setup_build.py').write_text('')
        with self.assertRaisesRegex(cc.ConvertError, '0.4.6.3'):
            cc.find_install(base)


class CheckTests(Tmp):
    def test_version_from_info_toml(self):
        mod = make_mod(self.t / 'm', version='v2.0.0.0')
        self.assertEqual(cc.read_info(mod)['version'], 'v2.0.0.0')

    def test_version_from_folder_name(self):
        mod = make_mod(self.t / 'Pokemon_Compass_v3.1.0.0_VIOLET')
        (mod / 'info.toml').unlink()
        self.assertEqual(cc.read_info(mod)['version'], 'v3.1.0.0')

    def test_edition_mismatch(self):
        inst = cc.check_install(make_install(self.t / 'i', VIOLET))
        mod = make_mod(self.t / 'm', SCARLET)
        with self.assertRaisesRegex(cc.ConvertError, 'Scarlet'):
            cc.check_mod(mod, inst)

    def test_not_an_nso(self):
        inst = cc.check_install(make_install(self.t / 'i'))
        mod = make_mod(self.t / 'm', plugin=b'ZIP!')
        with self.assertRaisesRegex(cc.ConvertError, 'not an NSO'):
            cc.check_mod(mod, inst)

    def test_unknown_plugin_is_not_tested(self):
        inst = cc.check_install(make_install(self.t / 'i'))
        self.assertIsNone(cc.check_mod(make_mod(self.t / 'm'), inst)['tested'])

    def test_install_needs_built_game(self):
        inst = make_install(self.t / 'i')
        (inst / 'build' / 'game' / 'karpur.exe').unlink()
        with self.assertRaisesRegex(cc.ConvertError, 'launcher'):
            cc.check_install(inst)


class ZipTests(Tmp):
    def test_unpack_once(self):
        src = make_mod(self.t / 'src' / 'Pokemon_Compass_v1_VIOLET')
        z = self.t / 'Pokemon_Compass_v1_VIOLET.zip'
        with zipfile.ZipFile(z, 'w') as f:
            for p in src.rglob('*'):
                if p.is_file():
                    f.write(p, p.relative_to(src.parent))
        out = cc.unpack_zip(z, self.t / 'out')
        self.assertTrue((out / 'Pokemon_Compass_v1_VIOLET' / 'exefs' / 'subsdk9').is_file())
        (out / 'marker').write_text('kept')
        cc.unpack_zip(z, self.t / 'out')
        self.assertTrue((out / 'marker').is_file())

    def test_zip_slip_refused(self):
        z = self.t / 'bad.zip'
        with zipfile.ZipFile(z, 'w') as f:
            f.writestr('../evil.txt', 'x')
        with self.assertRaises(cc.ConvertError):
            cc.unpack_zip(z, self.t / 'out')


class ConvertTests(Tmp):
    def fake_mod_plugin(self, inst_root, mod):
        """What PokiNative's mod_plugin.py leaves behind, for verify()."""
        def run(inst, m, refresh, force):
            pack = inst_root / 'build' / 'game' / 'mods' / 'compass'
            (pack / 'romfs').mkdir(parents=True, exist_ok=True)
            (pack / 'romfs' / 'manifest.tsv').write_text('# overlay\narc/x.bin\t1\tab\t-\n')
            (pack / 'exefs').mkdir(exist_ok=True)
            (pack / 'exefs' / 'subsdk9').write_bytes((mod / 'exefs' / 'subsdk9').read_bytes())
            hooks = inst_root / 'build' / 'plugins' / 'compass' / 'hooks.txt'
            hooks.parent.mkdir(parents=True, exist_ok=True)
            hooks.write_text('set plugin_compass X 0\nsite plugin_compass main 10 0 @jump:subsdk9+0\n')
            (inst_root / 'build' / 'plugins.json').write_text(json.dumps(
                {'plugins': [{'mod': 'compass', 'module': 'subsdk9', 'hooks': 'build/plugins/compass/hooks.txt'}]}))
            self.calls.append(refresh)
        return run

    def test_full_run_retires_hand_port_and_stamps(self):
        inst = make_install(self.t / 'KarPur').resolve()
        mod = make_mod(self.t / 'Pokemon_Compass_v1_VIOLET').resolve()
        pack = inst / 'build' / 'game' / 'mods' / 'compass'
        pack.mkdir(parents=True)
        (pack / 'prelude.lua').write_text('-- old')
        (pack / 'patch-sets.txt').write_text('compass\n')
        self.calls = []
        with mock.patch.object(cc, 'run_mod_plugin', self.fake_mod_plugin(inst, mod)), \
                mock.patch.object(cc, 'make_shortcut', lambda *a: None):
            rc = cc.main(['--compass', str(mod), '--pokinative', str(inst)])
            self.assertEqual(rc, 0)
            self.assertTrue((pack / 'prelude.lua.off').is_file())
            self.assertFalse((pack / 'patch-sets.txt').exists())
            stamp = json.loads((pack / 'converter.json').read_text())
            self.assertEqual(stamp['compass_version'], 'v9.9.9')
            # a second run with the same download keeps the RomFS overlay
            self.assertEqual(cc.main(['--compass', str(mod), '--pokinative', str(inst)]), 0)
        self.assertEqual(self.calls, [True, False])

    def test_check_only_runs_nothing(self):
        inst = make_install(self.t / 'KarPur')
        mod = make_mod(self.t / 'm')
        with mock.patch.object(cc, 'run_mod_plugin', side_effect=AssertionError('ran')):
            self.assertEqual(cc.main(['--compass', str(mod), '--pokinative', str(inst), '--check']), 0)

    def test_verify_reports_missing_hooks(self):
        inst = cc.check_install(make_install(self.t / 'KarPur'))
        m = cc.check_mod(make_mod(self.t / 'm'), inst)
        with self.assertRaisesRegex(cc.ConvertError, 'incomplete'):
            cc.verify(inst, m)


if __name__ == '__main__':
    unittest.main()
