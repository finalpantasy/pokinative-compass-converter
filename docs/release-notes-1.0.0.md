# Compass Converter for PokiNative 1.0.0

This release turns your own download of Pokémon Compass for Violet into a PokiNative mod pack. Start it with `--mod compass`. The release contains no Compass files or code. The converter runs PokiNative's own mod tools on the copy you downloaded.

## What it does

- Finds the Compass files in a folder or a `.zip`, including the `atmosphere/contents/<title id>/` layout.
- Checks your PokiNative build (0.4.6.3 or newer, the first with the exefs plugin loader), the game version and that Compass matches your edition (Violet or Scarlet).
- Runs PokiNative's `tools/mod_plugin.py`, which builds the RomFS overlay, lifts the Compass plugin, captures its hooks and rebuilds the game.
- Checks the result: the overlay manifest, the plugin copy, and the plugin entry and its hooks in `build/plugins.json`.
- Renames an older hand-made `prelude.lua` and `patch-sets.txt` in `mods/compass` to `*.off`.
- Creates the shortcut `Pokémon Violet Compass (PokiNative)` that starts the game with `--mod compass`.
- Runs again in under a minute when nothing changed. It rebuilds the overlay when the Compass download changes.

## Download

`pokinative-compass-converter-1.0.0.zip`: unpack it, close PokiNative, double-click `Convert-Compass.cmd`.

## Tested

Lab runs on 2026-11-25, Windows 11, PokiNative upstream `testing` at `ecadc99`, Violet 4.0.0, Compass 2.1.1.1 Violet:

| Check | Result |
|---|---|
| Unit tests (17, made-up files only) | pass |
| `--check` against the real download and install | pass: Violet 4.0.0, Compass v2.1.1.1, known plugin build |
| Clean conversion, starting from a build with no plugin | pass, about 10 minutes: 2032 RomFS files, 6 hooks, 5 of 6 at function starts. The hook table matches a conversion made earlier by hand. |
| Second run, nothing changed | pass, 8 seconds: overlay kept, hooks cached, build checked |
| Boot with `--mod compass` on a Compass save | pass: the pack loads with its own `save-compass`, Compass's Lua scripts run without errors, the world loads |
| Plugin hooks that ran in game | 3 of 6 (the ones that run at start-up and when Lua scripts load) |
| Save | pass: the game saved to `save-compass` (4.2 MiB commit) |
| Compass's EXP rate and level cap in battle | **not checked in game**: the lab runs did not reach a battle that gives EXP |
| Compass's longer food effects | **not checked in game** |

The hooks for these two are in the rebuilt game and match the earlier conversion. No lab run has executed them yet.

## Known limits

- PokiNative's lift picks its worker count from free memory. On a busy PC it can stop with `MemoryError`. Close other large programs and run it again.
- Compass 2.1 needs a new game save. A save from the unmodded game stops with `error_fatal_save_01`.
- Run the converter again after you update PokiNative or Compass.

Compass is made by Aria Seri and Kas Seri ([compass.seri.studio](https://compass.seri.studio)). Report gameplay bugs to them and converter bugs here.
