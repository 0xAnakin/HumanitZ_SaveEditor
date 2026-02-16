"""
HumanitZ Save Editor - Core Utilities
=======================================
Shared functions for reading GVAS save files, AES decryption,
binary searching, UE4 data parsing, and player ID loading.
"""

import struct
import io
import os
import re

try:
    from Crypto.Cipher import AES as PyCryptoAES
    HAS_PYCRYPTODOME = True
except ImportError:
    HAS_PYCRYPTODOME = False


# ============================================================================
# AES DECRYPTION
# ============================================================================

def aes_decrypt_ecb(data: bytes, key: bytes) -> bytes:
    """Decrypt data using AES-256-ECB. Pads input to a 16-byte boundary.
    
    Requires pycryptodome: pip install pycryptodome
    """
    if not HAS_PYCRYPTODOME:
        raise ImportError(
            'pycryptodome is required for AES decryption.\n'
            'Install it with: pip install pycryptodome'
        )
    cipher = PyCryptoAES.new(key, PyCryptoAES.MODE_ECB)
    padded_size = (len(data) + 15) & ~15
    padded = data + b'\x00' * (padded_size - len(data))
    return cipher.decrypt(padded)[:len(data)]


# ============================================================================
# BINARY SEARCH HELPERS
# ============================================================================

def find_all_bytes(data: bytes, needle: bytes) -> list[int]:
    """Find all occurrences of `needle` in `data`. Returns list of offsets."""
    results = []
    start = 0
    while True:
        idx = data.find(needle, start)
        if idx == -1:
            break
        results.append(idx)
        start = idx + 1
    return results


def read_null_terminated(data: bytes, offset: int) -> str:
    """Read a null-terminated ASCII string starting at `offset`."""
    end = data.index(b'\x00', offset)
    return data[offset:end].decode('ascii', errors='replace')


def find_nearest_player(data: bytes, offset: int, players: dict,
                        max_range: int = 100000) -> tuple[str | None, int]:
    """Find which player a byte offset belongs to by searching for nearby SteamIDs.
    
    Args:
        data: Full save file bytes.
        offset: The byte offset to search around.
        players: Dict of {steam_id_str: display_name}.
        max_range: How far to search in each direction (default 100KB).
    
    Returns:
        (player_name, distance) or (None, max_range+1) if none found.
    """
    search_start = max(0, offset - max_range)
    search_end = min(len(data), offset + max_range)
    region = data[search_start:search_end]

    best_player = None
    best_dist = max_range + 1

    for steam_id, name in players.items():
        steam_bytes = steam_id.encode('ascii')
        pos = 0
        while True:
            idx = region.find(steam_bytes, pos)
            if idx == -1:
                break
            abs_pos = search_start + idx
            dist = abs(abs_pos - offset)
            if dist < best_dist:
                best_dist = dist
                best_player = name
            pos = idx + 1

    return best_player, best_dist


# ============================================================================
# GVAS HEADER PARSER
# ============================================================================

class GvasHeader:
    """Parsed GVAS (UE4 save file) header."""
    def __init__(self):
        self.magic = 0
        self.save_game_version = 0
        self.package_version = 0
        self.engine_version_major = 0
        self.engine_version_minor = 0
        self.engine_version_patch = 0
        self.engine_version_changelist = 0
        self.engine_version_branch = ''
        self.custom_version_format = 0
        self.custom_version_count = 0
        self.custom_versions = []
        self.save_game_class = ''
        self.header_size = 0

    def __repr__(self):
        return (
            f'GvasHeader(magic=0x{self.magic:08X}, '
            f'save_ver={self.save_game_version}, '
            f'pkg_ver={self.package_version}, '
            f'engine={self.engine_version_major}.{self.engine_version_minor}.{self.engine_version_patch}, '
            f'class="{self.save_game_class}")'
        )


def read_fstring(stream: io.BytesIO) -> str:
    """Read a UE4 FString (int32 length + data + null terminator).
    Handles both ASCII (positive length) and UTF-16 (negative length).
    """
    length = struct.unpack('<i', stream.read(4))[0]
    if length == 0:
        return ''
    if length < 0:
        # UTF-16 encoded
        count = -length
        raw = stream.read(count * 2)
        return raw.decode('utf-16-le').rstrip('\x00')
    else:
        raw = stream.read(length)
        return raw.decode('utf-8', errors='replace').rstrip('\x00')


