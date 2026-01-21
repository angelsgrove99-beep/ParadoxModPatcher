# Paradox Mod Patcher v2.0.0

## Smart compatibility patch generator for Paradox mods

---

## 🎮 Supported Games

| Game | Status | Note |
|------|--------|------|
| **Crusader Kings 3** | ✅ Full support | Tested |
| Europa Universalis 4 | ⚠️ Experimental | Not tested |
| Hearts of Iron 4 | ⚠️ Experimental | replace_path not supported |
| Stellaris | ⚠️ Experimental | Not tested |
| Victoria 3 | ⚠️ Experimental | Not tested |

> ⚠️ **For games other than CK3**: use at your own risk.

---

## ✨ Features

- 🔍 **Mod scanning** — automatic detection of all mods
- 🎯 **Smart analysis** — shows only mods with actual base changes
- 🔧 **Intelligent merge** — combines changes at code block level
- 📦 **Patch generation** — creates ready-to-use mod
- 🌍 **12 interface languages** — EN, RU, DE, FR, ES, ZH, KO, JA, PL, TR, PT, IT
- 🔎 **Auto-detection** — automatic game and mods folder detection
- 💾 **Profiles** — save and load configurations

---

## 🚀 Quick Start

### Step 1: Mods Folder
- Click **[Auto]** for auto-detection
- Or **[Browse...]** for manual selection
- Click **[🔍 Scan]**

### Step 2: Select Base
- **Original game** — for patches to vanilla game
  - Click **[Auto]** to find installed CK3
- **Global mod** — for patches to a large mod (e.g., LOTR: Realms in Exile)

### Step 3: Select Mods
- Add mods from left list to right
- Order in right list = application order
- Use **[↑ Up]** / **[↓ Down]** to change order

### Step 4: Create Patch
- Enter patch name
- Click **[🔧 Create Patch]**
- Select save folder

### Step 5: Install Patch
1. Created folder is already in `mod/` directory
2. Enable patch in launcher **last** in load order

---

## 🔧 How Merge Works

The program parses Paradox scripts and combines changes at block level:

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

Menu: **🌐 Language** → select desired

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

---

## ⚠️ Known Limitations

- Does not merge binary files (images, sounds, models)
- HOI4 `replace_path` directives not processed
- Some complex structures may require manual merge

---

## 🙏 Acknowledgments

Created for the Paradox modding community.

It all started when the author wanted to romance elves while playing as humans in LOTR: Realms in Exile, but 20 other submods kept getting in the way. Thus this tool was born. 🧝‍♀️💍

---

**🤖 + 🧑 = ❤️**

*This project was created in collaboration with [Claude AI](https://claude.ai) (Anthropic).*

*AI is not a replacement for humans, but a tool that helps bring ideas to life.*
*Human creates ideas, directs and tests. AI helps write code and solve problems.*
*Together — stronger.*

---

## 📄 License

MIT License — do whatever you want, but at your own risk.
