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
    - Enum_Professions.uasset (extracted binary)
    - Prints the full NewEnumeratorN -> Display Name mapping

Notes:
    The NewEnumerator numbers in the game enum are NOT necessarily sequential.
    For example, NewEnumerator11 may not exist (gap in numbering).
    This script uses the .uasset name table to resolve the correct
    NewEnumerator number for each display name, rather than assuming
    sequential ordering.
"""

import struct
import io
import sys
import os
import re
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PAK_FILE, AES_KEY
from pak_reader import read_pak_info, read_pak_index, decode_entry, extract_file
from utils import read_fstring


def parse_enum_uexp(data: bytes) -> list[dict]:
    """Parse a UserDefinedEnum .uexp file to extract display names.
    
    UE4 UserDefinedEnum .uexp contains a DisplayNameMap section where
    each entry follows the pattern:
        FName   (uint32 index + uint32 instance=0)  [8 bytes]
        uint32  SavedFlags = 2                      [4 bytes]
        byte    HistoryType = 0xFF (None)            [1 byte]
        uint32  hasCultureInvariant = 1              [4 bytes]
        FString DisplayName (int32 len + chars)      [4 + len bytes]
    
    Returns list of dicts with 'name_idx' (FName index into .uasset name table)
    and 'display_name' in file order.
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


def extract_compressed_file(pak_handle, entry_info: dict) -> bytes:
    """Extract a Zlib-compressed file from the pak.
    
    Compressed entries have an inline FPakEntry header before the compressed data:
        int64  Offset (relative, usually 0)
        int64  Size (compressed size)
        int64  UncompressedSize
        uint32 CompressionMethodIndex
        uint8[20] Hash
        int32  CompressionBlocksCount
        [CompressionBlocksCount * (int64 Start, int64 End)]
        uint8  bEncrypted
        uint32 CompressionBlockSize
    """
    pak_handle.seek(entry_info['offset'])
    
    # Read inline FPakEntry header
    _offset = struct.unpack('<q', pak_handle.read(8))[0]
    comp_size = struct.unpack('<q', pak_handle.read(8))[0]
    uncomp_size = struct.unpack('<q', pak_handle.read(8))[0]
    comp_method = struct.unpack('<I', pak_handle.read(4))[0]
    _hash = pak_handle.read(20)
    
    block_count = struct.unpack('<i', pak_handle.read(4))[0]
    blocks = []
    for _ in range(block_count):
        b_start = struct.unpack('<q', pak_handle.read(8))[0]
        b_end = struct.unpack('<q', pak_handle.read(8))[0]
        blocks.append((b_start, b_end))
    
    b_encrypted = struct.unpack('<B', pak_handle.read(1))[0]
    b_block_size = struct.unpack('<I', pak_handle.read(4))[0]
    
    data_offset = pak_handle.tell()
    
    if comp_method == 1:  # Zlib
        compressed = pak_handle.read(comp_size)
        return zlib.decompress(compressed)
    else:
        raise ValueError(f'Unsupported compression method: {comp_method}')


def parse_uasset_name_table(data: bytes) -> list[str]:
    """Parse the name table from a .uasset file.
    
    Returns list of name strings indexed by their position in the table.
    """
    s = io.BytesIO(data)
    
    # Package header
    tag = struct.unpack('<I', s.read(4))[0]
    if tag != 0x9E2A83C1:
        raise ValueError(f'Invalid .uasset magic: 0x{tag:08X}')
    
    legacy_ver = struct.unpack('<i', s.read(4))[0]
    legacy_ue3 = struct.unpack('<i', s.read(4))[0]
    ue4_ver = struct.unpack('<i', s.read(4))[0]
    licensee = struct.unpack('<i', s.read(4))[0]
    
    custom_ver_count = struct.unpack('<i', s.read(4))[0]
    for _ in range(custom_ver_count):
        s.read(16 + 4)  # GUID + version
    
    total_header = struct.unpack('<i', s.read(4))[0]
    folder = read_fstring(s)
    pkg_flags = struct.unpack('<I', s.read(4))[0]
    name_count = struct.unpack('<i', s.read(4))[0]
    name_offset = struct.unpack('<i', s.read(4))[0]
    
    # Read name table
    s.seek(name_offset)
    names = []
    for _ in range(name_count):
        name = read_fstring(s)
        _hash = struct.unpack('<I', s.read(4))[0]
        names.append(name)
    
    return names


