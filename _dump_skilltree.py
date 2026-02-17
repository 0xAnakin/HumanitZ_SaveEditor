"""Dump the full SkillTree structure for 0xAnakin to understand all fields."""
import sys, struct; sys.path.insert(0, 'src')
from utils import load_save, load_players
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE

data = load_save('Save_MAZADedicatedSave1.sav')
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

anakin = players[0]
region_start = anakin['struct_start']
region_end = anakin['struct_end']
region = data[region_start:region_end]

# Find SkillTreeSaveData in 0xAnakin's region
needle = b'SkillTreeSaveData'
idx = region.find(needle)
if idx == -1:
    print("No SkillTreeSaveData found for 0xAnakin")
    sys.exit(1)

abs_start = region_start + idx
print(f"SkillTreeSaveData found at offset 0x{abs_start:08X}")

# Now let's find E_SkillCatType entries to understand each skill tree category
cat_needle = b'E_SkillCatType::NewEnumerator'
pos = 0
entries = []
while True:
    idx = region.find(cat_needle, pos)
    if idx == -1:
        break
    # Read the full null-terminated string
    end = region.index(b'\x00', idx)
    cat_str = region[idx:end].decode('ascii')
    cat_num = cat_str.split('NewEnumerator')[-1]
    
    abs_off = region_start + idx
    
    # Now scan ahead for the fields in this entry
    # Look for Locked?, NeedSpecialUnlock?, Exp, ExpNeeded, UnlockedSkills
    entry_region = region[idx:idx+2000]  # enough for one entry
    
    locked_val = None
    need_special = None
    exp_val = None
    exp_needed = None
    unlocked_count = None
    
    # Find Locked? BoolProperty
    locked_idx = entry_region.find(b'Locked?')
    if locked_idx != -1:
        # BoolProperty: name\0 + "BoolProperty\0" + size(8) + value(1)
        # Find the BoolProperty type after Locked?
        bp_idx = entry_region.find(b'BoolProperty', locked_idx)
        if bp_idx != -1:
            # value is at bp_idx + len("BoolProperty") + 1 + 8
            val_off = bp_idx + len(b'BoolProperty') + 1 + 8
            if val_off < len(entry_region):
                locked_val = entry_region[val_off]
    
    # Find NeedSpecialUnlock? BoolProperty
    nsu_idx = entry_region.find(b'NeedSpecialUnlock?')
    if nsu_idx != -1:
        bp_idx = entry_region.find(b'BoolProperty', nsu_idx)
        if bp_idx != -1:
            val_off = bp_idx + len(b'BoolProperty') + 1 + 8
            if val_off < len(entry_region):
                need_special = entry_region[val_off]
    
    # Find Exp FloatProperty
    exp_idx = entry_region.find(b'Exp_11_')
    if exp_idx != -1:
        fp_idx = entry_region.find(b'FloatProperty', exp_idx)
        if fp_idx != -1:
            val_off = fp_idx + len(b'FloatProperty') + 1 + 8 + 1
            if val_off + 4 <= len(entry_region):
                exp_val = struct.unpack_from('<f', entry_region, val_off)[0]
    
    # Find ExpNeeded FloatProperty
    en_idx = entry_region.find(b'ExpNeeded_13_')
    if en_idx != -1:
        fp_idx = entry_region.find(b'FloatProperty', en_idx)
        if fp_idx != -1:
            val_off = fp_idx + len(b'FloatProperty') + 1 + 8 + 1
            if val_off + 4 <= len(entry_region):
                exp_needed = struct.unpack_from('<f', entry_region, val_off)[0]
    
    # Find UnlockedSkills array count
    us_idx = entry_region.find(b'UnlockedSkills')
    if us_idx != -1:
        # Find ArrayProperty after it
        ap_idx = entry_region.find(b'ArrayProperty', us_idx)
        if ap_idx != -1:
            # ArrayProperty layout: "ArrayProperty\0" + size(8) + innerType(FString) + hasGuid(1) + count(4)
            after_ap = ap_idx + len(b'ArrayProperty') + 1
            arr_size = struct.unpack_from('<Q', entry_region, after_ap)[0]
            # Find inner type
            inner_len = struct.unpack_from('<i', entry_region, after_ap + 8)[0]
            inner_end = after_ap + 8 + 4 + inner_len
            count_off = inner_end + 1  # +1 for hasGuid byte
            if count_off + 4 <= len(entry_region):
                unlocked_count = struct.unpack_from('<i', entry_region, count_off)[0]
    
    entries.append({
        'cat': cat_str,
        'cat_num': cat_num,
        'offset': abs_off,
        'locked': locked_val,
        'need_special': need_special,
        'exp': exp_val,
        'exp_needed': exp_needed,
        'unlocked_skills_count': unlocked_count,
    })
    
    pos = idx + 1

