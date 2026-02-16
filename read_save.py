"""
HumanitZ Save Editor - Save Analyzer
======================================
Reads a dedicated server save file and reports:
  - GVAS header details
  - All players found (by SteamID)
  - Each player's active profession
  - Each player's unlocked professions
  - Property locations for editing

Usage:
    python read_save.py [save_file_path]

If no path is given, uses the default from config.py.
"""

import sys
import os
import struct

# Allow running from the script's own directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_SAVE_FILE, PROFESSIONS, PLAYERS
from utils import (
    load_save, parse_gvas_header, scan_enum_properties,
    find_all_bytes, find_nearest_player, read_null_terminated,
)


def format_profession(enum_num: int) -> str:
    """Return 'DisplayName (NewEnumeratorN)' for a given enum number."""
    name = PROFESSIONS.get(enum_num, f'Unknown({enum_num})')
    return f'{name} (NewEnumerator{enum_num})'


def analyze_save(filepath: str, players: dict = None) -> dict:
    """Analyze a HumanitZ save file and return structured results.
    
    Returns dict with:
        header: GvasHeader object
        size: file size in bytes
        player_locations: {steam_id: [offsets]}
        profession_entries: list of entry dicts augmented with player info
        player_summary: {player_name: {active: str, unlocked: [str]}}
    """
    if players is None:
        players = PLAYERS

    data = load_save(filepath)
    header = parse_gvas_header(data)
    entries = scan_enum_properties(data)

    # Find all SteamID locations
    player_locations = {}
    for steam_id, name in players.items():
        locs = find_all_bytes(data, steam_id.encode('ascii'))
        player_locations[steam_id] = locs

    # Augment entries with player information
    for entry in entries:
        player, dist = find_nearest_player(data, entry['offset'], players)
        entry['player'] = player or 'Unknown'
        entry['player_distance'] = dist

    # Build per-player summary
    player_summary = {}
    for name in players.values():
        player_entries = [e for e in entries if e['player'] == name]
        active_entries = [e for e in player_entries if e['context'] == 'StartingPerk']
        unlocked_entries = [e for e in player_entries if e['context'] == 'UnlockedProfessionArr']

        active = format_profession(active_entries[0]['enum_num']) if active_entries else 'Not set'
        unlocked = [format_profession(e['enum_num']) for e in unlocked_entries]

        if active_entries or unlocked_entries:
            player_summary[name] = {
                'active': active,
                'unlocked': unlocked,
            }

    # Check for players not in the save
    for name in players.values():
        if name not in player_summary:
            player_summary[name] = None  # Not present in save

    return {
        'header': header,
        'size': len(data),
        'player_locations': player_locations,
        'profession_entries': entries,
        'player_summary': player_summary,
    }


def print_report(filepath: str, results: dict) -> None:
    """Print a formatted report of the save analysis."""
    header = results['header']
    size = results['size']
    entries = results['profession_entries']
    summary = results['player_summary']

    print('=' * 70)
    print('  HumanitZ Save File Analysis')
    print('=' * 70)
    print(f'  File:    {filepath}')
    print(f'  Size:    {size:,} bytes ({size / 1024 / 1024:.1f} MB)')
    print(f'  Format:  GVAS (magic 0x{header.magic:08X})')
    print(f'  Engine:  {header.engine_version_branch}')
    print(f'  Save Version: {header.save_game_version}')
    print(f'  Package Version: {header.package_version}')
    print(f'  Save Class: {header.save_game_class}')
    print()

    # Player SteamID presence
    print('-' * 70)
    print('  Player SteamID Presence')
    print('-' * 70)
    for steam_id, locs in results['player_locations'].items():
        name = PLAYERS.get(steam_id, steam_id)
        status = f'{len(locs)} occurrence(s)' if locs else 'NOT FOUND in save'
        print(f'  {name} ({steam_id}): {status}')
    print()

    # Profession entries
    print('-' * 70)
    print('  Profession Entries Found')
    print('-' * 70)
    if not entries:
        print('  No profession entries found.')
    else:
        for i, e in enumerate(entries):
            ctx_label = {
                'StartingPerk': 'Active Profession',
                'UnlockedProfessionArr': 'Unlocked',
            }.get(e['context'], e['context'])

            print(f'  [{i + 1}] {e["player"]:<15s} | {ctx_label:<20s} | '
                  f'{PROFESSIONS.get(e["enum_num"], "?")} '
                  f'(NE{e["enum_num"]})')
            print(f'      Offset: 0x{e["offset"]:08X}  |  '
                  f'Length prefix valid: {e["length_prefix_ok"]}')
    print()

    # Player summary
    print('-' * 70)
    print('  Player Summary')
    print('-' * 70)
    for name, info in summary.items():
        if info is None:
            print(f'  {name}: NOT present in this save file')
        else:
            print(f'  {name}:')
            print(f'    Active Profession: {info["active"]}')
            if info['unlocked']:
                print(f'    Unlocked:          {", ".join(info["unlocked"])}')
            else:
                print(f'    Unlocked:          (none)')
    print()

    # Available professions reference
    print('-' * 70)
    print('  Available Professions (for editing)')
    print('-' * 70)
    for num, name in sorted(PROFESSIONS.items()):
        digit_group = '1-digit' if num < 10 else '2-digit'
        print(f'  {num:2d}: {name:<30s} [{digit_group}]')
    print()
    print('  Note: Swapping within the same digit group (0-9 or 10-16) is safest')
    print('        because the enum string length stays the same.')
    print()


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SAVE_FILE

    if not os.path.exists(filepath):
        print(f'Error: Save file not found: {filepath}')
        print(f'Usage: python read_save.py [save_file_path]')
        sys.exit(1)

    results = analyze_save(filepath)
    print_report(filepath, results)


if __name__ == '__main__':
    main()
