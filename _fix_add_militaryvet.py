"""Fix: Add MilitaryVet (NE14) to 0xAnakin's UnlockedProfessionArr."""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils import load_save, load_players, write_save
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE

SAVE = 'Save_MAZADedicatedSave1.sav'

data = load_save(SAVE)
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

anakin = next(p for p in players if p['name'] == '0xAnakin')
region_start = anakin['struct_start']
region = data[region_start:anakin['struct_end']]

PROP_NAME = b'UnlockedProfessionArr_17_2528BAE945B7A3B1A49D7893990D13BF'
idx = region.find(PROP_NAME)
if idx == -1:
    print("UnlockedProfessionArr not found!")
    sys.exit(1)

abs_base = region_start + idx
chunk = data[abs_base:]

# Parse the header to find exact offsets
pos = len(PROP_NAME) + 1           # skip name + null
type_len = struct.unpack_from('<i', chunk, pos)[0]
pos += 4 + type_len                 # skip type FString ("ArrayProperty\0")

prop_size_abs = abs_base + pos       # offset of PropertySize in data
prop_size_val = struct.unpack_from('<Q', chunk, pos)[0]
pos += 8

inner_len = struct.unpack_from('<i', chunk, pos)[0]
pos += 4 + inner_len                # skip inner type FString ("ByteProperty\0")
pos += 1                            # separator byte

count_abs = abs_base + pos           # offset of ArrayCount in data
count_val = struct.unpack_from('<i', chunk, pos)[0]
pos += 4

# Skip existing entries
for i in range(count_val):
    entry_len = struct.unpack_from('<i', chunk, pos)[0]
    pos += 4 + entry_len

insert_abs = abs_base + pos          # where new entry goes

print(f"Current ArrayCount: {count_val}")
print(f"Current PropertySize: {prop_size_val}")
print(f"Insert point: 0x{insert_abs:08X}")

# Build the new entry: FString for "Enum_Professions::NewEnumerator14\0"
new_enum = b'Enum_Professions::NewEnumerator14\x00'
new_entry = struct.pack('<i', len(new_enum)) + new_enum
print(f"New entry: {len(new_entry)} bytes -> {new_enum[:-1].decode()}")

# 1. Insert the entry bytes
data = data[:insert_abs] + new_entry + data[insert_abs:]

# 2. Update ArrayCount (count_abs hasn't shifted, it's before insertion point)
new_count = count_val + 1
data = data[:count_abs] + struct.pack('<i', new_count) + data[count_abs + 4:]

# 3. Update PropertySize
new_size = prop_size_val + len(new_entry)
data = data[:prop_size_abs] + struct.pack('<Q', new_size) + data[prop_size_abs + 8:]

print(f"New ArrayCount: {new_count}")
print(f"New PropertySize: {new_size}")
print(f"File size changed by +{len(new_entry)} bytes")

write_save(SAVE, data)
print("Done! Saved.")

# Verify
data = load_save(SAVE)
players = find_players(data, players_map)
anakin = next(p for p in players if p['name'] == '0xAnakin')
region = data[anakin['struct_start']:anakin['struct_end']]
idx = region.find(PROP_NAME)
chunk = region[idx:]
pos = len(PROP_NAME) + 1
type_len = struct.unpack_from('<i', chunk, pos)[0]
pos += 4 + type_len
pos += 8  # skip size
inner_len = struct.unpack_from('<i', chunk, pos)[0]
pos += 4 + inner_len + 1
count = struct.unpack_from('<i', chunk, pos)[0]
pos += 4
print(f"\nVerification — UnlockedProfessionArr now has {count} entries:")
for i in range(count):
    elen = struct.unpack_from('<i', chunk, pos)[0]
    estr = chunk[pos+4:pos+4+elen-1].decode()
    print(f"  [{i}] {estr}")
    pos += 4 + elen
