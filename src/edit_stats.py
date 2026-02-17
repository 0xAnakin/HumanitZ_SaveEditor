"""
HumanitZ Save Editor - Player Stats Editor
============================================
View and edit player Level, XP, and Skill Points in a HumanitZ save file.

Usage:
    python edit_stats.py <save_file> [--players <PlayerIDMapped.txt>]

The tool will:
  1. Locate all players by their SteamID properties (struct boundaries)
  2. Read Level, SkillsPoint, XPGained, Required XP, Current XP, and Profession
  3. Display a summary for each player
  4. Let you select a player and modify their stats or profession
  5. Create a timestamped backup before modifying

Property details:
  - Level (IntProperty):     The character's current level
  - SkillsPoint (IntProperty): Available (unspent) skill points
  - XPGained (IntProperty):  Total XP earned ever (lifetime)
  - Required XP (FloatProperty): XP needed to reach the next level
  - Current XP (FloatProperty):  XP progress towards the next level
  - StartingPerk (ByteProperty/Enum): Active profession

Stat edits are fixed-size in-place overwrites (int32 or float32),
so file size never changes. Profession edits within the same digit
group (0-9 or 10+) are also same-length. Cross-group swaps change
file size by 1 byte, which is handled automatically.
"""

import sys
import os
import struct
import shutil
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_PLAYER_ID_FILE, PROFESSIONS
from utils import load_save, load_players, write_save


# ============================================================================
# PROPERTY PATTERNS (name bytes as they appear in the save)
# ============================================================================

STEAMID_PROP = b'SteamID_67_6AFAA3B54A4447673EFF4D94BA0F84A7'

STARTING_PERK_PROP = b'StartingPerk_94_283EA71B427B7E97C43350818608A5E4'
UNLOCKED_PROF_PROP = b'UnlockedProfessionArr_17_2528BAE945B7A3B1A49D7893990D13BF'
ENUM_PREFIX = 'Enum_Professions::NewEnumerator'

STAT_PROPERTIES = {
    'level': {
        'name': 'Level',
        'bytes': b'Level_15_CF9C856C488C1A8E5FDBD0867E1E4B84',
        'type': 'int',
    },
    'skillpoints': {
        'name': 'Skill Points',
        'bytes': b'SkillsPoint_14_28A5347D4A1C7FE53D47AF8C61AF3F72',
        'type': 'int',
    },
    'xpgained': {
        'name': 'XP Gained (total)',
        'bytes': b'XPGained_9_DBB2D8FA4938305F1BD8C1AEE1155512',
        'type': 'int',
    },
    'required_xp': {
        'name': 'Required XP (next level)',
        'bytes': b'Required_3_9EC34DB94655BD224201AA9AD482C5BB',
        'type': 'float',
    },
    'current_xp': {
        'name': 'Current XP (progress)',
        'bytes': b'Current_4_EBCD0EF2496AEF7E3ACCBC9AD9D49E03',
        'type': 'float',
    },
}


# ============================================================================
# PLAYER DISCOVERY
# ============================================================================

