"""Enhanced SkillTree dump with Index values and side-by-side comparison."""
import sys, struct; sys.path.insert(0, 'src')
from utils import load_save, load_players
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE

data = load_save('Save_MAZADedicatedSave1.sav')
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

cat_needle = b'E_SkillCatType::NewEnumerator'

def parse_skill_entries(region):
    """Parse all skill tree entries from a player region."""
    entries = []
    pos = 0
    while True:
        idx = region.find(cat_needle, pos)
        if idx == -1:
            break
        end = region.index(b'\x00', idx)
        cat_str = region[idx:end].decode('ascii')
        entry_region = region[idx:idx+2000]
        
        # Index IntProperty
        index_val = None
        idx_prop = entry_region.find(b'Index_')
        if idx_prop != -1:
            ip_idx = entry_region.find(b'IntProperty', idx_prop)
            if ip_idx != -1:
                val_off = ip_idx + len(b'IntProperty') + 1 + 8 + 1
                if val_off + 4 <= len(entry_region):
                    index_val = struct.unpack_from('<i', entry_region, val_off)[0]
        
        # Locked? BoolProperty
        locked_val = None
        locked_idx = entry_region.find(b'Locked?')
        if locked_idx != -1:
            bp_idx = entry_region.find(b'BoolProperty', locked_idx)
            if bp_idx != -1:
                val_off = bp_idx + len(b'BoolProperty') + 1 + 8
                if val_off < len(entry_region):
                    locked_val = entry_region[val_off]
        
        # NeedSpecialUnlock? BoolProperty
        need_special = None
        nsu_idx = entry_region.find(b'NeedSpecialUnlock?')
        if nsu_idx != -1:
            bp_idx = entry_region.find(b'BoolProperty', nsu_idx)
            if bp_idx != -1:
                val_off = bp_idx + len(b'BoolProperty') + 1 + 8
                if val_off < len(entry_region):
                    need_special = entry_region[val_off]
        
        # Exp FloatProperty
        exp_val = None
        exp_idx = entry_region.find(b'Exp_11_')
        if exp_idx != -1:
            fp_idx = entry_region.find(b'FloatProperty', exp_idx)
            if fp_idx != -1:
                val_off = fp_idx + len(b'FloatProperty') + 1 + 8 + 1
                if val_off + 4 <= len(entry_region):
                    exp_val = struct.unpack_from('<f', entry_region, val_off)[0]
        
        # ExpNeeded FloatProperty
        exp_needed = None
        en_idx = entry_region.find(b'ExpNeeded_13_')
        if en_idx != -1:
            fp_idx = entry_region.find(b'FloatProperty', en_idx)
            if fp_idx != -1:
                val_off = fp_idx + len(b'FloatProperty') + 1 + 8 + 1
                if val_off + 4 <= len(entry_region):
                    exp_needed = struct.unpack_from('<f', entry_region, val_off)[0]
        
        # UnlockedSkills count
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
        
        entries.append({
            'cat': cat_str,
            'cat_num': cat_str.split('NewEnumerator')[-1],
            'index': index_val,
            'locked': locked_val,
            'need_special': need_special,
            'exp': exp_val,
            'exp_needed': exp_needed,
            'unlocked_skills': unlocked_count,
        })
        pos = idx + 1
    return entries

for p in players:
    name = p['name']
    region = data[p['struct_start']:p['struct_end']]
    entries = parse_skill_entries(region)
    
    print(f"\n{'='*100}")
    print(f"  {name}'s Skill Tree ({len(entries)} entries)  |  Profession: {p.get('profession','?')}")
    print(f"{'='*100}")
    print(f"  {'Category':30s} {'Index':>5s}  {'Lock':>4s}  {'NSU':>3s}  {'Exp':>8s}  {'ExpNeed':>8s}  {'Skills':>6s}")
    print(f"  {'-'*30} {'-'*5}  {'-'*4}  {'-'*3}  {'-'*8}  {'-'*8}  {'-'*6}")
    
    for e in entries:
        cat_short = f"NE{e['cat_num']}"
        idx_s = str(e['index']) if e['index'] is not None else '?'
        lk_s = str(e['locked']) if e['locked'] is not None else '?'
        nsu_s = str(e['need_special']) if e['need_special'] is not None else '?'
        exp_s = f"{e['exp']:.0f}" if e['exp'] is not None else '-'
        en_s = f"{e['exp_needed']:.0f}" if e['exp_needed'] is not None else '-'
        uk_s = str(e['unlocked_skills']) if e['unlocked_skills'] is not None else '?'
        print(f"  {cat_short:30s} {idx_s:>5s}  {lk_s:>4s}  {nsu_s:>3s}  {exp_s:>8s}  {en_s:>8s}  {uk_s:>6s}")

# Side-by-side comparison of NE2 entries only (profession skills)
print(f"\n{'='*100}")
print("  Side-by-side: E_SkillCatType::NewEnumerator2 entries (profession skills)")
print(f"{'='*100}")

for p in players:
    region = data[p['struct_start']:p['struct_end']]
    entries = parse_skill_entries(region)
    ne2 = [e for e in entries if e['cat_num'] == '2']
    print(f"\n  {p['name']} ({p.get('profession','?')}):")
    for i, e in enumerate(ne2):
        idx_s = str(e['index']) if e['index'] is not None else '?'
        lk = 'LOCKED' if e['locked'] else 'OPEN'
        nsu = 'REQ-PROF' if e['need_special'] else 'GENERAL'
        skills = e['unlocked_skills'] or 0
        marker = ' <<<' if not e['locked'] and e['need_special'] else ''
        print(f"    [{i:2d}] Index={idx_s:>3s}  {lk:8s}  {nsu:10s}  Skills={skills}{marker}")
