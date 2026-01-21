# Paradox Mod Patcher

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Python](https://img.shields.io/badge/python-3.8+-yellow)

**Automatic compatibility patch generator for Paradox mods**

*Merges conflicting files from multiple mods into one patch. Supports Steam Workshop + local mods.*

</div>

---

## 🎮 Supported Games

| Game | Status | Note |
|------|--------|------|
| **Crusader Kings 3** | ✅ Full support | Tested |
| Europa Universalis 4 | ⚠️ Experimental | Not tested |
| Hearts of Iron 4 | ⚠️ Experimental | `replace_path` not supported |
| Stellaris | ⚠️ Experimental | Not tested |
| Victoria 3 | ⚠️ Experimental | Not tested |

> ⚠️ **For games other than CK3**: use at your own risk. Full support coming in future versions.

---

## ✨ Features

- 🔍 **Mod Scanning** — automatic detection of all installed mods
- 🎯 **Smart Analysis** — shows only mods with actual file conflicts
- 🔧 **Intelligent Merge** — combines changes at code block level
- 📦 **Patch Generation** — creates ready-to-use compatibility patch
- 🌍 **12 Interface Languages** — EN, RU, DE, FR, ES, ZH, KO, JA, PL, TR, PT, IT
- 🔎 **Auto-Detection** — automatically finds game and mods folders
- 💾 **Profiles** — save and load mod configurations

---

## 📥 Installation

### Option 1: Pre-built executable (Windows)

1. Download `ParadoxModPatcher.zip` from [Releases](../../releases)
2. Extract to any folder
3. Run `ParadoxModPatcher.exe`

### Option 2: From source

```bash
# Clone the repository
git clone https://github.com/angelsgrove99-beep/ParadoxModPatcher.git
cd ParadoxModPatcher

# Install dependencies
pip install -r requirements.txt

# Run
python src/main.py
```

### Option 3: Build executable yourself

```bash
pip install -r requirements.txt
python build.py
# Result: dist/ParadoxModPatcher/
```

---

## 🚀 Usage

### Step 1: Mods Folder
- Click **[Auto]** for auto-detection
- Or **[Browse...]** for manual selection
- Click **[🔍 Scan]**

### Step 2: Select Base
- **Original game** — for patches to vanilla game
  - Click **[Auto]** to find installed CK3
- **Global mod** — for patches to a large overhaul mod (e.g., LOTR: Realms in Exile)

### Step 3: Select Mods
- Add mods from the left list to the right list
- Order in right list = load order priority
- Use **[↑ Up]** / **[↓ Down]** to change order

### Step 4: Create Patch
- Enter patch name
- Click **[🔧 Create Patch]**
- Select output folder

### Step 5: Install Patch
1. Copy created folder to `Documents/Paradox Interactive/Crusader Kings III/mod/`
2. Enable patch in launcher **last** in load order

---

## 🔧 How Merge Works

The program parses Paradox script files and combines changes at the block level:

```
# Base (LOTR mod):              # Submod A:                    # Submod B:
can_marry = {                   can_marry = {                  can_marry = {
    age >= 16                       is_elf = yes                   is_dwarf = yes  
}                               }                              }

# Merge result:
can_marry = {
    age >= 16        # Preserved from base
    is_elf = yes     # Added from A
    is_dwarf = yes   # Added from B
}
```

---

## 🌍 Interface Languages

| | | | |
|---|---|---|---|
| 🇬🇧 English | 🇷🇺 Русский | 🇩🇪 Deutsch | 🇫🇷 Français |
| 🇪🇸 Español | 🇨🇳 简体中文 | 🇰🇷 한국어 | 🇯🇵 日本語 |
| 🇵🇱 Polski | 🇹🇷 Türkçe | 🇵🇹 Português | 🇮🇹 Italiano |

Menu: **🌐 Language** → select your language

---

## 🔍 Path Auto-Detection

### Mods Folder
Automatically searches:
- Windows: `Documents/Paradox Interactive/Crusader Kings III/mod`
- Linux: `~/.local/share/Paradox Interactive/Crusader Kings III/mod`
- macOS: `~/Documents/Paradox Interactive/Crusader Kings III/mod`

### Game Folder
Searches for CK3 installation in:
- **Steam** — via registry and libraryfolders.vdf (all drives)
- **GOG** — via registry
- **Xbox Game Pass** — standard paths
- Common folders: `C:\Program Files`, `D:\Steam`, `D:\Games`, etc.

---

## 📁 Project Structure

```
ParadoxModPatcher/
├── src/
│   ├── main.py              # Entry point
│   ├── i18n.py              # Localization (12 languages)
│   ├── version.py           # Version info
│   ├── cli.py               # Command line interface
│   ├── core/
│   │   ├── scanner.py       # Mod scanner + auto-detection
│   │   ├── parser.py        # Paradox script parser
│   │   ├── smart_merger.py  # Intelligent merge logic
│   │   └── smart_patch_generator.py
│   └── gui/
│       └── main_window.py   # PyQt5 GUI
├── resources/
│   ├── icons/
│   └── docs/
├── requirements.txt
├── build.py
└── README.md
```

---

## ⚠️ Known Limitations

- Does not merge binary files (images, sounds, 3D models)
- HOI4 `replace_path` directives not processed
- Some complex nested structures may require manual merge

---

## 🗺️ Roadmap

- [ ] Full support for EU4, HOI4, Stellaris, Victoria 3
- [ ] Handle `replace_path` for HOI4
- [ ] Preview changes before merge
- [ ] Conflict visualization
- [ ] Extended CLI options

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs via [Issues](../../issues)
- Submit pull requests
- Suggest new features

---

## 📄 License

MIT License — do whatever you want, but at your own risk.

---

## 🙏 Acknowledgments

Created for the Paradox modding community.

It all started when the author wanted to romance elves while playing as humans in LOTR: Realms in Exile, but 20 other submods kept getting in the way. Thus this tool was born. 🧝‍♀️💍

---

<div align="center">

**🤖 + 🧑 = ❤️**

*This project was created in collaboration with [Claude AI](https://claude.ai) (Anthropic).*

*AI is not a replacement for humans, but a tool that helps bring ideas to life.*
*Human creates, directs, and tests. AI helps write code and solve problems.*
*Together — stronger.*

</div>
