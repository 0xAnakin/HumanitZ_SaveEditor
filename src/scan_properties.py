"""
HumanitZ Save Editor - Generic Property Scanner
=================================================
Scans a save file for any UE4 property type and reports all matches.
Useful for finding other editable values beyond professions.

Usage:
    python scan_properties.py <save_file> [--search <string>]

Examples:
    python scan_properties.py save.sav --search Health
    python scan_properties.py save.sav --search Stamina
    python scan_properties.py save.sav --search Level
"""

import sys
import os
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import load_save, parse_gvas_header, find_all_bytes


# UE4 property type names (these appear as FStrings in GVAS saves)
UE4_PROPERTY_TYPES = [
    'IntProperty', 'FloatProperty', 'BoolProperty', 'StrProperty',
    'NameProperty', 'TextProperty', 'ByteProperty', 'EnumProperty',
    'StructProperty', 'ArrayProperty', 'MapProperty', 'SetProperty',
    'ObjectProperty', 'SoftObjectProperty', 'Int8Property',
    'Int16Property', 'Int64Property', 'UInt16Property', 'UInt32Property',
    'UInt64Property', 'DoubleProperty',
]


def scan_for_string(data: bytes, search: str) -> None:
    """Find all occurrences of a string and show surrounding context."""
    needle = search.encode('ascii')
    locations = find_all_bytes(data, needle)

    print(f'Found {len(locations)} occurrences of "{search}":\n')

    for loc in locations:
        # Get context: 64 bytes before and after
        ctx_start = max(0, loc - 64)
        ctx_end = min(len(data), loc + len(needle) + 64)
        context = data[ctx_start:ctx_end]

        # Show as readable ASCII with dots for non-printable
        text = ''.join(chr(b) if 32 <= b < 127 else '.' for b in context)

        # Find where the match starts in the context string
        match_start = loc - ctx_start
        match_end = match_start + len(needle)

        print(f'  Offset 0x{loc:08X} ({loc:,}):')
        print(f'    {text}')
        print(f'    {"~" * match_start}{"^" * len(needle)}')

        # Try to identify the property type by looking ahead for known types
        after = data[loc:loc + 200]
        for prop_type in UE4_PROPERTY_TYPES:
            prop_bytes = prop_type.encode('ascii')
            idx = after.find(prop_bytes)
            if idx != -1 and idx < 100:
                print(f'    Property type: {prop_type} (at +{idx})')
                break

        # Check for int32 length prefix (common for FString)
        if loc >= 4:
            prefix = struct.unpack_from('<i', data, loc - 4)[0]
            if prefix == len(search) + 1:
                print(f'    Has valid FString length prefix: {prefix}')

        print()


def scan_property_names(data: bytes) -> dict:
    """Find all UE4 property names and count them."""
    property_counts = {}
    for prop_type in UE4_PROPERTY_TYPES:
        count = len(find_all_bytes(data, prop_type.encode('ascii')))
        if count > 0:
            property_counts[prop_type] = count
    return property_counts


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Scan HumanitZ save files for properties and strings'
    )
    parser.add_argument('save_file', help='Path to a HumanitZ .sav file')
    parser.add_argument('--search', '-s', metavar='STRING',
                        help='Search for a specific string')
    parser.add_argument('--properties', '-p', action='store_true',
                        help='Count all UE4 property types')
    parser.add_argument('--header', action='store_true',
                        help='Show GVAS header details')
    parser.add_argument('--hex', metavar='OFFSET',
                        help='Hex dump 256 bytes at a specific offset (hex or decimal)')

    args = parser.parse_args()

    if not os.path.exists(args.save_file):
        print(f'Error: File not found: {args.save_file}')
        sys.exit(1)

    data = load_save(args.save_file)
    print(f'File: {args.save_file}')
    print(f'Size: {len(data):,} bytes\n')

    if args.header:
        try:
            header = parse_gvas_header(data)
            print(f'GVAS Header:')
            print(f'  Magic:           0x{header.magic:08X}')
            print(f'  Save Version:    {header.save_game_version}')
            print(f'  Package Version: {header.package_version}')
            print(f'  Engine:          {header.engine_version_major}.'
                  f'{header.engine_version_minor}.{header.engine_version_patch}')
            print(f'  Branch:          {header.engine_version_branch}')
            print(f'  Custom Versions: {header.custom_version_count}')
            print(f'  Save Class:      {header.save_game_class}')
            print(f'  Header Size:     {header.header_size} bytes')
            print()
        except ValueError as e:
            print(f'Not a GVAS file: {e}\n')

    if args.properties:
        counts = scan_property_names(data)
        print('UE4 Property Types Found:')
        for prop_type, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f'  {prop_type:<25s} {count:>6,}')
        print()

    if args.search:
        scan_for_string(data, args.search)

    if args.hex:
        try:
            offset = int(args.hex, 0)  # supports 0x prefix
        except ValueError:
            print(f'Invalid offset: {args.hex}')
            sys.exit(1)

        end = min(len(data), offset + 256)
        chunk = data[offset:end]
        print(f'Hex dump at 0x{offset:08X} ({end - offset} bytes):')
        for i in range(0, len(chunk), 16):
            row = chunk[i:i + 16]
            hex_str = ' '.join(f'{b:02x}' for b in row)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
            print(f'  {offset + i:08x}: {hex_str:<48s} {ascii_str}')
        print()

    if not any([args.search, args.properties, args.header, args.hex]):
        print('No action specified. Use --help for options.')
        print('Quick examples:')
        print(f'  python scan_properties.py --header')
        print(f'  python scan_properties.py --properties')
        print(f'  python scan_properties.py --search Health')
        print(f'  python scan_properties.py --hex 0x007B3200')


if __name__ == '__main__':
    main()
