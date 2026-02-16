"""
HumanitZ Save Editor - Pak File Extractor
===========================================
Reads the encrypted UE4 Pak v11 index from HumanitZ's main pak file,
decrypts it with the AES key, and can:
  1. List all files in the pak (--list)
  2. Search for files by name (--search <pattern>)
  3. Extract specific uncompressed/unencrypted files (--extract <pattern>)

This is used to extract game data files like Enum_Professions.uasset/uexp
to build the profession enum mapping.

Usage:
    python pak_reader.py --list                       # List all files
    python pak_reader.py --search Enum_Professions    # Find files matching pattern
    python pak_reader.py --extract Enum_Professions   # Extract matching files

Requirements:
    pip install pycryptodome

Notes on Pak v11 Format:
    UE4 4.26+ uses Pak version 11, which uses a new index format with:
    - Encrypted index block (AES-256-ECB)
    - PathHashIndex (optional, for faster lookups)
    - FullDirectoryIndex (directory tree with encoded entry offsets)
    - Encoded entries (compact bitpacked format for file metadata)
    
    The encoded entry flags (uint32) have:
    - bits 0-5:   CompressionMethodIndex (0x3F = full entry follows)
    - bit 6:      bEncrypted
    - bits 7-17:  CompressionBlockCount (11 bits)
    - bit 29:     1 if Size fits in uint32
    - bit 30:     1 if UncompressedSize fits in uint32
    - bit 31:     1 if Offset fits in uint32
"""

import struct
import io
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PAK_FILE, AES_KEY, PAK_INFO_OFFSET
from utils import aes_decrypt_ecb, read_fstring


# ============================================================================
# PAK INDEX PARSING
# ============================================================================

class PakInfo:
    """Parsed Pak v11 footer/info block."""
    def __init__(self):
        self.magic = 0
        self.version = 0
        self.index_offset = 0
        self.index_size = 0
        self.index_hash = b''
        self.encrypted = False
        self.enc_key_guid = b''
        self.compression_methods = []


class PakDirectoryEntry:
    """A file entry from the Pak FullDirectoryIndex."""
    def __init__(self, path: str, encoded_offset: int):
        self.path = path                    # Full path like "HumanitZ/Content/..."
        self.encoded_offset = encoded_offset  # Byte offset into encoded entries blob
        self.decoded = None                  # Decoded entry data (populated later)


def read_pak_info(f, file_size: int) -> PakInfo:
    """Read the Pak info block from the end of the file."""
    info = PakInfo()
    f.seek(file_size - PAK_INFO_OFFSET)

    info.magic = struct.unpack('<I', f.read(4))[0]
    info.version = struct.unpack('<I', f.read(4))[0]
    info.index_offset = struct.unpack('<Q', f.read(8))[0]
    info.index_size = struct.unpack('<Q', f.read(8))[0]
    info.index_hash = f.read(20)
    info.encrypted = struct.unpack('<?', f.read(1))[0]
    info.enc_key_guid = f.read(16)

    comp_count = struct.unpack('<I', f.read(4))[0]
    for _ in range(comp_count):
        method_bytes = f.read(32)
        name = method_bytes.split(b'\x00')[0].decode('ascii', errors='replace')
        info.compression_methods.append(name)

    return info


