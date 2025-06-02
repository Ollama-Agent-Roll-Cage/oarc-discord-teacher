OllamaTeacher Bot Modularization Plan

1. Project Structure Reorganization

```bashs
ollama_teacher/
├── pyproject.toml
├── README.md
├── LICENSE
├── .env.template
├── .gitignore
├── assets/
├── docs/
│   ├── installation.md
│   ├── configuration.md
│   └── api/
├── tests/
│   ├── __init__.py
│   ├── test_bot.py
│   ├── test_commands.py
│   └── fixtures/
└── src/
    └── ollama_teacher/
        ├── __init__.py
        ├── cli/
        │   ├── __init__.py
        │   └── bot_cli.py
        ├── core/
        │   ├── __init__.py
        │   ├── bot.py
        │   └── config.py
        ├── commands/
        │   ├── __init__.py
        │   ├── base.py
        │   ├── arxiv.py
        │   ├── search.py
        │   ├── profile.py
        │   ├── links.py
        │   └── image_gen.py
        ├── services/
        │   ├── __init__.py
        │   ├── ollama.py
        │   ├── groq.py
        │   ├── arxiv.py
        │   ├── search.py
        │   └── storage.py
        ├── models/
        │   ├── __init__.py
        │   ├── user.py
        │   ├── conversation.py
        │   └── profile.py
        ├── ui/
        │   ├── __init__.py
        │   ├── main_window.py
        │   └── components/
        ├── utils/
        │   ├── __init__.py
        │   ├── text.py
        │   └── file_ops.py
        └── data/
            └── templates/
                └── env.template
```

2. Package Configuration (pyproject.toml)

```
[project]
name = "ollama_teacher"
version = "0.1.0"
description = "A modular Discord bot for AI-powered learning using Ollama"
authors = [{name = "Your Name", email = "your.email@example.com"}]
license = {file = "LICENSE"}
readme = "README.md"
requires-python = ">=3.8"
dependencies = [
    "discord.py>=2.0.0",
    "python-dotenv>=0.20.0",
    "ollama>=0.4.7",
    "pandas>=1.3.0",
    "pyarrow>=6.0.0",
    "beautifulsoup4>=4.10.0",
    "aiohttp>=3.8.0",
    "groq",
    "PyQt6",
    "diffusers>=0.21.0",
    "torch>=2.0.0",
    "transformers>=4.31.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "black>=22.0",
    "isort>=5.0",
    "mypy>=0.9"
]

[project.scripts]
ollama-teacher = "ollama_teacher.cli.bot_cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

3. Environment Management

Create an environment setup module:

```python
# src/ollama_teacher/core/env_setup.py
from pathlib import Path
import inquirer
from typing import Dict

class EnvSetup:
    def __init__(self):
        self.template_path = Path(__file__).parent.parent / "data/templates/env.template"
        self.config_items = {
            "DISCORD_TOKEN": {
                "description": "Your Discord Bot Token",
                "required": True
            },
            "OLLAMA_MODEL": {
                "description": "Default Ollama Model",
                "default": "llama2:latest"
            },
            "OLLAMA_VISION_MODEL": {
                "description": "Vision Model for Image Processing",
                "default": "llava"
            },
            # Add other config items
        }

    def setup_interactive(self) -> Dict[str, str]:
        # Interactive environment setup
        pass

    def generate_env_file(self, path: Path, values: Dict[str, str]) -> None:
        # Generate .env file from template
        pass
```

4. TODO List for Implementation

A. Core Structure Setup
<input disabled="" type="checkbox"> Create package directory structure
<input disabled="" type="checkbox"> Set up pyproject.toml with dependencies
<input disabled="" type="checkbox"> Create environment template system
<input disabled="" type="checkbox"> Set up logging configuration
<input disabled="" type="checkbox"> Create basic documentation structure
B. Module Separation
<input disabled="" type="checkbox"> Split commands into individual modules
<input disabled="" type="checkbox"> Create base command class
<input disabled="" type="checkbox"> Implement command registration system
<input disabled="" type="checkbox"> Move each command to its own file
<input disabled="" type="checkbox"> Separate services
<input disabled="" type="checkbox"> Ollama service
<input disabled="" type="checkbox"> Groq service
<input disabled="" type="checkbox"> ArXiv service
<input disabled="" type="checkbox"> Search service
<input disabled="" type="checkbox"> Create model classes
<input disabled="" type="checkbox"> User model
<input disabled="" type="checkbox"> Conversation model
<input disabled="" type="checkbox"> Profile model
C. Configuration System
<input disabled="" type="checkbox"> Create config management class
<input disabled="" type="checkbox"> Implement environment variable validation
<input disabled="" type="checkbox"> Add configuration file support
<input disabled="" type="checkbox"> Create user-specific config profiles
D. Storage System
<input disabled="" type="checkbox"> Abstract storage interface
<input disabled="" type="checkbox"> Implement ParquetStorage class
<input disabled="" type="checkbox"> Add profile storage system
<input disabled="" type="checkbox"> Create conversation history manager
E. UI Components
<input disabled="" type="checkbox"> Separate PyQt6 UI components
<input disabled="" type="checkbox"> Create component factory system
<input disabled="" type="checkbox"> Implement UI state management
<input disabled="" type="checkbox"> Add theme support
F. CLI System
<input disabled="" type="checkbox"> Create CLI interface
<input disabled="" type="checkbox"> Add command-line arguments
<input disabled="" type="checkbox"> Implement interactive setup
<input disabled="" type="checkbox"> Add deployment helpers
G. Testing Framework
<input disabled="" type="checkbox"> Set up pytest structure
<input disabled="" type="checkbox"> Create mock services
<input disabled="" type="checkbox"> Add command tests
<input disabled="" type="checkbox"> Implement UI tests
H. Documentation
<input disabled="" type="checkbox"> Create API documentation
<input disabled="" type="checkbox"> Write installation guide
<input disabled="" type="checkbox"> Add configuration guide
<input disabled="" type="checkbox"> Create usage examples
I. Deployment Tools
<input disabled="" type="checkbox"> Create installation script
<input disabled="" type="checkbox"> Add Docker support
<input disabled="" type="checkbox"> Create systemd service file
<input disabled="" type="checkbox"> Add Windows service support
Would you like me to focus on implementing any specific part of this plan first?