def find_players(data: bytes, players: dict) -> list[dict]:
    """Find all players by locating SteamID properties in the save.
    
    Returns a list of dicts with:
        name, steam_id, struct_start, struct_end, stats (dict of stat values/offsets)
    """
    # Find all SteamID property locations
    steamid_locs = []
    pos = 0
    while True:
        idx = data.find(STEAMID_PROP, pos)
        if idx == -1:
            break
        # Parse the SteamID value
        name_end = idx + len(STEAMID_PROP) + 1  # +null
        type_len = struct.unpack_from('<i', data, name_end)[0]
        type_end = name_end + 4 + type_len
        val_start = type_end + 8 + 1  # size(8) + guid(1)
        val_len = struct.unpack_from('<i', data, val_start)[0]
        if 0 < val_len < 200:
            val_str = data[val_start + 4:val_start + 4 + val_len - 1].decode('ascii', 'replace')
            steam_id = val_str.split('_+_')[0]
            player_name = players.get(steam_id, f'Unknown({steam_id})')
            steamid_locs.append({
                'name': player_name,
                'steam_id': steam_id,
                'struct_start': idx,
            })
        pos = idx + 1

    if not steamid_locs:
        return []

    # Sort by offset and set struct boundaries
    steamid_locs.sort(key=lambda x: x['struct_start'])
    for i in range(len(steamid_locs)):
        if i + 1 < len(steamid_locs):
            steamid_locs[i]['struct_end'] = steamid_locs[i + 1]['struct_start']
        else:
            steamid_locs[i]['struct_end'] = len(data)

    # Read stats for each player
    for player in steamid_locs:
        region = data[player['struct_start']:player['struct_end']]
        player['stats'] = {}
        for key, prop in STAT_PROPERTIES.items():
            pidx = region.find(prop['bytes'])
            if pidx == -1:
                player['stats'][key] = None
                continue
            abs_off = player['struct_start'] + pidx
            name_end = abs_off + len(prop['bytes']) + 1
            tlen = struct.unpack_from('<i', data, name_end)[0]
            type_end = name_end + 4 + tlen
            val_off = type_end + 8 + 1  # size(8) + guid(1)
            if prop['type'] == 'int':
                val = struct.unpack_from('<i', data, val_off)[0]
            else:
                val = struct.unpack_from('<f', data, val_off)[0]
            player['stats'][key] = {
                'value': val,
                'offset': val_off,
                'type': prop['type'],
            }

        # Read profession (ByteProperty with Enum_Professions)
        perk_idx = region.find(STARTING_PERK_PROP)
        if perk_idx == -1:
            player['profession'] = None
        else:
            abs_off = player['struct_start'] + perk_idx
            name_end = abs_off + len(STARTING_PERK_PROP) + 1
            tlen = struct.unpack_from('<i', data, name_end)[0]
            type_end = name_end + 4 + tlen
            # ByteProperty layout: size(8) + enum_type(FString) + separator(1) + value(FString)
            size_off = type_end
            size_val = struct.unpack_from('<Q', data, size_off)[0]
            enum_type_off = size_off + 8
            enum_type_len = struct.unpack_from('<i', data, enum_type_off)[0]
            separator_off = enum_type_off + 4 + enum_type_len
            val_len_off = separator_off + 1
            val_len = struct.unpack_from('<i', data, val_len_off)[0]
            val_str_off = val_len_off + 4
            val_str = data[val_str_off:val_str_off + val_len - 1].decode('ascii', 'replace')
            # Extract the enum number
            enum_num = -1
            if ENUM_PREFIX in val_str:
                try:
                    enum_num = int(val_str[len(ENUM_PREFIX):])
                except ValueError:
                    pass
            player['profession'] = {
                'enum_num': enum_num,
                'enum_str': val_str,
                'display': PROFESSIONS.get(enum_num, f'Unknown({enum_num})'),
                'val_len_off': val_len_off,    # offset of the value FString length prefix
                'val_str_off': val_str_off,    # offset of the value FString data
                'val_len': val_len,            # current FString length (incl. null)
                'size_off': size_off,          # offset of the ByteProperty size field
                'size_val': size_val,          # current size value
            }

    return steamid_locs


# ============================================================================
# DISPLAY
# ============================================================================

def show_players(players: list[dict]) -> None:
    """Display all players and their stats."""
    print(f'\n{"=" * 60}')
    print(f'  Player Stats')
    print(f'{"=" * 60}')
    for i, p in enumerate(players):
        print(f'\n  [{i + 1}] {p["name"]} (SteamID: {p["steam_id"]})')
        # Show profession
        prof = p.get('profession')
        if prof:
            print(f'      {"Profession":30s}: {prof["display"]} (NE{prof["enum_num"]})')
        else:
            print(f'      {"Profession":30s}: NOT FOUND')
        # Show stats
        for key, prop in STAT_PROPERTIES.items():
            stat = p['stats'].get(key)
            if stat is None:
                print(f'      {prop["name"]:30s}: NOT FOUND')
            elif prop['type'] == 'int':
                print(f'      {prop["name"]:30s}: {stat["value"]:,}')
            else:
                print(f'      {prop["name"]:30s}: {stat["value"]:,.1f}')
    print()


# ============================================================================
# EDITING
# ============================================================================

def _ensure_backup(save_file: str, backup_created: list) -> None:
    """Create a timestamped backup (once per session)."""
    if not backup_created[0]:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'{save_file}.backup_{timestamp}'
        shutil.copy2(save_file, backup_path)
        print(f'  Backup created: {backup_path}')
        backup_created[0] = True


def apply_stat_change(data: bytes, stat: dict, new_value, save_file: str,
                      backup_created: list) -> bytes:
    """Write a new value for a stat property. Returns modified data."""
    _ensure_backup(save_file, backup_created)

    offset = stat['offset']

    if stat['type'] == 'int':
        new_bytes = struct.pack('<i', int(new_value))
        data = data[:offset] + new_bytes + data[offset + 4:]
    else:
        new_bytes = struct.pack('<f', float(new_value))
        data = data[:offset] + new_bytes + data[offset + 4:]

    write_save(save_file, data)
    return data


