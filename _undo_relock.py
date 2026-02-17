"""Undo the re-lock: restore the 5 NE2 entries that were wrongly locked."""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils import load_save, load_players, write_save
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE

SAVE = 'Save_MAZADedicatedSave1.sav'
SKILL_CAT_NEEDLE = b'E_SkillCatType::NewEnumerator'
NE2_SUFFIX = b'2'

# These NE2 indices were Locked=0 before the bad fix
SHOULD_BE_UNLOCKED = {5, 6, 8, 9, 10}

data = load_save(SAVE)
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

anakin = next(p for p in players if p['name'] == '0xAnakin')
region_start = anakin['struct_start']
region_end = anakin['struct_end']
region = data[region_start:region_end]

fixed = 0
pos = 0
while True:
    idx = region.find(SKILL_CAT_NEEDLE, pos)
    if idx == -1:
        break

    try:
        end = region.index(b'\x00', idx)
    except ValueError:
        break
    cat_str = region[idx:end]
    cat_suffix = cat_str[len(SKILL_CAT_NEEDLE):]
    pos = idx + 1

    if cat_suffix != NE2_SUFFIX:
        continue

    window = region[idx:idx + 2000]

    # Get Index value
    idx_prop = window.find(b'Index_')
    if idx_prop == -1:
        continue
    ip_idx = window.find(b'IntProperty', idx_prop)
    if ip_idx == -1:
        continue
    val_off = ip_idx + len(b'IntProperty') + 1 + 8 + 1
    if val_off + 4 > len(window):
        continue
    index_val = struct.unpack_from('<i', window, val_off)[0]

    if index_val not in SHOULD_BE_UNLOCKED:
        continue

    # Find Locked? BoolProperty and set to 0
    locked_idx = window.find(b'Locked?')
    if locked_idx == -1:
        continue
    bp_idx = window.find(b'BoolProperty', locked_idx)
    if bp_idx == -1:
        continue
    locked_val_off = bp_idx + len(b'BoolProperty') + 1 + 8
    if locked_val_off >= len(window):
        continue

    abs_off = region_start + idx + locked_val_off
    old_val = data[abs_off]
    if old_val != 0:
        data = data[:abs_off] + b'\x00' + data[abs_off + 1:]
        print(f"  NE2 Index {index_val}: Locked {old_val} -> 0 (restored)")
        fixed += 1
    else:
        print(f"  NE2 Index {index_val}: already unlocked")

if fixed:
    write_save(SAVE, data)
    print(f"\nRestored {fixed} entries. Saved.")
else:
    print("\nNothing to restore.")
