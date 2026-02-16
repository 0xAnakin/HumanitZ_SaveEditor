"""
HumanitZ Save Editor - Enum Extractor
=======================================
Extracts the Enum_Professions uasset/uexp from the game pak file
and parses the display name mapping.

This was used to build the PROFESSIONS dict in config.py.
Run it again if the game updates with new professions.

Usage:
    python extract_enums.py [--output <dir>]

Output:
    - Enum_Professions.uexp (extracted binary)
    - Prints the full NewEnumeratorN -> Display Name mapping
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PAK_FILE, AES_KEY
from pak_reader import read_pak_info, read_pak_index, decode_entry, extract_file


def parse_enum_uexp(data: bytes) -> list[dict]:
    """Parse a UserDefinedEnum .uexp file to extract display names.
    
    UE4 UserDefinedEnum .uexp contains a DisplayNameMap section where
    each entry follows the pattern:
        FName   (uint32 index + uint32 instance=0)  [8 bytes]
        uint32  SavedFlags = 2                      [4 bytes]
        byte    HistoryType = 0xFF (None)            [1 byte]
        uint32  hasCultureInvariant = 1              [4 bytes]
        FString DisplayName (int32 len + chars)      [4 + len bytes]
    
    Returns list of dicts with 'name_idx' and 'display_name' in order.
    """
    display_names = []
    pos = 0

    while pos < len(data) - 20:
        if (pos + 17 <= len(data) and
                data[pos + 4:pos + 8] == b'\x00\x00\x00\x00' and    # instance = 0
                data[pos + 8:pos + 12] == b'\x02\x00\x00\x00' and   # SavedFlags = 2
                data[pos + 12] == 0xFF and                            # HistoryType = None
                data[pos + 13:pos + 17] == b'\x01\x00\x00\x00'):     # hasCultureInvariant
            
            name_idx = struct.unpack_from('<I', data, pos)[0]
            str_len = struct.unpack_from('<i', data, pos + 17)[0]

            if 1 <= str_len <= 200 and pos + 21 + str_len <= len(data):
                string = data[pos + 21:pos + 21 + str_len - 1].decode('ascii', errors='replace')
                display_names.append({
                    'name_idx': name_idx,
                    'display_name': string,
                    'offset': pos,
                })
                pos = pos + 21 + str_len
                continue
        pos += 1

    return display_names


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract and parse Enum_Professions from HumanitZ pak file'
    )
    parser.add_argument('--output', '-o', default='.',
                        help='Output directory for extracted files')
    parser.add_argument('--pak', default=PAK_FILE,
                        help='Path to pak file')

    args = parser.parse_args()

    if not os.path.exists(args.pak):
        print(f'Error: Pak file not found: {args.pak}')
        sys.exit(1)

    print(f'Reading pak file: {args.pak}')

    with open(args.pak, 'rb') as f:
        f.seek(0, 2)
        file_size = f.tell()

        pak_info = read_pak_info(f, file_size)
        mount_point, num_entries, encoded_data, dir_entries = read_pak_index(
            f, pak_info, AES_KEY
        )

        print(f'Index decrypted: {num_entries:,} entries, {len(dir_entries):,} directory entries')

        # Find Enum_Professions files
        target_files = {}
        for entry in dir_entries:
            if 'Enum_Professions' in entry.path:
                target_files[entry.path] = entry

        if not target_files:
            print('ERROR: Enum_Professions files not found in pak!')
            print('Try searching: python pak_reader.py --search Professions')
            sys.exit(1)

        print(f'\nFound {len(target_files)} Enum_Professions files:')
        for path in target_files:
            print(f'  {path}')

        # Extract the .uexp file (contains display names)
        uexp_entry = None
        for path, entry in target_files.items():
            if path.endswith('.uexp'):
                uexp_entry = entry
                break

        if not uexp_entry:
            print('ERROR: Enum_Professions.uexp not found!')
            sys.exit(1)

        decoded = decode_entry(encoded_data, uexp_entry.encoded_offset)

        if not (0 < decoded['offset'] < file_size and 0 < decoded['size'] < 10 * 1024 * 1024):
            print(f'ERROR: Decoded entry has invalid offset/size:')
            print(f'  Offset: {decoded["offset"]}, Size: {decoded["size"]}')
            sys.exit(1)

        uexp_data = extract_file(f, decoded, AES_KEY)
        print(f'\nExtracted Enum_Professions.uexp: {len(uexp_data):,} bytes')

        # Save to output dir
        os.makedirs(args.output, exist_ok=True)
        out_path = os.path.join(args.output, 'Enum_Professions.uexp')
        with open(out_path, 'wb') as out:
            out.write(uexp_data)
        print(f'Saved to: {out_path}')

        # Parse display names
        display_names = parse_enum_uexp(uexp_data)

        if not display_names:
            print('\nERROR: Could not parse display names from .uexp!')
            print('The file format may have changed. Check the raw hex dump.')
            sys.exit(1)

        print(f'\n{"=" * 60}')
        print(f'  Enum_Professions Mapping ({len(display_names)} entries)')
        print(f'{"=" * 60}')
        print(f'  {"#":<4s} {"NewEnumerator":<20s} {"Display Name":<30s}')
        print(f'  {"-" * 54}')

        for i, dn in enumerate(display_names):
            print(f'  {i:<4d} NewEnumerator{i:<7d} {dn["display_name"]}')

        # Output as Python dict for config.py
        print(f'\n{"=" * 60}')
        print('  Python dict for config.py:')
        print(f'{"=" * 60}')
        print('PROFESSIONS = {')
        for i, dn in enumerate(display_names):
            print(f'    {i}: {dn["display_name"]!r},')
        print('}')


if __name__ == '__main__':
    main()
