"""Hex dump the UnlockedProfessionArr for both players to understand binary layout."""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils import load_save, load_players
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE

SAVE = 'Save_MAZADedicatedSave1.sav'
data = load_save(SAVE)
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

NEEDLE = b'UnlockedProfessionArr'

for p in players:
    region = data[p['struct_start']:p['struct_end']]
    idx = region.find(NEEDLE)
    if idx == -1:
        print(f"\n{p['name']}: UnlockedProfessionArr NOT FOUND")
        continue
    
    abs_off = p['struct_start'] + idx
    # Dump 300 bytes from the start of the property name
    chunk = data[abs_off:abs_off + 400]
    
    print(f"\n{'='*80}")
    print(f"  {p['name']} — UnlockedProfessionArr at offset 0x{abs_off:08X}")
    print(f"{'='*80}")
    
    # Annotated parse
    pos = 0
    # Property name
    name_end = chunk.index(b'\x00', pos) + 1
    print(f"  [0x{pos:03X}] PropertyName: {chunk[pos:name_end-1].decode()}")
    pos = name_end
    
    # Type name (FString: len + str)
    type_len = struct.unpack_from('<i', chunk, pos)[0]
    type_str = chunk[pos+4:pos+4+type_len-1].decode()
    print(f"  [0x{pos:03X}] TypeLen={type_len}, TypeStr={type_str}")
    pos += 4 + type_len
    
    # Property size (8 bytes)
    prop_size = struct.unpack_from('<Q', chunk, pos)[0]
    print(f"  [0x{pos:03X}] PropertySize={prop_size}")
    prop_size_off = pos  # remember for fixing
    pos += 8
    
    # Inner type (FString)
    inner_len = struct.unpack_from('<i', chunk, pos)[0]
    inner_str = chunk[pos+4:pos+4+inner_len-1].decode()
    print(f"  [0x{pos:03X}] InnerTypeLen={inner_len}, InnerType={inner_str}")
    pos += 4 + inner_len
    
    # Separator byte
    sep = chunk[pos]
    print(f"  [0x{pos:03X}] Separator=0x{sep:02X}")
    pos += 1
    
    # Array count
    count = struct.unpack_from('<i', chunk, pos)[0]
    print(f"  [0x{pos:03X}] ArrayCount={count}")
    count_off = pos
    pos += 4
    
    # Array entries
    for i in range(count):
        entry_len = struct.unpack_from('<i', chunk, pos)[0]
        entry_str = chunk[pos+4:pos+4+entry_len-1].decode()
        print(f"  [0x{pos:03X}] [{i}] EntryLen={entry_len}, Entry={entry_str}")
        pos += 4 + entry_len
    
    print(f"  [0x{pos:03X}] <-- end of array data")
    print(f"  Total array data size (from after inner type+sep to end): {pos - count_off}")
    print(f"  PropertySize field stores: {prop_size}")
    
    # Hex dump
    dump_len = min(pos + 20, len(chunk))
    print(f"\n  Raw hex dump (0x{abs_off:08X} +{dump_len} bytes):")
    for row in range(0, dump_len, 16):
        hex_part = ' '.join(f'{chunk[row+j]:02X}' if row+j < dump_len else '  ' for j in range(16))
        asc_part = ''.join(chr(chunk[row+j]) if 32 <= chunk[row+j] < 127 else '.' for j in range(16) if row+j < dump_len)
        print(f"    {row:04X}: {hex_part}  {asc_part}")