def parse_gvas_header(data: bytes) -> GvasHeader:
    """Parse the GVAS header from a save file.
    
    GVAS Header Layout (UE4 4.27):
        uint32  Magic               (0x53415647 = "GVAS")
        uint32  SaveGameVersion     (2 for current saves)
        uint32  PackageVersion      (522 for UE4 4.27)
        uint16  EngineMajor
        uint16  EngineMinor
        uint16  EnginePatch
        uint32  EngineChangelist
        FString EngineBranch        (e.g. "++UE4+Release-4.27")
        int32   CustomVersionFormat (3 = Guids format)
        int32   CustomVersionCount
        [CustomVersionCount × (GUID(16) + int32(4))]
        FString SaveGameClass
    """
    s = io.BytesIO(data)
    h = GvasHeader()

    h.magic = struct.unpack('<I', s.read(4))[0]
    if h.magic != 0x53415647:
        raise ValueError(f'Not a GVAS file: magic=0x{h.magic:08X}, expected 0x53415647')

    h.save_game_version = struct.unpack('<I', s.read(4))[0]
    h.package_version = struct.unpack('<I', s.read(4))[0]

    h.engine_version_major = struct.unpack('<H', s.read(2))[0]
    h.engine_version_minor = struct.unpack('<H', s.read(2))[0]
    h.engine_version_patch = struct.unpack('<H', s.read(2))[0]
    # No padding — changelist (uint32) follows immediately after patch (uint16)
    h.engine_version_changelist = struct.unpack('<I', s.read(4))[0]
    h.engine_version_branch = read_fstring(s)

    # CustomVersionFormat: serialization format for custom versions
    # (3 = Guids: each entry is GUID(16 bytes) + int32(4 bytes))
    h.custom_version_format = struct.unpack('<i', s.read(4))[0]
    h.custom_version_count = struct.unpack('<I', s.read(4))[0]
    h.custom_versions = []
    for _ in range(h.custom_version_count):
        guid = s.read(16)
        version = struct.unpack('<i', s.read(4))[0]
        h.custom_versions.append((guid, version))

    h.save_game_class = read_fstring(s)
    h.header_size = s.tell()

    return h


# ============================================================================
# UE4 PROPERTY SCANNER
# ============================================================================

def scan_enum_properties(data: bytes, enum_type: str = 'Enum_Professions') -> list[dict]:
    """Scan raw save data for all occurrences of a specific enum type.
    
    Returns list of dicts with keys:
        offset: byte offset of the enum value string
        enum_str: full string like "Enum_Professions::NewEnumerator14"
        enum_num: the integer N from NewEnumeratorN
        context: the property name this belongs to (StartingPerk, UnlockedProfessionArr, etc.)
        length_prefix_offset: offset of the int32 FString length prefix
        length_prefix_ok: whether the length prefix matches
    """
    needle = f'{enum_type}::NewEnumerator'.encode('ascii')
    locations = find_all_bytes(data, needle)

    entries = []
    for loc in locations:
        # Read full null-terminated string
        end = data.index(b'\x00', loc)
        enum_str = data[loc:end].decode('ascii')

        # Extract the enumerator number
        num_str = enum_str.split('NewEnumerator')[-1]
        try:
            enum_num = int(num_str)
        except ValueError:
            enum_num = -1

        # Determine context by looking backwards for known property names
        search_back = data[max(0, loc - 500):loc]
        if b'StartingPerk' in search_back:
            context = 'StartingPerk'
        elif b'UnlockedProfessionArr' in search_back:
            context = 'UnlockedProfessionArr'
        else:
            context = 'Unknown'

        # Validate the FString length prefix at offset-4
        prefix_offset = loc - 4
        stored_len = struct.unpack_from('<i', data, prefix_offset)[0]
        actual_len = len(enum_str) + 1  # +1 for null terminator
        length_ok = (stored_len == actual_len)

        entries.append({
            'offset': loc,
            'enum_str': enum_str,
            'enum_num': enum_num,
            'context': context,
            'length_prefix_offset': prefix_offset,
            'length_prefix_ok': length_ok,
            'end': end + 1,
        })

    return entries


def scan_string_properties(data: bytes, search_str: str) -> list[int]:
    """Find all occurrences of a plain string in save data."""
    return find_all_bytes(data, search_str.encode('ascii'))


# ============================================================================
# SAVE FILE I/O
# ============================================================================

def load_save(filepath: str) -> bytes:
    """Load a save file and return its raw bytes."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Save file not found: {filepath}')
    with open(filepath, 'rb') as f:
        return f.read()


def write_save(filepath: str, data: bytes) -> None:
    """Write raw bytes to a save file."""
    with open(filepath, 'wb') as f:
        f.write(data)


# ============================================================================
# PLAYER ID LOADING
# ============================================================================

def load_players(filepath: str) -> dict[str, str]:
    """Load player SteamID -> display name mapping from a PlayerIDMapped.txt file.
    
    The file is exported from a HumanitZ dedicated server. Each line has the format:
        <SteamID64>_+_|<InternalID>@<DisplayName>
    
    Example:
        76561198142478391_+_|00028ce6e7d54af2968d8aff2e694375@0xAnakin
    
    Args:
        filepath: Path to the PlayerIDMapped.txt file.
    
    Returns:
        Dict mapping SteamID64 string -> display name string.
    
    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains no valid player entries.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f'Player ID file not found: {filepath}\n'
            f'Copy PlayerIDMapped.txt from your HumanitZ dedicated server\n'
            f'(usually in the server\'s Saved/SaveGames/ directory).'
        )
    
    players = {}
    line_pattern = re.compile(r'^(\d{10,20})_\+_\|[0-9a-f]+@(.+)$')
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            m = line_pattern.match(line)
            if m:
                steam_id = m.group(1)
                display_name = m.group(2)
                players[steam_id] = display_name
            else:
                print(f'  Warning: Skipping malformed line {line_num} in {filepath}')
    
    if not players:
        raise ValueError(
            f'No valid player entries found in {filepath}\n'
            f'Expected format: <SteamID64>_+_|<InternalID>@<DisplayName>'
        )
    
    return players
