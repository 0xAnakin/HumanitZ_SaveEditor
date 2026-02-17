"""Analyze SkillTree data structure for all players."""
import sys; sys.path.insert(0, 'src')
import struct
from utils import load_save, load_players
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE, PROFESSIONS

data = load_save('Save_MAZADedicatedSave1.sav')
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

# Relevant property names to search for
SKILLTREE_PROP = b'SkillTreeSaveData'
TREE_PROP = b'Tree_3_71EF7C2447EC923994A4BD8F4B59443E'
TYPE_PROP = b'Type_2_1204A3D84C6E61DFB0E01C814BBC366A'
INDEX_PROP = b'Index_5_299F9B8A4718F0B7021F2AB67F73882C'
LOCKED_PROP = b'Locked?_8_FD4426E545C1D540C0D8209102242DFD'
NEEDSPECIAL_PROP = b'NeedSpecialUnlock?_26_CDF5B48A4ACFEB670EB808964C2B3819'
EXP_PROP = b'Exp_11_D502E95A470B4DF13831B2B2B3CAA1A3'
EXPNEEDED_PROP = b'ExpNeeded_13_9BE2223F4EFEADF9F833749887E70955'
UNLOCKED_SKILLS_PROP = b'UnlockedSkills_18_ECD8BE254FC82D1298F10398C4BF1A23'

def read_bool_at(data, offset):
    """Read a BoolProperty value. Bool is stored as single byte after the property header."""
    # Property: name\0 + "BoolProperty\0" + size(8) + value(1) + guid(1)
    return data[offset] != 0

