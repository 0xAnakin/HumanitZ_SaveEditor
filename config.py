"""
HumanitZ Save Editor - Configuration
======================================
Central configuration for paths, keys, and game data constants.
Edit the values in this file to match your environment.
"""

# ============================================================================
# PATHS
# ============================================================================

# Default dedicated server save file path
DEFAULT_SAVE_FILE = r'c:\Users\p0ffer\Desktop\SaveGames\SaveList\Default\Save_MAZADedicatedSave1.sav'

# HumanitZ game installation directory
GAME_DIR = r'e:\Steam\steamapps\common\HumanitZ'

# Main game pak file
PAK_FILE = GAME_DIR + r'\HumanitZ\Content\Paks\pakchunk0-WindowsNoEditor.pak'

# Local save directory (single player)
LOCAL_SAVE_DIR = r'C:\Users\p0ffer\AppData\Local\HumanitZ\Saved\SaveGames'

# ============================================================================
# AES ENCRYPTION KEY
# ============================================================================
# From the HumanitZ Unofficial Modding Guide on Steam:
# https://steamcommunity.com/sharedfiles/filedetails/?id=3035793498
AES_KEY_HEX = '321166CACD1E2BBEAC9794AAF468DE277001D2EF8F74A8D6B3CC6EDFE87945CA'
AES_KEY = bytes.fromhex(AES_KEY_HEX)

# ============================================================================
# GAME DATA: Enum_Professions
# ============================================================================
# Extracted from HumanitZ/Content/Coredamage/Data/Enum_Professions.uasset/.uexp
# inside the encrypted pak file (pakchunk0-WindowsNoEditor.pak).
#
# The enum is a UE4 UserDefinedEnum (Blueprint enum).
# In save files, the active profession is stored as:
#   Property: StartingPerk_94_283EA71B427B7E97C43350818608A5E4
#   Type:     ByteProperty
#   Enum:     Enum_Professions
#   Value:    Enum_Professions::NewEnumeratorN
#
# Unlocked professions are stored as:
#   Property: UnlockedProfessionArr_17_2528BAE945B7A3B1A49D7893990D13BF
#   Type:     ArrayProperty of ByteProperty
#   Values:   [Enum_Professions::NewEnumeratorN, ...]

PROFESSIONS = {
    0:  'Unemployed',
    1:  'AmateurBoxer',
    2:  'Farmer',
    3:  'Mechanic',
    4:  'JuniorBiodiesel Researcher',
    5:  'EmergencyMedicalTechnician',
    6:  'ApprenticeGunsmith',
    7:  'FoodServiceWorker',
    8:  'SundayFisherman',
    9:  'CarSalesman',
    10: 'Outdoorsman',
    11: 'Chemist',
    12: 'EMT',
    13: 'MilitaryVet',
    14: 'Thief',
    15: 'FireFighter',
    16: 'ElectricalEngineer',
}

# Reverse lookup: name -> enum index
PROFESSION_BY_NAME = {v.lower(): k for k, v in PROFESSIONS.items()}

# ============================================================================
# GAME DATA: Known Players (edit to match your server)
# ============================================================================
# Format: SteamID64 -> display name
# You can find SteamID64 from the PlayerIDMapped.txt file or in-game admin tools.
PLAYERS = {
    '76561198142478391': '0xAnakin',
    '76561198108344973': 'raybanme',
    '76561198144568733': 'Johnny Kopo',
}

# ============================================================================
# SAVE FILE FORMAT CONSTANTS
# ============================================================================

# GVAS (GameVersionedArchiveSerializer) header magic
GVAS_MAGIC = 0x53415647  # "GVAS" in little-endian

# UE4 engine version string found in saves
UE4_ENGINE_VERSION = '++UE4+Release-4.27'

# Save game class path (BP_HumanitzSave)
SAVE_GAME_CLASS = '/Game/TSS_Game/Blueprints/Objective_System/System/BP_HumanitzSave.BP_HumanitzSave_C'

# Pak file version (UE4 4.27 = Pak v11)
PAK_VERSION = 11

# Pak footer size: magic(4) + version(4) + indexOffset(8) + indexSize(8) +
#                  indexHash(20) + encrypted(1) + encKeyGuid(16) (+compression methods)
# In practice we read from file_size - 204 for the info block
PAK_INFO_OFFSET = 204
