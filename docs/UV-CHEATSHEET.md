
# UV Package Manager Cheat Sheet

## Create Environment

```bash
# Create a virtual environment with Python 3.11
uv venv -p 3.11 .venv

# Activate the environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

## Remove Environment Entirely

```bash
# Windows
Remove-Item -Recurse -Force .venv

# Linux/Mac
rm -rf .venv
```

## Core Utils to Install After Cleaning Environment

```bash
# Install core utilities
uv pip install uv pip wheel setuptools build twine

# Install project requirements
uv pip install -r requirements.txt
# also if you encounter issues you can uninstall requirements if needed
uv pip uninstall -r requirements.txt
```

## Starting the Discord Bot

```bash
# Use the following command to run the discord bot with UI
python start_ui.py

# You can also run the bot directly (headless mode)
python start_bot.py

# Or use the provided scripts
# Windows:
.\startup.bat
# Linux/Mac:
./startup.sh
```