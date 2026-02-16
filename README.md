# HumanitZ Save Editor

A Python toolkit for reading, analyzing, and editing HumanitZ dedicated server save files.
Built through reverse-engineering the UE4 4.27 GVAS save format and the encrypted Pak v11 archive.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [File Overview](#file-overview)
- [Scripts](#scripts)
  - [read_save.py — Save Analyzer](#read_savepy--save-analyzer)
  - [edit_profession.py — Profession Changer](#edit_professionpy--profession-changer)
  - [scan_properties.py — Generic Property Scanner](#scan_propertiespy--generic-property-scanner)
  - [pak_reader.py — Pak File Reader/Extractor](#pak_readerpy--pak-file-readerextractor)
  - [extract_enums.py — Enum Extractor](#extract_enumspy--enum-extractor)
- [Configuration](#configuration)
- [Profession Enum Map](#profession-enum-map)
- [Technical Reference](#technical-reference)
  - [Save File Format (GVAS)](#save-file-format-gvas)
  - [Save File Structure (HumanitZ)](#save-file-structure-humanitz)
  - [Pak File Format (v11)](#pak-file-format-v11)
  - [AES Encryption](#aes-encryption)
- [Save File Locations](#save-file-locations)
- [Map Exploration / Fog of War](#map-exploration--fog-of-war)
- [How Profession Editing Works](#how-profession-editing-works)
- [Known Player Data](#known-player-data)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```powershell
# 1. Install the only dependency
pip install pycryptodome

# 2. Analyze a save file
python read_save.py "path\to\Save_MAZADedicatedSave1.sav"

# 3. Change a player's profession
python edit_profession.py "path\to\Save_MAZADedicatedSave1.sav"
```

---

## Requirements

- **Python 3.10+** (tested with 3.13)
- **pycryptodome** — for AES-256-ECB decryption of the pak index
  ```
  pip install pycryptodome
  ```
- No other dependencies required. All scripts use the Python standard library plus pycryptodome.

---

## File Overview

```
HumanitZ_SaveEditor/
├── config.py            # Paths, AES key, profession enum map, player list
├── utils.py             # Core utilities: GVAS parser, AES, binary search
├── read_save.py         # Analyze a save file (read-only)
├── edit_profession.py   # Interactive profession editor
├── scan_properties.py   # Generic property/string scanner
├── pak_reader.py        # Pak file index reader and file extractor
├── extract_enums.py     # Extract Enum_Professions from pak, parse mapping
└── README.md            # This file
```

---

## Scripts

### `read_save.py` — Save Analyzer

Reads a HumanitZ save file and produces a detailed report including GVAS header info,
player SteamID presence, all profession entries with player attribution, and a summary.

```powershell
# Using default save path (from config.py)
python read_save.py

# Specify a save file
python read_save.py "C:\path\to\save.sav"
```

**Output includes:**
- File size, GVAS magic, engine version, save class
- Which players (by SteamID) are present in the save
- Every profession entry found, tagged with:
  - Which player it belongs to (nearest SteamID match)
  - Whether it's the active profession (`StartingPerk`) or unlocked (`UnlockedProfessionArr`)
  - The display name and NewEnumerator number
  - The byte offset for manual editing
- A reference table of all 17 professions

---

### `edit_profession.py` — Profession Changer

Interactive tool to change a player's profession in the save file.

```powershell
python edit_profession.py "C:\path\to\save.sav"
```

**Features:**
- Scans the save and displays all profession entries with player names
- Lets you select an entry by number
- Shows available professions (0–16)
- Indicates whether a swap is "safe" (same string length) or requires length adjustment
- **Always creates a timestamped backup** before modifying (e.g., `save.sav.backup_20260216_143022`)
- After editing, re-scans and displays updated entries
- Supports multiple edits in one session

**Safety levels:**
| Swap Type | Safety | Example |
|-----------|--------|---------|
| Same digit count (0↔9 or 10↔16) | ✅ SAFE — identical byte lengths | NE14 → NE13 |
| Cross digit count (0-9 ↔ 10-16) | ⚠️ CAUTION — length prefix updated, file size changes by 1 byte | NE3 → NE14 |

---

### `scan_properties.py` — Generic Property Scanner

A general-purpose tool for searching save files for any string, counting UE4 property types,
viewing GVAS headers, or doing hex dumps at specific offsets.

```powershell
# Show GVAS header
python scan_properties.py --header

# Count all UE4 property types
python scan_properties.py --properties

# Search for a string (shows context around each match)
python scan_properties.py --search Health
python scan_properties.py --search SkillPoints
python scan_properties.py --search Season

# Hex dump at a specific offset
python scan_properties.py --hex 0x007B3200

# Use a different save file
python scan_properties.py "C:\path\to\save.sav" --search Stamina
```

---

### `pak_reader.py` — Pak File Reader/Extractor

Reads the encrypted UE4 Pak v11 index from HumanitZ's main pak file, decrypts it,
and can list, search, or extract files.

```powershell
# Show pak file info
python pak_reader.py --info

# List all files in the pak (~103,000)
python pak_reader.py --list

# Search for files by regex pattern
python pak_reader.py --search "Enum_Professions"
python pak_reader.py --search "DT_Professions"
python pak_reader.py --search "SkillSystem"

# Extract matching files to a directory
python pak_reader.py --extract "Enum_Professions" --output ./extracted
```

**Limitations:**
- Only extracts uncompressed files (the HumanitZ pak has no compression methods registered,
  so most files are uncompressed)
- Files with `flags & 0x3F == 0x3F` in the encoded entry use a "full entry" format that
  sometimes produces invalid offsets (known issue with certain encrypted entries)
- Files that ARE individually encrypted in the pak are AES-decrypted automatically

---

### `extract_enums.py` — Enum Extractor

Specialized script to extract `Enum_Professions.uexp` from the pak and parse its display
name mapping. Run this after a game update to check if new professions were added.

```powershell
python extract_enums.py --output ./extracted
```

**Output:**
- The extracted `.uexp` binary file
- A formatted table of all NewEnumeratorN → Display Name mappings
- A ready-to-paste Python dict for updating `config.py`

---

## Configuration

Edit `config.py` to match your environment:

```python
# Path to the dedicated server save file
DEFAULT_SAVE_FILE = r'c:\Users\p0ffer\Desktop\SaveGames\SaveList\Default\Save_MAZADedicatedSave1.sav'

# HumanitZ installation directory
GAME_DIR = r'e:\Steam\steamapps\common\HumanitZ'

# Known players on your server (SteamID64 -> display name)
PLAYERS = {
    '76561198142478391': '0xAnakin',
    '76561198108344973': 'raybanme',
    '76561198144568733': 'Johnny Kopo',
}
```

To add new players, find their SteamID64 from:
- The `PlayerIDMapped.txt` file (format: `SteamID64_+_|GUID@DisplayName`)
- SteamID finder websites
- In-game admin tools

---

## Profession Enum Map

Extracted from `HumanitZ/Content/Coredamage/Data/Enum_Professions.uasset/.uexp`:

| # | Enum Value | Internal Name | Game Display Name |
|---|-----------|---------------|-------------------|
| 0 | `NewEnumerator0` | Unemployed | Unemployed |
| 1 | `NewEnumerator1` | AmateurBoxer | Amateur Boxer |
| 2 | `NewEnumerator2` | Farmer | Farmer |
| 3 | `NewEnumerator3` | Mechanic | Mechanic |
| 4 | `NewEnumerator4` | JuniorBiodiesel Researcher | Junior Biodiesel Researcher |
| 5 | `NewEnumerator5` | EmergencyMedicalTechnician | Emergency Medical Technician |
| 6 | `NewEnumerator6` | ApprenticeGunsmith | Apprentice Gunsmith |
| 7 | `NewEnumerator7` | FoodServiceWorker | Food Service Worker |
| 8 | `NewEnumerator8` | SundayFisherman | Sunday Fisherman |
| 9 | `NewEnumerator9` | CarSalesman | Car Salesman |
| 10 | `NewEnumerator10` | Outdoorsman | Outdoorsman |
| 11 | `NewEnumerator11` | Chemist | Chemist |
| 12 | `NewEnumerator12` | EMT | EMT |
| 13 | `NewEnumerator13` | MilitaryVet | Military Veteran |
| 14 | `NewEnumerator14` | Thief | Thief |
| 15 | `NewEnumerator15` | FireFighter | Firefighter |
| 16 | `NewEnumerator16` | ElectricalEngineer | Electrical Engineer |

**Note:** Professions 4–8 and 12 (JuniorBiodiesel Researcher, EmergencyMedicalTechnician,
ApprenticeGunsmith, FoodServiceWorker, SundayFisherman, EMT) are newer additions not in
the original Steam community guide.

---

## Technical Reference

### Save File Format (GVAS)

HumanitZ saves use UE4's GVAS (Generic Versioned Archive Serializer) format.

**Header layout:**

| Offset | Type | Field |
|--------|------|-------|
| 0x00 | uint32 | Magic (`0x53415647` = "GVAS") |
| 0x04 | uint32 | Save Game Version (2) |
| 0x08 | uint32 | Package File Version (522) |
| 0x0C | uint16 | Engine Major Version |
| 0x0E | uint16 | Engine Minor Version |
| 0x10 | uint16 | Engine Patch Version |
| 0x12 | uint32 | Engine Changelist |
| 0x16 | FString | Engine Branch (`++UE4+Release-4.27`) |
| var  | int32 | Custom Version Format (3 = Guids) |
| var  | int32 | Custom Version Count (54 in this game) |
| var  | CustomVersion[] | Array of (GUID[16] + int32 version) |
| var  | FString | Save Game Class Path |

**After the header**, the data section contains serialized UE4 properties in a flat
key-value format. Each property has:
1. **FString Name** — Property name (e.g., `StartingPerk_94_283EA71B427B7E97C43350818608A5E4`)
2. **FString Type** — Property type (e.g., `ByteProperty`, `ArrayProperty`, `StructProperty`)
3. **int64 Size** — Size of the value data
4. Various type-specific fields and the value itself

Properties are nested inside `StructProperty` and `ArrayProperty` containers.

**FString encoding:**
- `int32 length` (including null terminator; negative = UTF-16)
- `char[length]` (data + null byte)

### Save File Structure (HumanitZ)

The main dedicated server save (`Save_MAZADedicatedSave1.sav`) contains:

```
BP_HumanitzSave_C
├── (world state data...)
├── DropInSaves (ArrayProperty of StructProperty "ST_SaveDropIn")
│   ├── Player 0
│   │   ├── SteamID_67_6AFAA3B54A4447673EFF4D94BA0F84A7 (StrProperty)
│   │   ├── StartingPerk_94_283EA71B427B7E97C43350818608A5E4 (ByteProperty)
│   │   │   └── Enum type: Enum_Professions
│   │   │   └── Value: "Enum_Professions::NewEnumeratorN"
│   │   ├── UnlockedProfessionArr_17_2528BAE945B7A3B1A49D7893990D13BF (ArrayProperty)
│   │   │   └── Array of ByteProperty (Enum_Professions values)
│   │   ├── (health, inventory, skills, position, etc.)
│   │   └── ...
│   ├── Player 1
│   │   └── (same structure)
│   └── ...
└── (more world data...)
```

**Key property names:**
- `StartingPerk_94_*` — The player's active/chosen profession (ByteProperty, Enum_Professions)
- `UnlockedProfessionArr_17_*` — Professions unlocked during gameplay (ArrayProperty)
- `SteamID_67_*` — Player's Steam ID string (StrProperty)

### Pak File Format (v11)

HumanitZ uses UE4 Pak version 11 (introduced in UE4 4.26+).

**Footer/Info block** (read from `file_size - 204`):

| Field | Type | Description |
|-------|------|-------------|
| Magic | uint32 | `0x5A6F12E1` |
| Version | uint32 | 11 |
| IndexOffset | uint64 | Byte offset to encrypted index |
| IndexSize | uint64 | Size of encrypted index in bytes |
| IndexHash | byte[20] | SHA-1 hash of decrypted index |
| bEncryptedIndex | bool | Whether the index is AES encrypted |
| EncryptionKeyGuid | byte[16] | GUID for encryption key identification |
| CompressionMethodCount | uint32 | Number of compression methods |
| CompressionMethods | char[32][] | Compression method names (empty for HumanitZ) |

**Decrypted primary index layout:**

1. **FString MountPoint** — `../../../`
2. **int32 NumEntries** — Total file count (102,964 for current build)
3. **uint64 PathHashSeed**
4. **PathHashIndex** (optional): `int32 bHasIt`, if 1: `int64 Offset`, `int64 Size`, `byte[20] Hash`
5. **FullDirectoryIndex** (optional): `int32 bHasIt`, if 1: `int64 Offset`, `int64 Size`, `byte[20] Hash`
   - **Important**: The offset/size point to a SEPARATE encrypted block in the pak file, not inline data
6. **int32 EncodedEntriesSize**
7. **byte[] EncodedEntries** — Compact bitpacked file metadata

**FullDirectoryIndex** (separate encrypted block at the offset above):
```
int32 DirCount
For each directory:
  FString DirName
  int32 FileCount
  For each file:
    FString FileName
    int32 EncodedEntryOffset
```

**Encoded entry format (compact):**

The `uint32 flags` word:
- Bits 0–5: CompressionMethodIndex (0x3F = full/unencoded entry follows)
- Bit 6: bEncrypted (per-file encryption)
- Bits 7–17: CompressionBlockCount (11 bits)
- Bit 29: 1 if Size fits in uint32 (else int64)
- Bit 30: 1 if UncompressedSize fits in uint32 (else int64)
- Bit 31: 1 if Offset fits in uint32 (else int64)

After flags:
1. Offset (uint32 or int64)
2. UncompressedSize (uint32 or int64)
3. Size (uint32 or int64) — **only if compressed (CompMethod ≠ 0)**
4. BlockSize (uint32) — only if has compression blocks
5. Block pairs — (start, end) for each compression block

### AES Encryption

- **Algorithm:** AES-256-ECB
- **Key (hex):** `321166CACD1E2BBEAC9794AAF468DE277001D2EF8F74A8D6B3CC6EDFE87945CA`
- **Source:** [HumanitZ Unofficial Modding Guide](https://steamcommunity.com/sharedfiles/filedetails/?id=3035793498) on Steam
- **Used for:**
  - Decrypting the pak index (required to list/find files)
  - Decrypting individually encrypted files within the pak
- **Not used for:** Save files (`.sav`) — these are stored unencrypted

---

## Save File Locations

### Dedicated Server Saves

Default location (configurable in server settings):
```
<ServerRoot>\HumanitZ\Saved\SaveGames\
├── DedSave_ResGlobal.sav        # Global resource/settings (1.2 KB)
├── Save_ClanData.sav            # Clan data (3.1 KB)
├── SaveList\
│   ├── SaveCache.sav            # Save metadata cache (2 KB)
│   └── Default\
│       ├── Save_<Name>.sav      # Main save with player data (36+ MB)
│       └── <Name>_Foliage.sav   # Foliage state (65 KB)
```

### Local (Single Player / Client) Saves

```
C:\Users\<user>\AppData\Local\HumanitZ\Saved\
├── Minimap\
│   ├── Minimap_<SaveID>.exr      # Fog-of-war texture per save (EXR image)
│   └── steam_autocloud.vdf
├── SaveGames\
│   ├── Minimap_<SaveID>.sav      # POI markers (root-level copy)
│   ├── SavedSettings.sav         # Client settings
│   ├── Minimap\
│   │   ├── Minimap_<SaveID>.sav  # POI markers per save (GVAS, BP_POISave_C)
│   │   └── steam_autocloud.vdf
│   └── SaveList\
│       └── Default\
│           ├── Save_<Name>.sav          # Single player save
│           ├── <Name>_CharPreview.sav   # Character preview
│           └── <Name>_Foliage.sav       # Foliage state
```

**Note:** The `_CharPreview.sav` stores the profession as a human-readable `StrProperty`
(e.g., `"Unemployed"`) rather than the enum format, which was useful for confirming
the enum mapping.

---

## Map Exploration / Fog of War

HumanitZ uses the **MinimapPlugin** (UE4 Marketplace) with a custom `KaiMinimapMap` system
for the in-game map and fog-of-war.

### How It Works

- The fog-of-war is rendered to a **render target texture** at runtime
- As the player explores, the fog texture is updated (revealed areas become transparent)
- The texture is periodically saved as an **EXR image file** on the **client's machine**
- Map POI (Point of Interest) markers are saved as GVAS `.sav` files

### Key Files

| File | Location | Purpose |
|------|----------|---------|
| `Minimap_<SaveID>.exr` | `%LOCALAPPDATA%\HumanitZ\Saved\Minimap\` | Fog-of-war texture (EXR image) |
| `Minimap_<SaveID>.sav` | `%LOCALAPPDATA%\HumanitZ\Saved\SaveGames\Minimap\` | Map POI markers (GVAS, `BP_POISave_C`) |

- The `<SaveID>` is a UE4 GUID that identifies the specific save/world
- Larger `.exr` files = more map explored (e.g., 620KB = heavily explored, 20KB = barely started)
- The `.sav` POI files contain an `ArrayProperty` of `StructProperty` entries (one per map marker)

### Can the Map Be Revealed via Save Editing?

**The fog-of-war is stored CLIENT-SIDE, not on the dedicated server.** The server save
(`Save_MAZADedicatedSave1.sav`) contains zero fog/map exploration data.

To reveal the map for a specific player, you would need to modify the `.exr` file on
**that player's local machine**:

```
C:\Users\<user>\AppData\Local\HumanitZ\Saved\Minimap\Minimap_<SaveID>.exr
```

Replacing this with a fully-white EXR image (white = revealed) would uncover the entire map.
This cannot be done server-side.

### Game Assets (from Pak)

The minimap system assets are located at:
- `Engine/Plugins/Marketplace/MinimapPlugin/` — Base plugin (materials, fog shaders, revealers)
- `HumanitZ/Content/TSS_Game/KaiWorldEffects/KaiMinimapMap/` — Custom implementation:
  - `BP_KaiMinimap` / `BP_KaiMinimapMain` / `BP_KaiMinimapComp` — Core minimap Blueprints
  - `BP_MinimapGrid` — Grid system
  - `BP_MinimapPOI` / `BP_POISave` / `BP_POIButton` — POI system
  - `BP_SatNav` — In-game GPS item integration
  - `M_KaiFog` / `M_KaiFogFull` — Fog-of-war materials
  - `RT_KaiMinimap_Tex` — Render target texture
  - `HZ_FullMap_4Kisland_FINAL` — The full 4K map image

---

## How Profession Editing Works

The profession is stored in the save as a `ByteProperty` with the enum type `Enum_Professions`.
The value is a null-terminated FString like `Enum_Professions::NewEnumerator14`.

**To read:**
1. Search the binary save data for `Enum_Professions::NewEnumerator`
2. Read the full null-terminated string to get the number
3. Look up the number in the profession map

**To edit:**
1. The FString has a 4-byte int32 length prefix immediately before the string data
2. For same-length swaps (e.g., NE14 → NE13): just overwrite the string bytes
3. For different-length swaps (e.g., NE3 → NE14):
   - Update the length prefix (int32 at offset - 4)
   - Replace the string bytes (old length → new length)
   - File size changes by the length difference

**Player attribution:**
- Each profession entry is inside a `ST_SaveDropIn` struct within the `DropInSaves` array
- The same struct contains the player's `SteamID` property
- We find the nearest SteamID occurrence to identify which player owns each profession entry

---

## Known Player Data

From `PlayerIDMapped.txt`:

| Player | SteamID64 | GUID |
|--------|-----------|------|
| 0xAnakin | 76561198142478391 | 00028ce6-e7d5-4af2-968d-8aff2e694375 |
| raybanme | 76561198108344973 | 0002462c-ecc1-4620-a256-442159aac2fe |
| Johnny Kopo | 76561198144568733 | 0002e1af-75a4-491c-ae70-b32049427e21 |

**Last analyzed (from server save):**
- **0xAnakin:** Active profession = **Thief** (NewEnumerator14)
- **raybanme:** Active profession = **Thief** (NewEnumerator14), also unlocked MilitaryVet and FireFighter
- **Johnny Kopo:** Not present in server save file

---

## Troubleshooting

### "pycryptodome not found"
```
pip install pycryptodome
```
If you have `pycrypto` installed, uninstall it first (`pip uninstall pycrypto`) as they conflict.

### "Save file not found"
Edit `DEFAULT_SAVE_FILE` in `config.py` to point to your save file, or pass the path as a command-line argument.

### "No profession entries found"
- The save file may be from a version that uses a different property name
- The player may not have selected a profession yet
- Try `python scan_properties.py --search Profession` to find related strings

### Pak extraction returns invalid offset/size
Some pak entries use the "full entry" format (`flags & 0x3F == 0x3F`) which is an unencoded
FPakEntry structure. For certain encrypted entries, this can produce invalid values. This is a
known limitation. The `.uexp` files needed for enum parsing typically use the compact format
and extract correctly.

### Game update changed professions
Run `python extract_enums.py` to re-extract the enum from the pak and update the mapping in
`config.py`.

### Save becomes corrupted after editing
Restore from the automatic backup file (`*.backup_YYYYMMDD_HHMMSS`). If editing across
digit groups (e.g., NE5 ↔ NE14), the file size changes, which in rare cases can affect
other size-dependent fields. Stick to same-digit-group swaps when possible.