for p in players:
    print(f"\n{'='*70}")
    print(f"  {p['name']} (SteamID: {p['steam_id']})")
    print(f"{'='*70}")
    
    region = data[p['struct_start']:p['struct_end']]
    
    # Find SkillTreeSaveData
    st_idx = region.find(SKILLTREE_PROP)
    if st_idx == -1:
        print("  SkillTreeSaveData: NOT FOUND")
        continue
    
    # Find all Type entries (each represents a skill category)
    pos = 0
    entries = []
    while True:
        idx = region.find(TYPE_PROP, pos)
        if idx == -1:
            break
        
        abs_off = p['struct_start'] + idx
        
        # Read the ByteProperty value (E_SkillCatType::NewEnumeratorN)
        name_end = abs_off + len(TYPE_PROP) + 1
        tlen = struct.unpack_from('<i', data, name_end)[0]
        type_end = name_end + 4 + tlen
        size_off = type_end
        size = struct.unpack_from('<Q', data, size_off)[0]
        enum_type_off = size_off + 8
        enum_type_len = struct.unpack_from('<i', data, enum_type_off)[0]
        enum_type_str = data[enum_type_off+4:enum_type_off+4+enum_type_len-1].decode('ascii','replace')
        sep_off = enum_type_off + 4 + enum_type_len
        val_len_off = sep_off + 1
        val_len = struct.unpack_from('<i', data, val_len_off)[0]
        val_str = data[val_len_off+4:val_len_off+4+val_len-1].decode('ascii','replace')
        
        entry = {'type_str': val_str, 'abs_off': abs_off}
        
        # Find Index (IntProperty) nearby
        search_region = data[abs_off:abs_off+300]
        idx_off = search_region.find(INDEX_PROP)
        if idx_off != -1:
            idx_abs = abs_off + idx_off
            n_end = idx_abs + len(INDEX_PROP) + 1
            tl = struct.unpack_from('<i', data, n_end)[0]
            te = n_end + 4 + tl
            v_off = te + 8 + 1  # size(8) + guid(1)
            entry['index'] = struct.unpack_from('<i', data, v_off)[0]
        
        # Find Locked? (BoolProperty) nearby
        locked_off = search_region.find(LOCKED_PROP)
        if locked_off != -1:
            l_abs = abs_off + locked_off
            n_end = l_abs + len(LOCKED_PROP) + 1
            tl = struct.unpack_from('<i', data, n_end)[0]
            te = n_end + 4 + tl
            # BoolProperty: size(8, always 0) + value(1) + guid_flag(1)
            val_byte = data[te + 8]
            entry['locked'] = val_byte != 0
        
        # Find NeedSpecialUnlock? nearby
        nsu_off = search_region.find(NEEDSPECIAL_PROP)
        if nsu_off != -1:
            n_abs = abs_off + nsu_off
            n_end = n_abs + len(NEEDSPECIAL_PROP) + 1
            tl = struct.unpack_from('<i', data, n_end)[0]
            te = n_end + 4 + tl
            val_byte = data[te + 8]
            entry['need_special_unlock'] = val_byte != 0
        
        # Find Exp (FloatProperty) nearby 
        exp_off = search_region.find(EXP_PROP)
        if exp_off != -1:
            e_abs = abs_off + exp_off
            n_end = e_abs + len(EXP_PROP) + 1
            tl = struct.unpack_from('<i', data, n_end)[0]
            te = n_end + 4 + tl
            v_off = te + 8 + 1
            entry['exp'] = struct.unpack_from('<f', data, v_off)[0]
        
        # Find ExpNeeded nearby
        expn_off = search_region.find(EXPNEEDED_PROP)
        if expn_off != -1:
            e_abs = abs_off + expn_off
            n_end = e_abs + len(EXPNEEDED_PROP) + 1
            tl = struct.unpack_from('<i', data, n_end)[0]
            te = n_end + 4 + tl
            v_off = te + 8 + 1
            entry['exp_needed'] = struct.unpack_from('<f', data, v_off)[0]
        
        # Find UnlockedSkills count nearby (within 500 bytes)
        search_region2 = data[abs_off:abs_off+600]
        us_off = search_region2.find(UNLOCKED_SKILLS_PROP)
        if us_off != -1:
            u_abs = abs_off + us_off
            n_end = u_abs + len(UNLOCKED_SKILLS_PROP) + 1
            tl = struct.unpack_from('<i', data, n_end)[0]
            te = n_end + 4 + tl
            data_size = struct.unpack_from('<Q', data, te)[0]
            # Inner type
            inner_off = te + 8
            inner_len = struct.unpack_from('<i', data, inner_off)[0]
            inner_str = data[inner_off+4:inner_off+4+inner_len-1].decode('ascii','replace')
            # ... skip to count
            # After inner type: has_guid(1) then depends on StructProperty vs others
            # For StructProperty the header is more complex
            # Let's just find the count
            entry['unlocked_skills_type'] = inner_str
            # Try to find count after inner type
            if inner_str == 'StructProperty':
                # Skip: inner_type_len, inner_type, 0x00, then struct size, struct name, ...
                # Complex, let's just get data_size to estimate
                entry['unlocked_skills_data_size'] = data_size
            else:
                count_off = inner_off + 4 + inner_len + 1
                entry['unlocked_skills_count'] = struct.unpack_from('<i', data, count_off)[0]
        
        entries.append(entry)
        pos = idx + 1
    
    # Map known E_SkillCatType values
    skillcat_names = {
        'E_SkillCatType::NewEnumerator0': 'Weapons',
        'E_SkillCatType::NewEnumerator1': 'Survival',
        'E_SkillCatType::NewEnumerator2': 'Professions',
    }
    
    print(f"  Found {len(entries)} skill tree entries:\n")
    for e in entries:
        cat = skillcat_names.get(e['type_str'], e['type_str'])
        idx_val = e.get('index', '?')
        locked = e.get('locked', '?')
        nsu = e.get('need_special_unlock', '?')
        exp = e.get('exp', '?')
        exp_needed = e.get('exp_needed', '?')
        us_size = e.get('unlocked_skills_data_size', None)
        us_count = e.get('unlocked_skills_count', None)
        
        print(f"  [{idx_val}] {cat:20s} | Locked={locked!s:5s} | NeedSpecial={nsu!s:5s} | "
              f"Exp={exp!s:>10s} | ExpNeeded={exp_needed!s:>10s} | "
              f"Skills={'size='+str(us_size) if us_size else 'count='+str(us_count) if us_count is not None else '?'}")