print(f"\n{'='*80}")
print(f"  0xAnakin's Skill Tree Entries ({len(entries)} categories)")
print(f"{'='*80}")
for e in entries:
    locked_str = f"Locked={e['locked']}" if e['locked'] is not None else "Locked=?"
    nsu_str = f"NeedSpecialUnlock={e['need_special']}" if e['need_special'] is not None else "NeedSpecialUnlock=?"
    exp_str = f"Exp={e['exp']:.1f}" if e['exp'] is not None else "Exp=?"
    en_str = f"ExpNeeded={e['exp_needed']:.1f}" if e['exp_needed'] is not None else "ExpNeeded=?"
    us_str = f"UnlockedSkills={e['unlocked_skills_count']}" if e['unlocked_skills_count'] is not None else "UnlockedSkills=?"
    print(f"  {e['cat']:45s} | {locked_str:10s} | {nsu_str:20s} | {exp_str:15s} | {en_str:20s} | {us_str}")

# Now do the same for raybanme for comparison
print(f"\n{'='*80}")
raybanme = players[1]
region2 = data[raybanme['struct_start']:raybanme['struct_end']]
pos = 0
entries2 = []
while True:
    idx = region2.find(cat_needle, pos)
    if idx == -1:
        break
    end = region2.index(b'\x00', idx)
    cat_str = region2[idx:end].decode('ascii')
    entry_region = region2[idx:idx+2000]
    
    locked_val = None
    locked_idx = entry_region.find(b'Locked?')
    if locked_idx != -1:
        bp_idx = entry_region.find(b'BoolProperty', locked_idx)
        if bp_idx != -1:
            val_off = bp_idx + len(b'BoolProperty') + 1 + 8
            if val_off < len(entry_region):
                locked_val = entry_region[val_off]
    
    need_special = None
    nsu_idx = entry_region.find(b'NeedSpecialUnlock?')
    if nsu_idx != -1:
        bp_idx = entry_region.find(b'BoolProperty', nsu_idx)
        if bp_idx != -1:
            val_off = bp_idx + len(b'BoolProperty') + 1 + 8
            if val_off < len(entry_region):
                need_special = entry_region[val_off]
    
    unlocked_count = None
    us_idx = entry_region.find(b'UnlockedSkills')
    if us_idx != -1:
        ap_idx = entry_region.find(b'ArrayProperty', us_idx)
        if ap_idx != -1:
            after_ap = ap_idx + len(b'ArrayProperty') + 1
            inner_len = struct.unpack_from('<i', entry_region, after_ap + 8)[0]
            inner_end = after_ap + 8 + 4 + inner_len
            count_off = inner_end + 1
            if count_off + 4 <= len(entry_region):
                unlocked_count = struct.unpack_from('<i', entry_region, count_off)[0]
    
    entries2.append({
        'cat': cat_str,
        'locked': locked_val,
        'need_special': need_special,
        'unlocked_skills_count': unlocked_count,
    })
    pos = idx + 1

print(f"  raybanme's Skill Tree Entries ({len(entries2)} categories)")
print(f"{'='*80}")
for e in entries2:
    locked_str = f"Locked={e['locked']}" if e['locked'] is not None else "Locked=?"
    nsu_str = f"NeedSpecialUnlock={e['need_special']}" if e['need_special'] is not None else "NeedSpecialUnlock=?"
    us_str = f"UnlockedSkills={e['unlocked_skills_count']}" if e['unlocked_skills_count'] is not None else "UnlockedSkills=?"
    print(f"  {e['cat']:45s} | {locked_str:10s} | {nsu_str:20s} | {us_str}")