def _add_to_unlocked_professions(data: bytes, player: dict,
                                  enum_num: int) -> tuple[bytes, bool]:
    """Add a profession to the player's UnlockedProfessionArr if not already present.

    Returns (modified_data, was_added).
    """
    region = data[player['struct_start']:player['struct_end']]
    prop_idx = region.find(UNLOCKED_PROF_PROP)
    if prop_idx == -1:
        return data, False

    abs_base = player['struct_start'] + prop_idx
    chunk = data[abs_base:]

    # Parse header
    pos = len(UNLOCKED_PROF_PROP) + 1           # name + null
    type_len = struct.unpack_from('<i', chunk, pos)[0]
    pos += 4 + type_len                          # type FString

    prop_size_abs = abs_base + pos
    prop_size_val = struct.unpack_from('<Q', chunk, pos)[0]
    pos += 8

    inner_len = struct.unpack_from('<i', chunk, pos)[0]
    pos += 4 + inner_len + 1                     # inner type FString + separator

    count_abs = abs_base + pos
    count_val = struct.unpack_from('<i', chunk, pos)[0]
    pos += 4

    # Check if already present
    target_str = f'{ENUM_PREFIX}{enum_num}'
    for i in range(count_val):
        entry_len = struct.unpack_from('<i', chunk, pos)[0]
        entry_str = chunk[pos + 4:pos + 4 + entry_len - 1].decode('ascii', 'replace')
        if entry_str == target_str:
            return data, False      # already in the array
        pos += 4 + entry_len

    insert_abs = abs_base + pos

    # Build new FString entry
    new_entry_str = target_str.encode('ascii') + b'\x00'
    new_entry = struct.pack('<i', len(new_entry_str)) + new_entry_str

    # Insert entry, update count, update property size
    data = data[:insert_abs] + new_entry + data[insert_abs:]
    data = (data[:count_abs] +
            struct.pack('<i', count_val + 1) +
            data[count_abs + 4:])
    data = (data[:prop_size_abs] +
            struct.pack('<Q', prop_size_val + len(new_entry)) +
            data[prop_size_abs + 8:])

    return data, True


def apply_profession_change(data: bytes, player: dict, new_num: int,
                            save_file: str, backup_created: list) -> bytes:
    """Change a player's starting profession and preserve the old one.

    1. Adds the old profession to UnlockedProfessionArr (if not already there)
       so it remains available in the skill tree.
    2. Updates StartingPerk to the new profession.
    """
    _ensure_backup(save_file, backup_created)

    prof = player['profession']
    old_num = prof['enum_num']
    old_enum_str = prof['enum_str']
    new_enum_str = f'{ENUM_PREFIX}{new_num}'

    # Preserve the old profession in UnlockedProfessionArr
    data, added = _add_to_unlocked_professions(data, player, old_num)
    if added:
        old_name = PROFESSIONS.get(old_num, f'NE{old_num}')
        print(f'  Added {old_name} (NE{old_num}) to UnlockedProfessionArr'
              f' (preserving old profession).')
        # struct_end shifted by the inserted bytes — recalculate
        entry_bytes = len(f'{ENUM_PREFIX}{old_num}'.encode('ascii')) + 1 + 4  # FString
        player = dict(player)
        player['struct_end'] += entry_bytes
        # Recalculate profession offsets in the new data
        region = data[player['struct_start']:player['struct_end']]
        perk_idx = region.find(STARTING_PERK_PROP)
        if perk_idx != -1:
            abs_off = player['struct_start'] + perk_idx
            name_end = abs_off + len(STARTING_PERK_PROP) + 1
            tlen = struct.unpack_from('<i', data, name_end)[0]
            type_end = name_end + 4 + tlen
            size_off = type_end
            size_val = struct.unpack_from('<Q', data, size_off)[0]
            enum_type_off = size_off + 8
            enum_type_len = struct.unpack_from('<i', data, enum_type_off)[0]
            separator_off = enum_type_off + 4 + enum_type_len
            val_len_off = separator_off + 1
            val_len = struct.unpack_from('<i', data, val_len_off)[0]
            val_str_off = val_len_off + 4
            prof = {
                'enum_num': old_num,
                'enum_str': old_enum_str,
                'display': prof['display'],
                'val_len_off': val_len_off,
                'val_str_off': val_str_off,
                'val_len': val_len,
                'size_off': size_off,
                'size_val': size_val,
            }

    old_val_bytes = old_enum_str.encode('ascii') + b'\x00'
    new_val_bytes = new_enum_str.encode('ascii') + b'\x00'

    old_display = prof['display']
    new_display = PROFESSIONS.get(new_num, f'Unknown({new_num})')

    if len(old_val_bytes) == len(new_val_bytes):
        # Same length: simple in-place swap (safest)
        data = (data[:prof['val_str_off']] +
                new_val_bytes +
                data[prof['val_str_off'] + len(old_val_bytes):])
        print(f'  StartingPerk: {old_display} -> {new_display} (same-length swap)')
    else:
        # Different length: update value FString length prefix and size field
        new_val_len = len(new_enum_str) + 1  # +1 for null
        old_val_len = prof['val_len']
        delta = new_val_len - old_val_len

        # Update the value FString: length prefix + string + null
        old_full = struct.pack('<i', old_val_len) + old_val_bytes
        new_full = struct.pack('<i', new_val_len) + new_val_bytes
        data = (data[:prof['val_len_off']] +
                new_full +
                data[prof['val_len_off'] + len(old_full):])

        # Update the ByteProperty size field
        new_size = prof['size_val'] + delta
        data = (data[:prof['size_off']] +
                struct.pack('<Q', new_size) +
                data[prof['size_off'] + 8:])

        print(f'  StartingPerk: {old_display} -> {new_display}')
        print(f'  Note: String length changed ({old_val_len} -> {new_val_len}).'
              f' File size changed by {delta:+d} byte(s).')

    write_save(save_file, data)
    print(f'  Done! Saved to {save_file}')
    return data


