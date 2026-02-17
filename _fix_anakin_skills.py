"""One-off fix: re-lock stale profession skill tree entries for 0xAnakin."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils import load_save, load_players, write_save
from edit_stats import find_players, relock_profession_skills
from config import DEFAULT_PLAYER_ID_FILE

SAVE = 'Save_MAZADedicatedSave1.sav'

data = load_save(SAVE)
players_map = load_players(DEFAULT_PLAYER_ID_FILE)
players = find_players(data, players_map)

anakin = next(p for p in players if p['name'] == '0xAnakin')
print(f"Player: {anakin['name']}  Profession: {anakin['profession']['display']}")

data, count = relock_profession_skills(data, anakin)
if count:
    write_save(SAVE, data)
    print(f"Re-locked {count} stale NE2 profession skill entries. Saved.")
else:
    print("No stale entries found — nothing to fix.")
