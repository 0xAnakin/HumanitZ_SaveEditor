"""
HumanitZ Save Editor - Player Stats Editor
============================================
View and edit player Level, XP, and Skill Points in a HumanitZ save file.

Usage:
    python edit_stats.py [save_file_path]

If no path is given, uses the default from config.py.
The tool will:
  1. Locate all players by their SteamID properties (struct boundaries)
  2. Read Level, SkillsPoint, XPGained, Required XP, and Current XP
  3. Display a summary for each player
  4. Let you select a player and modify their stats
  5. Create a timestamped backup before modifying

Property details:
  - Level (IntProperty):     The character's current level
  - SkillsPoint (IntProperty): Available (unspent) skill points
  - XPGained (IntProperty):  Total XP earned ever (lifetime)
  - Required XP (FloatProperty): XP needed to reach the next level
  - Current XP (FloatProperty):  XP progress towards the next level

All edits are fixed-size in-place overwrites (int32 or float32),
so file size never changes. This is completely safe.
"""

import sys
import os
import struct
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_SAVE_FILE, PLAYERS
from utils import load_save, write_save


# ============================================================================
# PROPERTY PATTERNS (name bytes as they appear in the save)
# ============================================================================

STEAMID_PROP = b'SteamID_67_6AFAA3B54A4447673EFF4D94BA0F84A7'

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

def find_players(data: bytes) -> list[dict]:
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
            player_name = PLAYERS.get(steam_id, f'Unknown({steam_id})')
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

def apply_stat_change(data: bytes, stat: dict, new_value, save_file: str,
                      backup_created: list) -> bytes:
    """Write a new value for a stat property. Returns modified data."""
    # Create backup only once per session
    if not backup_created[0]:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'{save_file}.backup_{timestamp}'
        shutil.copy2(save_file, backup_path)
        print(f'  Backup created: {backup_path}')
        backup_created[0] = True

    offset = stat['offset']
    old_value = stat['value']

    if stat['type'] == 'int':
        new_bytes = struct.pack('<i', int(new_value))
        data = data[:offset] + new_bytes + data[offset + 4:]
    else:
        new_bytes = struct.pack('<f', float(new_value))
        data = data[:offset] + new_bytes + data[offset + 4:]

    write_save(save_file, data)
    return data


def main():
    save_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SAVE_FILE

    if not os.path.exists(save_file):
        print(f'Error: Save file not found: {save_file}')
        print(f'Usage: python edit_stats.py [save_file_path]')
        sys.exit(1)

    data = load_save(save_file)
    print(f'Save file: {save_file}')
    print(f'Size: {len(data):,} bytes')

    players = find_players(data)
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
            players = find_players(data)
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
        print(f'\n  Selected: {player["name"]}')
        print(f'  What to change?')
        print(f'    1. Level           (current: {_fmt_stat(player, "level")})')
        print(f'    2. Skill Points    (current: {_fmt_stat(player, "skillpoints")})')
        print(f'    3. XP Gained       (current: {_fmt_stat(player, "xpgained")})')
        print(f'    4. Current XP      (current: {_fmt_stat(player, "current_xp")})')
        print(f'    5. Required XP     (current: {_fmt_stat(player, "required_xp")})')
        print(f'    6. Set all (Level + Skill Points + XP)')
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
                players = find_players(data)
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
        players = find_players(data)
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
