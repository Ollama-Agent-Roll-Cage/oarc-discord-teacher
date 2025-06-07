# envCreation Cheat Sheet

## Create env

```bash
uv venv -p 3.11 .venv
.venv\Scripts\activate
```

## Uninstall all packages from your Python environment

```bash
uv pip freeze > requirements.txt
uv pip uninstall -r requirements.txt
```

## Remove .venv entirely
```bash
Remove-Item -Recurse -Force .venv
```

## Core utils to install after cleaning env
```bash
# Install core utils
uv pip install uv pip wheel setuptools build twine
```

## Install oarc-crawlers in development mode

```bash
# Install in development mode with dev dependencies
uv pip install -e ".[dev]"

# Clean build artifacts (Windows PowerShell)
Remove-Item -Path "dist","build","*.egg-info" -Recurse -Force -ErrorAction SilentlyContinue
```

## Building the package, and uploading to pypi with twine

```bash
# Build package
python -m build

# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Upload to PyPI
python -m twine upload dist/*
```