def read_pak_index(f, pak_info: PakInfo, aes_key: bytes) -> tuple:
    """Read and decrypt the Pak v11 index. Returns (mount_point, num_entries, encoded_data, directory_entries).
    
    Pak v11 has a primary index block (at pak_info.index_offset) containing:
        FString MountPoint
        int32   NumEntries
        uint64  PathHashSeed
        int32   bHasPathHashIndex      (if 1: offset(int64), size(int64), hash(20))
        int32   bHasFullDirectoryIndex  (if 1: offset(int64), size(int64), hash(20))
        int32   EncodedEntriesSize
        bytes   EncodedEntries
    
    The FullDirectoryIndex is stored as a SEPARATE encrypted block in the
    pak file (at the offset specified above), NOT inline in the primary index.
    Its format is:
        int32 DirectoryCount
        For each directory:
            FString DirectoryName
            int32 FileCount
            For each file:
                FString FileName
                int32 EncodedEntryOffset  (byte offset into encoded_data)
    """
    f.seek(pak_info.index_offset)
    raw_index = f.read(pak_info.index_size)

    if pak_info.encrypted:
        decrypted = aes_decrypt_ecb(raw_index, aes_key)
    else:
        decrypted = raw_index

    idx = io.BytesIO(decrypted)

    mount_point = read_fstring(idx)
    num_entries = struct.unpack('<i', idx.read(4))[0]
    path_hash_seed = struct.unpack('<Q', idx.read(8))[0]

    # Skip PathHashIndex
    has_path_hash = struct.unpack('<i', idx.read(4))[0]
    if has_path_hash:
        path_hash_offset = struct.unpack('<q', idx.read(8))[0]
        path_hash_size = struct.unpack('<q', idx.read(8))[0]
        path_hash_hash = idx.read(20)

    # Read FullDirectoryIndex metadata (offset/size in pak file)
    has_full_dir = struct.unpack('<i', idx.read(4))[0]
    full_dir_offset = 0
    full_dir_size = 0
    if has_full_dir:
        full_dir_offset = struct.unpack('<q', idx.read(8))[0]
        full_dir_size = struct.unpack('<q', idx.read(8))[0]
        full_dir_hash = idx.read(20)

    # Read encoded entries blob
    encoded_size = struct.unpack('<i', idx.read(4))[0]
    encoded_data = idx.read(encoded_size)

    # Read the FullDirectoryIndex: it's a separate encrypted block in the pak file
    dir_entries = []
    if has_full_dir and full_dir_offset > 0 and full_dir_size > 0:
        f.seek(full_dir_offset)
        raw_dir = f.read(full_dir_size)
        if pak_info.encrypted:
            raw_dir = aes_decrypt_ecb(raw_dir, aes_key)
        dir_stream = io.BytesIO(raw_dir)
        try:
            dir_count = struct.unpack('<i', dir_stream.read(4))[0]
            for _ in range(dir_count):
                dir_name = read_fstring(dir_stream)
                file_count = struct.unpack('<i', dir_stream.read(4))[0]
                for _ in range(file_count):
                    file_name = read_fstring(dir_stream)
                    enc_offset = struct.unpack('<i', dir_stream.read(4))[0]
                    full_path = dir_name + file_name
                    dir_entries.append(PakDirectoryEntry(full_path, enc_offset))
        except Exception as e:
            print(f'Warning: FullDirectoryIndex parsing stopped: {e}')

    return mount_point, num_entries, encoded_data, dir_entries


def decode_entry(encoded_data: bytes, byte_offset: int) -> dict:
    """Decode a single encoded pak entry at the given byte offset.
    
    Returns dict with: offset, size, uncompressed_size, compression,
                       encrypted, full_entry, entry_size
    """
    s = io.BytesIO(encoded_data)
    s.seek(byte_offset)

    flags = struct.unpack('<I', s.read(4))[0]
    comp_method = flags & 0x3F

    if comp_method == 0x3F:
        # Full FPakEntry (not compact)
        offset = struct.unpack('<q', s.read(8))[0]
        size = struct.unpack('<q', s.read(8))[0]
        uncomp_size = struct.unpack('<q', s.read(8))[0]
        comp_method_real = struct.unpack('<I', s.read(4))[0]
        sha1_hash = s.read(20)
        enc_flags = struct.unpack('<B', s.read(1))[0]
        block_size = struct.unpack('<I', s.read(4))[0]
        entry_size = 4 + 8 + 8 + 8 + 4 + 20 + 1 + 4  # 57

        blocks = []
        if comp_method_real != 0:
            block_count = (flags >> 7) & 0x7FF
            for _ in range(block_count):
                bs = struct.unpack('<q', s.read(8))[0]
                be = struct.unpack('<q', s.read(8))[0]
                blocks.append((bs, be))
            entry_size += block_count * 16

        return {
            'full_entry': True,
            'offset': offset,
            'size': size,
            'uncompressed_size': uncomp_size,
            'compression': comp_method_real,
            'encrypted': bool(enc_flags & 1),
            'block_size': block_size,
            'entry_size': entry_size,
        }
    else:
        # Compact entry
        encrypted = bool(flags & (1 << 6))
        block_count = (flags >> 7) & 0x7FF
        offset_32 = bool(flags & (1 << 31))
        uncomp_32 = bool(flags & (1 << 30))
        size_32 = bool(flags & (1 << 29))

        offset = struct.unpack('<I', s.read(4))[0] if offset_32 else struct.unpack('<q', s.read(8))[0]
        uncomp_size = struct.unpack('<I', s.read(4))[0] if uncomp_32 else struct.unpack('<q', s.read(8))[0]

        if comp_method != 0:
            size = struct.unpack('<I', s.read(4))[0] if size_32 else struct.unpack('<q', s.read(8))[0]
        else:
            size = uncomp_size

        block_size = 0
        if comp_method != 0 and block_count > 0:
            block_size = struct.unpack('<I', s.read(4))[0]
            for _ in range(block_count):
                s.read(8)  # skip block start/end pairs

        return {
            'full_entry': False,
            'offset': offset,
            'size': size,
            'uncompressed_size': uncomp_size,
            'compression': comp_method,
            'encrypted': encrypted,
            'block_count': block_count,
            'block_size': block_size,
            'entry_size': s.tell() - byte_offset,
        }