def main():
    parser = argparse.ArgumentParser(
        description='View and edit player stats and professions in a HumanitZ save file'
    )
    parser.add_argument('save_file', help='Path to a HumanitZ .sav file')
    parser.add_argument('--players', default=DEFAULT_PLAYER_ID_FILE,
                        help='Path to PlayerIDMapped.txt (default: %(default)s)')
    args = parser.parse_args()

    save_file = args.save_file
    if not os.path.exists(save_file):
        print(f'Error: Save file not found: {save_file}')
        sys.exit(1)

    known_players = load_players(args.players)
    print(f'Loaded {len(known_players)} player(s) from {args.players}')

    data = load_save(save_file)
    print(f'Save file: {save_file}')
    print(f'Size: {len(data):,} bytes')

    players = find_players(data, known_players)
    if not players:
        print('No players found in save file.')
        return

    show_players(players)

    print('=' * 60)
    print('  Stats Editor')
    print('=' * 60)
    print('  Commands:')
    print('    <player#>  — Select a player to edit')
    print('    list       — Re-display player stats')
    print('    q          — Quit')
    print()

    backup_created = [False]  # mutable flag for backup tracking

    while True:
        choice = input('Player # to edit (or q/list): ').strip().lower()

        if choice == 'q':
            print('Exiting.')
            return
        if choice == 'list':
            players = find_players(data, known_players)
            show_players(players)
            continue

        try:
            player_idx = int(choice) - 1
            if player_idx < 0 or player_idx >= len(players):
                print(f'  Invalid. Choose 1-{len(players)}.')
                continue
        except ValueError:
            print('  Enter a number, "list", or "q".')
            continue

        player = players[player_idx]
        prof = player.get('profession')
        prof_display = prof['display'] if prof else 'N/A'

        print(f'\n  Selected: {player["name"]}')
        print(f'  What to change?')
        print(f'    1. Level           (current: {_fmt_stat(player, "level")})')
        print(f'    2. Skill Points    (current: {_fmt_stat(player, "skillpoints")})')
        print(f'    3. XP Gained       (current: {_fmt_stat(player, "xpgained")})')
        print(f'    4. Current XP      (current: {_fmt_stat(player, "current_xp")})')
        print(f'    5. Required XP     (current: {_fmt_stat(player, "required_xp")})')
        print(f'    6. Set all (Level + Skill Points + XP)')
        print(f'    7. Profession      (current: {prof_display})')
        print(f'    b. Back')

        stat_choice = input('  Choice: ').strip().lower()
        if stat_choice == 'b':
            continue

        stat_map = {
            '1': 'level',
            '2': 'skillpoints',
            '3': 'xpgained',
            '4': 'current_xp',
            '5': 'required_xp',
        }

        if stat_choice == '7':
            # Change profession
            if prof is None:
                print('  Profession not found for this player.')
                continue
            print(f'\n  Current profession: {prof["display"]} (NE{prof["enum_num"]})')
            print(f'\n  Available professions:')
            for num, name in sorted(PROFESSIONS.items()):
                group = '[1-digit]' if num < 10 else '[2-digit]'
                marker = ' <-- current' if num == prof['enum_num'] else ''
                print(f'    {num:2d}: {name:<30s} {group}{marker}')
            try:
                new_input = input(f'\n  New profession # (0-{max(PROFESSIONS.keys())}): ').strip()
                new_num = int(new_input)
                if new_num not in PROFESSIONS:
                    print(f'  Invalid. Choose 0-{max(PROFESSIONS.keys())}.')
                    continue
            except ValueError:
                print('  Invalid number.')
                continue
            if new_num == prof['enum_num']:
                print('  Same profession, no change needed.')
                continue

            new_display = PROFESSIONS[new_num]
            old_digits = len(str(prof['enum_num']))
            new_digits = len(str(new_num))
            safety = ('SAFE (same string length)' if old_digits == new_digits
                      else 'OK (string length changes, handled automatically)')
            print(f'\n  Change: {prof["display"]} (NE{prof["enum_num"]}) -> '
                  f'{new_display} (NE{new_num})')
            print(f'  Safety: {safety}')
            confirm = input('  Confirm? (y/n): ').strip().lower()
            if confirm != 'y':
                print('  Cancelled.')
                continue

            data = apply_profession_change(data, player, new_num,
                                           save_file, backup_created)
            players = find_players(data, known_players)
            show_players(players)
            continue

        if stat_choice == '6':
            # Set all main stats at once
            try:
                new_level = input(f'  New Level (current: {_fmt_stat(player, "level")}): ').strip()
                new_sp = input(f'  New Skill Points (current: {_fmt_stat(player, "skillpoints")}): ').strip()
                new_xp = input(f'  New XP Gained (current: {_fmt_stat(player, "xpgained")}): ').strip()

                changes = []
                if new_level:
                    lv = int(new_level)
                    if player['stats']['level']:
                        changes.append(('level', lv))
                if new_sp:
                    sp = int(new_sp)
                    if player['stats']['skillpoints']:
                        changes.append(('skillpoints', sp))
                if new_xp:
                    xp = int(new_xp)
                    if player['stats']['xpgained']:
                        changes.append(('xpgained', xp))

                if not changes:
                    print('  No changes specified.')
                    continue

                print(f'\n  Changes for {player["name"]}:')
                for key, val in changes:
                    prop = STAT_PROPERTIES[key]
                    old = player['stats'][key]['value'] if player['stats'][key] else 'N/A'
                    print(f'    {prop["name"]}: {old} -> {val}')

                confirm = input('  Confirm? (y/n): ').strip().lower()
                if confirm != 'y':
                    print('  Cancelled.')
                    continue

                for key, val in changes:
                    data = apply_stat_change(data, player['stats'][key], val,
                                            save_file, backup_created)
                    print(f'  Updated {STAT_PROPERTIES[key]["name"]} to {val}')

                # Re-scan
                players = find_players(data, known_players)
                show_players(players)

            except ValueError:
                print('  Invalid number entered.')
            continue

        if stat_choice not in stat_map:
            print('  Invalid choice.')
            continue

        stat_key = stat_map[stat_choice]
        stat = player['stats'].get(stat_key)
        if stat is None:
            print(f'  {STAT_PROPERTIES[stat_key]["name"]} not found for this player.')
            continue

        prop = STAT_PROPERTIES[stat_key]
        try:
            if prop['type'] == 'int':
                new_val = int(input(f'  New {prop["name"]} value: ').strip())
            else:
                new_val = float(input(f'  New {prop["name"]} value: ').strip())
        except ValueError:
            print('  Invalid number.')
            continue

        old_val = stat['value']
        print(f'\n  Change {prop["name"]}: {old_val} -> {new_val}')
        confirm = input('  Confirm? (y/n): ').strip().lower()
        if confirm != 'y':
            print('  Cancelled.')
            continue

        data = apply_stat_change(data, stat, new_val, save_file, backup_created)
        print(f'  Done! {prop["name"]} updated to {new_val}')

        # Re-scan
        players = find_players(data, known_players)
        show_players(players)


def _fmt_stat(player: dict, key: str) -> str:
    """Format a stat value for display."""
    stat = player['stats'].get(key)
    if stat is None:
        return 'N/A'
    if STAT_PROPERTIES[key]['type'] == 'int':
        return f'{stat["value"]:,}'
    return f'{stat["value"]:,.1f}'


if __name__ == '__main__':
    main()
