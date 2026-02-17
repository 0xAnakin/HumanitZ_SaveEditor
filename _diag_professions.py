"""Deep diagnostic: dump ALL profession-related data for 0xAnakin.

Examines:
1. StartingPerk
2. UnlockedProfessionArr contents
3. NE2 skill tree entries (Index, Locked, NeedSpecialUnlock)
4. NeedSpecialUnlock flag comparison between players to find profession-specific mapping
"""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils import load_save, load_players, write_save
from edit_stats import find_players
from config import DEFAULT_PLAYER_ID_FILE, PROFESSIONS

SAVE = 'Save_MAZADedicatedSave1.sav'

data = load_save(SAVE)
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

SKILL_CAT_NEEDLE = b'E_SkillCatType::NewEnumerator'
NE2_SUFFIX = b'2'
ENUM_PREFIX = b'Enum_Professions::NewEnumerator'

def parse_ne2_entries(region):
    """Parse NE2 skill tree entries from a player region."""
    entries = []
    pos = 0
    while True:
        idx = region.find(SKILL_CAT_NEEDLE, pos)
        if idx == -1:
            break
        try:
            end = region.index(b'\x00', idx)
        except ValueError:
            break
        cat_suffix = region[idx + len(SKILL_CAT_NEEDLE):end]
        pos = idx + 1

        if cat_suffix != NE2_SUFFIX:
            continue

        window = region[idx:idx + 2000]

        # Index
        index_val = None
        idx_prop = window.find(b'Index_')
        if idx_prop != -1:
            ip_idx = window.find(b'IntProperty', idx_prop)
            if ip_idx != -1:
                val_off = ip_idx + len(b'IntProperty') + 1 + 8 + 1
                if val_off + 4 <= len(window):
                    index_val = struct.unpack_from('<i', window, val_off)[0]

        # Locked?
        locked_val = None
        locked_abs_off = None
        li = window.find(b'Locked?')
        if li != -1:
            bp = window.find(b'BoolProperty', li)
            if bp != -1:
                vo = bp + len(b'BoolProperty') + 1 + 8
                if vo < len(window):
                    locked_val = window[vo]
                    locked_abs_off = vo  # relative to window start

        # NeedSpecialUnlock?
        nsu_val = None
        nsu_abs_off = None
        ni = window.find(b'NeedSpecialUnlock?')
        if ni != -1:
            bp = window.find(b'BoolProperty', ni)
            if bp != -1:
                vo = bp + len(b'BoolProperty') + 1 + 8
                if vo < len(window):
                    nsu_val = window[vo]
                    nsu_abs_off = vo

        entries.append({
            'index': index_val,
            'locked': locked_val,
            'nsu': nsu_val,
            'locked_rel_off': locked_abs_off,
            'nsu_rel_off': nsu_abs_off,
            'cat_offset_in_region': idx,
        })
    return entries


def parse_unlocked_profession_arr(region):
    """Find and parse UnlockedProfessionArr contents."""
    needle = b'UnlockedProfessionArr'
    idx = region.find(needle)
    if idx == -1:
        return None, []

    # UnlockedProfessionArr -> ArrayProperty -> ByteProperty inner type
    # Then array count, then each element is an Enum_Professions::NewEnumeratorN FString
    window = region[idx:idx + 5000]
    
    # Find ArrayProperty
    ap = window.find(b'ArrayProperty')
    if ap == -1:
        return idx, []

    after_ap = ap + len(b'ArrayProperty') + 1  # +null
    arr_total_size = struct.unpack_from('<Q', window, after_ap)[0]

    # Inner type FString
    inner_off = after_ap + 8
    inner_len = struct.unpack_from('<i', window, inner_off)[0]
    inner_str = window[inner_off + 4:inner_off + 4 + inner_len - 1].decode('ascii', 'replace')

    # Separator byte
    sep_off = inner_off + 4 + inner_len
    
    # Count
    count_off = sep_off + 1
    count = struct.unpack_from('<i', window, count_off)[0]

    entries = []
    pos = count_off + 4
    for i in range(count):
        if pos + 4 > len(window):
            break
        slen = struct.unpack_from('<i', window, pos)[0]
        if slen <= 0 or slen > 200:
            break
        s = window[pos + 4:pos + 4 + slen - 1].decode('ascii', 'replace')
        entries.append(s)
        pos += 4 + slen

    return idx, entries


for p in players:
    name = p['name']
    region = data[p['struct_start']:p['struct_end']]
    prof = p.get('profession', {})

    print(f"\n{'='*80}")
    print(f"  {name}")
    print(f"{'='*80}")

    # 1. StartingPerk
    print(f"\n  StartingPerk: {prof.get('display', '?')} (NE{prof.get('enum_num', '?')})")

    # 2. UnlockedProfessionArr
    arr_off, arr_entries = parse_unlocked_profession_arr(region)
    if arr_off is not None:
        print(f"\n  UnlockedProfessionArr ({len(arr_entries)} entries):")
        for e in arr_entries:
            # extract enum num
            if 'NewEnumerator' in e:
                num = e.split('NewEnumerator')[-1]
                display = PROFESSIONS.get(int(num), f'Unknown({num})')
                print(f"    {e}  ->  {display}")
            else:
                print(f"    {e}")
    else:
        print("\n  UnlockedProfessionArr: NOT FOUND")

    # 3. NE2 entries
    ne2 = parse_ne2_entries(region)
    print(f"\n  NE2 Skill Tree Entries ({len(ne2)} entries):")
    print(f"  {'Idx':>3s}  {'Locked':>6s}  {'NeedSpecialUnlock':>17s}")
    print(f"  {'---':>3s}  {'------':>6s}  {'-'*17:>17s}")
    for e in ne2:
        idx_s = str(e['index']) if e['index'] is not None else '?'
        lk = str(e['locked']) if e['locked'] is not None else '?'
        nsu = str(e['nsu']) if e['nsu'] is not None else '?'
        lk_label = 'LOCKED' if e['locked'] else 'OPEN'
        nsu_label = 'REQ-PROF' if e['nsu'] else 'GENERAL'
        print(f"  {idx_s:>3s}  {lk_label:>6s}  {nsu_label:>17s}")

# Side-by-side NeedSpecialUnlock comparison
print(f"\n{'='*80}")
print(f"  NeedSpecialUnlock comparison (which indices are GENERAL per player)")
print(f"{'='*80}")
print(f"  {'Idx':>3s}  ", end="")
for p in players:
    print(f"  {p['name']:>15s}", end="")
print()
print(f"  {'---':>3s}  ", end="")
for p in players:
    print(f"  {'---------------':>15s}", end="")
print()

all_ne2 = {}
for p in players:
    region = data[p['struct_start']:p['struct_end']]
    ne2 = parse_ne2_entries(region)
    all_ne2[p['name']] = {e['index']: e for e in ne2}

max_idx = max(max(d.keys()) for d in all_ne2.values())
for i in range(max_idx + 1):
    print(f"  {i:>3d}  ", end="")
    for p in players:
        e = all_ne2[p['name']].get(i, {})
        nsu = e.get('nsu')
        locked = e.get('locked')
        if nsu is not None:
            nsu_label = 'GENERAL' if nsu == 0 else 'REQ-PROF'
            lk_label = 'OPEN' if locked == 0 else 'LOCKED'
            print(f"  {nsu_label+'/'+lk_label:>15s}", end="")
        else:
            print(f"  {'?':>15s}", end="")
    print()