# ============================================================================
# FILE EXTRACTION
# ============================================================================

def extract_file(pak_handle, entry_info: dict, aes_key: bytes) -> bytes:
    """Read raw file data from the pak at the decoded entry's offset.
    
    Only works for uncompressed files. If the file is encrypted (per-file),
    it will be AES-decrypted.
    
    Returns the file bytes, or raises ValueError for compressed entries.
    """
    if entry_info['compression'] not in (0, 0x3F):
        raise ValueError(
            f'File is compressed (method={entry_info["compression"]}). '
            f'Extraction of compressed files is not yet supported.'
        )

    pak_handle.seek(entry_info['offset'])
    data = pak_handle.read(entry_info['size'])

    if entry_info['encrypted']:
        data = aes_decrypt_ecb(data, aes_key)

    return data


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='HumanitZ Pak File Reader - Read/search/extract from encrypted UE4 pak files'
    )
    parser.add_argument('--pak', default=PAK_FILE,
                        help=f'Path to pak file (default: {PAK_FILE})')
    parser.add_argument('--list', action='store_true',
                        help='List all files in the pak')
    parser.add_argument('--search', metavar='PATTERN',
                        help='Search for files matching pattern (case-insensitive regex)')
    parser.add_argument('--extract', metavar='PATTERN',
                        help='Extract files matching pattern to --output directory')
    parser.add_argument('--output', '-o', default='.',
                        help='Output directory for extracted files (default: current dir)')
    parser.add_argument('--info', action='store_true',
                        help='Show pak file info only')

    args = parser.parse_args()

    if not os.path.exists(args.pak):
        print(f'Error: Pak file not found: {args.pak}')
        sys.exit(1)

    with open(args.pak, 'rb') as f:
        f.seek(0, 2)
        file_size = f.tell()

        pak_info = read_pak_info(f, file_size)

        if args.info or (not args.list and not args.search and not args.extract):
            print(f'Pak File:     {args.pak}')
            print(f'File Size:    {file_size:,} bytes ({file_size / 1024 / 1024 / 1024:.2f} GB)')
            print(f'Version:      {pak_info.version}')
            print(f'Index Offset: {pak_info.index_offset:,}')
            print(f'Index Size:   {pak_info.index_size:,}')
            print(f'Encrypted:    {pak_info.encrypted}')
            print(f'Compression:  {pak_info.compression_methods or "(none)"}')

            if not args.list and not args.search and not args.extract:
                print('\nUse --list, --search, or --extract for more operations.')
                return

        print('Reading and decrypting pak index...')
        mount_point, num_entries, encoded_data, dir_entries = read_pak_index(
            f, pak_info, AES_KEY
        )
        print(f'Mount point: {mount_point}')
        print(f'Total entries: {num_entries:,}')
        print(f'Directory entries parsed: {len(dir_entries):,}')
        print(f'Encoded data: {len(encoded_data):,} bytes')
        print()

        if args.list:
            for entry in dir_entries:
                print(entry.path)

        if args.search:
            pattern = re.compile(args.search, re.IGNORECASE)
            matches = [e for e in dir_entries if pattern.search(e.path)]
            print(f'Found {len(matches)} files matching "{args.search}":\n')
            for entry in matches:
                print(f'  {entry.path}  (encoded offset: {entry.encoded_offset})')

        if args.extract:
            pattern = re.compile(args.extract, re.IGNORECASE)
            matches = [e for e in dir_entries if pattern.search(e.path)]
            print(f'Found {len(matches)} files matching "{args.extract}":\n')

            os.makedirs(args.output, exist_ok=True)
            extracted = 0

            for entry in matches:
                try:
                    decoded = decode_entry(encoded_data, entry.encoded_offset)
                    entry.decoded = decoded

                    # Validate: offset and size must be reasonable
                    if not (0 < decoded['offset'] < file_size and
                            0 < decoded['size'] < 100 * 1024 * 1024):
                        print(f'  SKIP (invalid offset/size): {entry.path}')
                        print(f'       offset={decoded["offset"]}, size={decoded["size"]}')
                        continue

                    data = extract_file(f, decoded, AES_KEY)

                    # Write to output dir (flatten path: just use filename)
                    filename = os.path.basename(entry.path)
                    out_path = os.path.join(args.output, filename)
                    with open(out_path, 'wb') as out:
                        out.write(data)

                    print(f'  OK: {entry.path} -> {out_path} ({len(data):,} bytes)')
                    extracted += 1

                except Exception as e:
                    print(f'  ERROR: {entry.path} -> {e}')

            print(f'\nExtracted {extracted}/{len(matches)} files to {args.output}')


if __name__ == '__main__':
    main()
