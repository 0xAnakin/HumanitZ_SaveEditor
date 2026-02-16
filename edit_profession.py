"""
HumanitZ Save Editor - Profession Changer
==========================================
Interactive tool to change player professions in a HumanitZ save file.

Usage:
    python edit_profession.py [save_file_path]

If no path is given, uses the default from config.py.
The tool will:
  1. Scan the save for all profession entries
  2. Show which player each entry belongs to
  3. Let you select an entry and a new profession
  4. Create a timestamped backup before modifying
  5. Update the save file

Safety notes:
  - Always creates a backup before any modification.
  - Swapping between professions with the same digit count in their
    NewEnumerator number (0-9 = 1 digit, 10-16 = 2 digits) is a
    same-length replacement and is completely safe.
  - Cross-group swaps (e.g., NE5 -> NE14) change the FString length,
    which requires updating the int32 length prefix. This is handled
    automatically, but the file size changes, which could potentially
    cause issues with other size-dependent fields in rare cases.
"""

import sys
import os
import struct
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_SAVE_FILE, PROFESSIONS, PLAYERS
from utils import (
    load_save, write_save, scan_enum_properties,
    find_nearest_player,
)


def show_entries(entries: list[dict]) -> None:
    """Display all profession entries in a numbered list."""
    print(f'\nFound {len(entries)} profession entries:\n')
    for i, e in enumerate(entries):
        ctx_label = {
            'StartingPerk': 'Active Profession',
            'UnlockedProfessionArr': 'Unlocked',
        }.get(e['context'], e['context'])

        display = PROFESSIONS.get(e['enum_num'], f'Unknown({e["enum_num"]})')
        print(f'  [{i + 1}] {e["player"]:<15s} | {ctx_label:<20s} | '
              f'{display} (NE{e["enum_num"]})')
        print(f'      Offset: 0x{e["offset"]:08X}')


def show_professions() -> None:
    """Display the profession selection menu."""
    print()
    print('=' * 50)
    print('  Available Professions')
    print('=' * 50)
    for num, name in sorted(PROFESSIONS.items()):
        group = '[1-digit]' if num < 10 else '[2-digit]'
        print(f'  {num:2d}: {name:<30s} {group}')
    print()


def rescan_entries(data: bytes) -> list[dict]:
    """Re-scan the save data for profession entries with player mapping."""
    entries = scan_enum_properties(data)
    for entry in entries:
        player, dist = find_nearest_player(data, entry['offset'], PLAYERS)
        entry['player'] = player or 'Unknown'
        entry['player_distance'] = dist
    return entries


def apply_change(data: bytes, entry: dict, new_num: int,
                 save_file: str) -> bytes:
    """Apply a profession change and return the modified data.
    
    Creates a backup before writing, then writes the modified save.
    Returns the new data bytes.
    """
    old_enum_str = entry['enum_str']
    new_enum_str = f'Enum_Professions::NewEnumerator{new_num}'

    old_bytes = old_enum_str.encode('ascii') + b'\x00'
    new_bytes = new_enum_str.encode('ascii') + b'\x00'

    old_display = PROFESSIONS.get(entry['enum_num'], '?')
    new_display = PROFESSIONS.get(new_num, '?')

    # Create backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{save_file}.backup_{timestamp}'
    shutil.copy2(save_file, backup_path)
    print(f'  Backup created: {backup_path}')

    if len(old_bytes) == len(new_bytes):
        # Same length: simple byte replacement (safest)
        data = data[:entry['offset']] + new_bytes + data[entry['end']:]
        write_save(save_file, data)
        print(f'  Done! {old_display} -> {new_display} (same-length swap)')
    else:
        # Different length: need to update the FString length prefix too
        prefix_offset = entry['length_prefix_offset']
        stored_len = struct.unpack_from('<i', data, prefix_offset)[0]
        old_len = len(old_enum_str) + 1
        new_len = len(new_enum_str) + 1

        if entry['length_prefix_ok']:
            # Build full replacement (length prefix + string + null)
            old_full = struct.pack('<i', old_len) + old_bytes
            new_full = struct.pack('<i', new_len) + new_bytes

            data = (data[:prefix_offset] +
                    new_full +
                    data[prefix_offset + len(old_full):])

            write_save(save_file, data)
            print(f'  Done! {old_display} -> {new_display}')
            print(f'  Note: String length changed ({old_len} -> {new_len} bytes).')
            print(f'  File size changed by {new_len - old_len} byte(s).')
        else:
            print(f'  ERROR: Length prefix mismatch at 0x{prefix_offset:08X}.')
            print(f'  Expected {old_len}, found {stored_len}.')
            print(f'  Cannot safely modify this entry. Restoring backup.')
            shutil.copy2(backup_path, save_file)
            return load_save(save_file)

    return data


def main():
    save_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SAVE_FILE

    if not os.path.exists(save_file):
        print(f'Error: Save file not found: {save_file}')
        print(f'Usage: python edit_profession.py [save_file_path]')
        sys.exit(1)

    data = load_save(save_file)
    print(f'Save file: {save_file}')
    print(f'Size: {len(data):,} bytes')

    entries = rescan_entries(data)

    if not entries:
        print('No profession entries found in save file.')
        return

    show_entries(entries)
    show_professions()

    print('=' * 50)
    print('  Profession Editor')
    print('=' * 50)
    print('  Enter the entry number to change, then the new profession number.')
    print('  Type "q" to quit without changes.')
    print('  Type "list" to re-display entries.')
    print('  Type "profs" to re-display available professions.')

    while True:
        choice = input('\nEntry # to change (or q/list/profs): ').strip().lower()

        if choice == 'q':
            print('Exiting. No further changes.')
            return
        if choice == 'list':
            show_entries(entries)
            continue
        if choice == 'profs':
            show_professions()
            continue

        try:
            entry_idx = int(choice) - 1
            if entry_idx < 0 or entry_idx >= len(entries):
                print(f'  Invalid. Choose 1-{len(entries)}.')
                continue
        except ValueError:
            print('  Please enter a number, "q", "list", or "profs".')
            continue

        entry = entries[entry_idx]
        old_display = PROFESSIONS.get(entry['enum_num'], '?')
        print(f'\n  Selected: [{entry_idx + 1}] {entry["player"]} - '
              f'{old_display} (NE{entry["enum_num"]}) [{entry["context"]}]')

        new_input = input('  New profession # (0-16): ').strip()
        try:
            new_num = int(new_input)
            if new_num not in PROFESSIONS:
                print(f'  Invalid profession. Choose 0-16.')
                continue
        except ValueError:
            print('  Please enter a number 0-16.')
            continue

        if new_num == entry['enum_num']:
            print('  Same profession selected, no change needed.')
            continue

        new_display = PROFESSIONS[new_num]

        # Show safety info
        old_digits = len(str(entry['enum_num']))
        new_digits = len(str(new_num))
        if old_digits == new_digits:
            safety = 'SAFE (same string length)'
        else:
            safety = 'CAUTION (string length changes, length prefix will be updated)'

        print(f'\n  Change: {old_display} (NE{entry["enum_num"]}) -> '
              f'{new_display} (NE{new_num})')
        print(f'  Safety: {safety}')

        confirm = input('  Confirm? (y/n): ').strip().lower()
        if confirm != 'y':
            print('  Cancelled.')
            continue

        data = apply_change(data, entry, new_num, save_file)

        # Re-scan after modification
        entries = rescan_entries(data)
        print('\n  Updated entries:')
        show_entries(entries)


if __name__ == '__main__':
    main()