def build_enum_mapping(uexp_data: bytes, uasset_data: bytes) -> dict[int, str]:
    """Build the NewEnumerator# -> display name mapping.
    
    Uses the .uasset name table to resolve FName indices from the .uexp
    DisplayNameMap to their actual NewEnumerator numbers.
    
    Returns dict mapping NewEnumerator number -> display name.
    """
    # Parse name table from .uasset
    name_table = parse_uasset_name_table(uasset_data)
    
    # Parse DisplayNameMap from .uexp
    display_entries = parse_enum_uexp(uexp_data)
    
    # Build mapping: resolve each FName index to its NewEnumerator number
    ne_pattern = re.compile(r'NewEnumerator(\d+)$')
    mapping = {}
    
    for entry in display_entries:
        fname_idx = entry['name_idx']
        display_name = entry['display_name']
        
        if fname_idx < len(name_table):
            name_str = name_table[fname_idx]
            m = ne_pattern.search(name_str)
            if m:
                ne_num = int(m.group(1))
                mapping[ne_num] = display_name
            else:
                print(f'  Warning: FName[{fname_idx}] = "{name_str}" does not match NewEnumerator pattern')
        else:
            print(f'  Warning: FName index {fname_idx} out of range (name table has {len(name_table)} entries)')
    
    return mapping


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
        uasset_entry = None
        for path, entry in target_files.items():
            if path.endswith('.uexp'):
                uexp_entry = entry
            elif path.endswith('.uasset'):
                uasset_entry = entry

        if not uexp_entry:
            print('ERROR: Enum_Professions.uexp not found!')
            sys.exit(1)

        # Extract .uexp (uncompressed)
        decoded_uexp = decode_entry(encoded_data, uexp_entry.encoded_offset)

        if not (0 < decoded_uexp['offset'] < file_size and 0 < decoded_uexp['size'] < 10 * 1024 * 1024):
            print(f'ERROR: Decoded .uexp entry has invalid offset/size:')
            print(f'  Offset: {decoded_uexp["offset"]}, Size: {decoded_uexp["size"]}')
            sys.exit(1)

        uexp_data = extract_file(f, decoded_uexp, AES_KEY)
        print(f'\nExtracted Enum_Professions.uexp: {len(uexp_data):,} bytes')

        # Save .uexp to output dir
        os.makedirs(args.output, exist_ok=True)
        out_path = os.path.join(args.output, 'Enum_Professions.uexp')
        with open(out_path, 'wb') as out:
            out.write(uexp_data)
        print(f'Saved to: {out_path}')

        # Extract .uasset (may be compressed)
        uasset_data = None
        if uasset_entry:
            decoded_uasset = decode_entry(encoded_data, uasset_entry.encoded_offset)
            
            try:
                if decoded_uasset.get('full_entry') or decoded_uasset['compression'] not in (0,):
                    # Compressed entry - use inline FPakEntry header approach
                    print('\nExtracting .uasset (compressed)...')
                    uasset_data = extract_compressed_file(f, decoded_uasset)
                else:
                    uasset_data = extract_file(f, decoded_uasset, AES_KEY)
            except Exception as e:
                print(f'Warning: Could not extract .uasset via standard method: {e}')
                print('Trying compressed extraction...')
                try:
                    uasset_data = extract_compressed_file(f, decoded_uasset)
                except Exception as e2:
                    print(f'ERROR: Could not extract .uasset: {e2}')
            
            if uasset_data:
                print(f'Extracted Enum_Professions.uasset: {len(uasset_data):,} bytes')
                out_path = os.path.join(args.output, 'Enum_Professions.uasset')
                with open(out_path, 'wb') as out:
                    out.write(uasset_data)
                print(f'Saved to: {out_path}')

        # Build the mapping
        if uasset_data:
            # Use .uasset name table for accurate NewEnumerator resolution
            mapping = build_enum_mapping(uexp_data, uasset_data)
        else:
            # Fallback: assume sequential ordering (may be inaccurate!)
            print('\nWARNING: Could not extract .uasset - falling back to sequential ordering.')
            print('This mapping may be WRONG if the enum has gaps in NewEnumerator numbers.')
            display_names = parse_enum_uexp(uexp_data)
            mapping = {i: dn['display_name'] for i, dn in enumerate(display_names)}

        if not mapping:
            print('\nERROR: Could not build enum mapping!')
            sys.exit(1)

        print(f'\n{"=" * 60}')
        print(f'  Enum_Professions Mapping ({len(mapping)} entries)')
        print(f'{"=" * 60}')
        print(f'  {"NE#":<6s} {"Display Name":<35s}')
        print(f'  {"-" * 41}')

        for ne_num in sorted(mapping.keys()):
            print(f'  {ne_num:<6d} {mapping[ne_num]}')

        # Output as Python dict for config.py
        print(f'\n{"=" * 60}')
        print('  Python dict for config.py:')
        print(f'{"=" * 60}')
        print('PROFESSIONS = {')
        for ne_num in sorted(mapping.keys()):
            print(f'    {ne_num}: {mapping[ne_num]!r},')
        print('}')


if __name__ == '__main__':
    main()
