# Compass Converter for PokiNative

Play the **Pokémon Compass** fan mod for Pokémon Violet in **PokiNative**, the native PC recompilation of Violet. This tool takes the Compass download you got yourself and sets it up as a PokiNative mod pack on your own PC. You then start the game with `--mod compass`.

![A Compass save loaded in PokiNative with --mod compass (lab run, 4K, scaled down)](docs/screenshots/compass-world.jpg)

This repository contains no part of Compass: no files, no code and nothing decoded from it. You download Compass from its authors, and the converter reformats your copy locally. The mod stays theirs. Compass is made by Aria Seri and Kas Seri: [compass.seri.studio](https://compass.seri.studio). Report Compass gameplay bugs to them and converter bugs here.

## What you need

- **PokiNative 0.4.6.3 or newer**, built with its launcher from your own Violet game and update 4.0.0. The converter relies on PokiNative's exefs plugin loader, which first shipped in 0.4.6.3.
- **Pokémon Compass for Violet**, downloaded from [compass.seri.studio](https://compass.seri.studio) and unpacked. Version 2.1.1.1 has been tested. Other versions should convert too (see [Versions](#versions)).
- About 1 GB free disk space and 10 to 45 minutes. The conversion recompiles the game once (about 10 minutes on a 32-thread PC).

## Use

1. Download `pokinative-compass-converter-1.0.0.zip` from [Releases](../../releases) and unpack it anywhere.
2. Close PokiNative if it is running.
3. Double-click **`Convert-Compass.cmd`**. It asks for two folders:
   - your **PokiNative folder** (the target folder you chose in the PokiNative launcher);
   - your **Compass folder** (the one with `exefs`, `romfs` and `info.toml` in it). A `.zip` works too.
4. Wait until it prints `Done`. It creates the shortcut **Pokémon Violet Compass (PokiNative)** next to the launcher's own shortcut.
5. Start the game with that shortcut, or run `build\game\karpur.exe --mod compass` in your PokiNative folder.

The end of a real conversion (lab run, paths shortened):

```
plugin_hooks: 6 sites (6 hooks, 0 plain words), 18 code words, 21 entries; 5 of 6 branch hooks at main function starts
done: karpur.exe --mod compass

Done: Compass v2.1.1.1 is the mod pack "compass" (2032 RomFS files, 6 plugin hooks).
Start it with the shortcut ...\Pokémon Violet Compass (PokiNative).lnk
```

From a terminal, the same thing:

```
<PokiNative folder>\python\python.exe compass_to_pokinative.py --compass "D:\Downloads\Pokemon_Compass_v2.1.1.1_VIOLET" --pokinative "D:\Games\PokiNative"
```

`--check` only checks the two folders and changes nothing. `--refresh` rebuilds the RomFS overlay, `--force` captures the plugin's hooks again and `--no-shortcut` skips the shortcut.

## Saves

The Compass pack keeps its own saves in `save-compass` inside your PokiNative profile. Your normal Violet saves are not touched, and without `--mod compass` the game runs unmodded. Compass 2.1 needs a **new game**: a save from the unmodded game will not load with Compass.

## How it works

The converter is a front end for tools that PokiNative already ships:

1. It checks your PokiNative build, the game version (Violet update 4.0.0) and that your Compass download is for the same edition.
2. It runs PokiNative's `tools/mod_plugin.py` on your Compass folder:
   - `tools/mod_overlay.py` turns Compass's `romfs` folder into an overlay under `build\game\mods\compass\romfs`. The game reads those files in place of its own as it loads them.
   - Compass's code plugin (`exefs/subsdk9`) is Switch code. PokiNative lifts it to C like the game itself, runs the game once to record where the plugin hooks into the game, and rebuilds the game with those hooks. Compass's own code then runs as written.
3. It checks the result and writes the shortcut.

Everything made from your Compass files stays in your PokiNative folder (`build\` and `generated\`). An older hand-made setup that put `prelude.lua` or `patch-sets.txt` into `mods\compass` is renamed to `*.off`, because those would apply the same changes twice.

## Versions

The converter knows two hashes: Violet 4.0.0's `main` and Compass 2.1.1.1's plugin. Other versions get a warning but still convert. PokiNative stops at the hook step when the plugin's hooks do not land on function starts in your game, which happens when the plugin was built for another game version.

Run the converter again after you update Compass or PokiNative.

## Troubleshooting

- **"the game is running"**: close PokiNative and run it again.
- **"a PokiNative build without the exefs plugin loader"**: update PokiNative in its launcher (Repair), then run it again.
- **The game closes with `error_fatal_save_01`** right after loading: that save was not made with Compass. Start a new game.
- **`MemoryError` while it lifts the game**: close other large programs and run it again. Finished steps are skipped.

## Tested

Release 1.0.0 was tested in automated lab runs. We started with a clean PokiNative build (upstream `testing`, no plugin), converted Compass 2.1.1.1 with this tool, booted with `--mod compass`, loaded a Compass save, reached the world, checked that the game saved to `save-compass`, and checked Compass's EXP rate and level cap in wild battles. Compass's longer food effects were not checked in game. The [release notes](docs/release-notes-1.0.0.md) list what was checked and what was not.

## License

MIT for the converter (this repository). Pokémon Compass belongs to its authors and is not included. PokiNative is MIT-licensed and is not included either. Pokémon is a trademark of Nintendo, Creatures and Game Freak. This project is not affiliated with them, with the Compass team or with the PokiNative project.
