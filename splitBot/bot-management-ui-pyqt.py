import os
import sys
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime, timezone, UTC
from pathlib import Path
import threading
import subprocess
import signal
import webbrowser
import re
from diffusers import StableDiffusionXLPipeline
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QUrl
from PyQt6.QtGui import QColor, QPalette, QTextCursor, QFont, QDesktopServices, QAction
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QTreeWidget, QTreeWidgetItem, QTextEdit,
    QSplitter, QCheckBox, QStatusBar, QMenuBar, QMenu, QDialog, QFileDialog,
    QLineEdit, QGridLayout, QMessageBox, QHeaderView, QScrollArea, QSpacerItem,
    QSizePolicy, QGroupBox, QComboBox
)

# Import bot modules - adjust paths as needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from utils import ParquetStorage, SYSTEM_PROMPT
    from config import DATA_DIR, MODEL_NAME, TEMPERATURE, TIMEOUT, CHANGE_NICKNAME
except ImportError:
    # Fallback values if imports fail
    DATA_DIR = os.getenv('DATA_DIR', 'data')
    MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3')
    TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))
    TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))
    CHANGE_NICKNAME = True
    SYSTEM_PROMPT = """AI assistant placeholder prompt"""
    
    # Placeholder for ParquetStorage
    class ParquetStorage:
        @staticmethod
        def load_from_parquet(file_path):
            try:
                import pandas as pd
                if not os.path.exists(file_path):
                    return None
                return pd.read_parquet(file_path)
            except Exception as e:
                logging.error(f"Error loading from Parquet: {e}")
                return None
        
        @staticmethod
        def save_to_parquet(data, file_path):
            try:
                import pandas as pd
                import pyarrow as pa
                import pyarrow.parquet as pq
                
                # Convert to DataFrame if it's a dictionary
                if isinstance(data, dict):
                    df = pd.DataFrame([data])
                elif isinstance(data, list):
                    df = pd.DataFrame(data)
                else:
                    df = data
                    
                # Save to Parquet
                pq.write_table(pa.Table.from_pandas(df), file_path)
                logging.info(f"Data saved to {file_path}")
                return True
            except Exception as e:
                logging.error(f"Error saving to Parquet: {e}")
                return False

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BotManager")

# Define theme colors
class AcidTheme:
    BG_DARK = "#121212"           # Dark background
    BG_MEDIUM = "#1E1E1E"         # Medium background
    ACCENT_PRIMARY = "#39FF14"    # Acid green
    ACCENT_SECONDARY = "#00FF8C"  # Secondary neon green
    ACCENT_TERTIARY = "#50FA7B"   # Tertiary green
    TEXT_PRIMARY = "#FFFFFF"      # White text
    TEXT_SECONDARY = "#AAAAAA"    # Light gray text
    DANGER = "#FF5555"            # Red for danger/stop
    WARNING = "#F1FA8C"           # Yellow for warnings
    SUCCESS = "#39FF14"           # Green for success

class LogMonitorThread(QThread):
    """Thread to monitor the log file and emit its content"""
    log_updated = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.file_path = "bot_manager.log"
        
    def run(self):
        """Run the thread, monitoring the log file for changes"""
        last_size = 0
        
        while self.running:
            try:
                if os.path.exists(self.file_path):
                    current_size = os.path.getsize(self.file_path)
                    
                    if (current_size > last_size):
                        with open(self.file_path, 'r') as f:
                            content = f.read()
                            self.log_updated.emit(content)
                        
                        last_size = current_size
            except Exception as e:
                logger.error(f"Error in log monitor: {e}")
                
            # Sleep for a short period
            self.msleep(1000)  # Sleep for 1 second
            
    def stop(self):
        """Stop the thread"""
        self.running = False
        self.wait()

class ProcessOutputThread(QThread):
    """Thread to monitor a subprocess's output"""
    output_received = pyqtSignal(str)
    process_ended = pyqtSignal(int)
    
    def __init__(self, process, parent=None):
        super().__init__(parent)
        self.process = process
        
    def run(self):
        """Run the thread, capturing process output"""
        try:
            for line in iter(self.process.stdout.readline, ''):
                if not line:
                    break
                self.output_received.emit(line.strip())
                
            # Process has ended
            exit_code = self.process.wait()
            self.process_ended.emit(exit_code)
            
        except Exception as e:
            logger.error(f"Error in process output thread: {e}")
            self.process_ended.emit(-1)

class ProfileDialog(QDialog):
    """Dialog for viewing a user profile"""
    def __init__(self, profile_data, user_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"User Profile: {profile_data.get('username', 'Unknown')}")
        self.resize(600, 400)
        
        # Set up the UI
        layout = QVBoxLayout(self)
        
        # Profile text area
        self.profile_text = QTextEdit()
        self.profile_text.setReadOnly(True)
        self.profile_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                font-family: 'Segoe UI', sans-serif;
            }}
        """)
        
        # Format profile data
        formatted_profile = f"# User Profile: {profile_data.get('username', 'Unknown')}\n\n"
        formatted_profile += f"**User ID:** {user_id}\n"
        formatted_profile += f"**Last Active:** {profile_data.get('timestamp', 'Unknown')}\n\n"
        formatted_profile += "## Learning Analysis\n\n"
        formatted_profile += profile_data.get('analysis', 'No analysis available')
        
        self.profile_text.setMarkdown(formatted_profile)
        layout.addWidget(self.profile_text)
        
        # Close button
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.ACCENT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                padding: 5px 15px;
            }}
            QPushButton:hover {{
                background-color: {AcidTheme.ACCENT_PRIMARY};
                color: {AcidTheme.BG_DARK};
            }}
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

class PaperDialog(QDialog):
    """Dialog for viewing a paper's details"""
    def __init__(self, paper_data, arxiv_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Paper: {paper_data.get('title', 'Unknown')}")
        self.resize(700, 500)
        
        # Set up the UI
        layout = QVBoxLayout(self)
        
        # Paper text area
        self.paper_text = QTextEdit()
        self.paper_text.setReadOnly(True)
        self.paper_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                font-family: 'Segoe UI', sans-serif;
            }}
        """)
        
        # Format paper data
        formatted_paper = f"# {paper_data.get('title', 'Unknown')}\n\n"
        formatted_paper += f"**ArXiv ID:** {arxiv_id}\n"
        formatted_paper += f"**Authors:** {', '.join(paper_data.get('authors', []))}\n"
        formatted_paper += f"**Published:** {paper_data.get('published', 'Unknown')}\n"
        formatted_paper += f"**Categories:** {', '.join(paper_data.get('categories', []))}\n\n"
        formatted_paper += "## Abstract\n\n"
        formatted_paper += paper_data.get('abstract', 'No abstract available')
        
        # Add links
        formatted_paper += "\n\n## Links\n\n"
        formatted_paper += f"- [ArXiv Page]({paper_data.get('arxiv_url', '')})\n"
        formatted_paper += f"- [PDF Download]({paper_data.get('pdf_link', '')})\n"
        
        self.paper_text.setMarkdown(formatted_paper)
        layout.addWidget(self.paper_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        # Open ArXiv page button
        arxiv_btn = QPushButton("Open ArXiv Page")
        arxiv_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(paper_data.get('arxiv_url', ''))))
        
        # Open PDF button
        pdf_btn = QPushButton("Open PDF")
        pdf_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(paper_data.get('pdf_link', ''))))
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        # Style buttons
        for btn in [arxiv_btn, pdf_btn, close_btn]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {AcidTheme.BG_MEDIUM};
                    color: {AcidTheme.ACCENT_PRIMARY};
                    border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                    padding: 5px 15px;
                }}
                QPushButton:hover {{
                    background-color: {AcidTheme.ACCENT_PRIMARY};
                    color: {AcidTheme.BG_DARK};
                }}
            """)
        
        btn_layout.addWidget(arxiv_btn)
        btn_layout.addWidget(pdf_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

class SystemPromptDialog(QDialog):
    """Dialog for editing the system prompt"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit System Prompt")
        self.resize(600, 400)
        
        # Set up the UI
        layout = QVBoxLayout(self)
        
        # Label
        label = QLabel("Edit System Prompt:")
        label.setStyleSheet(f"color: {AcidTheme.TEXT_PRIMARY};")
        layout.addWidget(label)
        
        # Prompt text area
        self.prompt_text = QTextEdit()
        self.prompt_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                font-family: 'Segoe UI', sans-serif;
            }}
        """)
        
        # Load current prompt
        self.prompt_text.setPlainText(SYSTEM_PROMPT.strip())
        layout.addWidget(self.prompt_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        # Save button
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self.save_prompt)
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        # Style buttons
        for btn in [save_btn, cancel_btn]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {AcidTheme.BG_MEDIUM};
                    color: {AcidTheme.ACCENT_PRIMARY};
                    border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                    padding: 5px 15px;
                }}
                QPushButton:hover {{
                    background-color: {AcidTheme.ACCENT_PRIMARY};
                    color: {AcidTheme.BG_DARK};
                }}
            """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
    def save_prompt(self):
        """Save the edited system prompt"""
        new_prompt = self.prompt_text.toPlainText().strip()
        try:
            # Read the config.py file
            with open("config.py", 'r') as f:
                config_content = f.read()
            
            # Find the SYSTEM_PROMPT section
            pattern = r'SYSTEM_PROMPT\s*=\s*""".*?"""'
            new_config = re.sub(pattern, f'SYSTEM_PROMPT = """\n{new_prompt}\n"""', config_content, flags=re.DOTALL)
            
            # Write back the updated config
            with open("config.py", 'w') as f:
                f.write(new_config)
                
            QMessageBox.information(self, "Success", "System prompt updated.\nRestart the bot for changes to take effect.")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update system prompt: {str(e)}")

class ConfigDialog(QDialog):
    """Dialog for editing bot configuration"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bot Configuration")
        self.resize(500, 400)  # Made taller for new options
        
        # Set up the UI
        layout = QVBoxLayout(self)
        
        # Config form
        config_grid = QGridLayout()
        
        # Regular Ollama Model Selection (ADD THIS FIRST)
        config_grid.addWidget(QLabel("Ollama Model:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        self.model_combo.setEnabled(False)
        self.model_combo.addItem("Loading models...")
        config_grid.addWidget(self.model_combo, 0, 1)
        
        # Add refresh button for regular models
        refresh_btn = QPushButton("⟳")
        refresh_btn.setToolTip("Refresh Models")
        refresh_btn.clicked.connect(self.fetch_models)
        config_grid.addWidget(refresh_btn, 0, 2)

        # Vision Model Selection
        config_grid.addWidget(QLabel("Vision Model:"), 1, 0)
        self.vision_model_combo = QComboBox()
        self.vision_model_combo.setMinimumWidth(200)
        self.vision_model_combo.setEnabled(False)
        self.vision_model_combo.addItem("Loading models...")
        config_grid.addWidget(self.vision_model_combo, 1, 1)
        
        # Add refresh button for vision models
        refresh_vision_btn = QPushButton("⟳")
        refresh_vision_btn.setToolTip("Refresh Vision Models")
        refresh_vision_btn.clicked.connect(self.fetch_vision_models)
        config_grid.addWidget(refresh_vision_btn, 1, 2)

        # Temperature
        config_grid.addWidget(QLabel("Temperature:"), 2, 0)
        self.temp_entry = QLineEdit(str(TEMPERATURE))
        config_grid.addWidget(self.temp_entry, 2, 1)
        
        # Timeout
        config_grid.addWidget(QLabel("Timeout (seconds):"), 3, 0)
        self.timeout_entry = QLineEdit(str(TIMEOUT))
        config_grid.addWidget(self.timeout_entry, 3, 1)
        
        # Data directory
        config_grid.addWidget(QLabel("Data Directory:"), 4, 0)
        self.data_dir_entry = QLineEdit(DATA_DIR)
        config_grid.addWidget(self.data_dir_entry, 4, 1)
        
        # Change nickname option
        config_grid.addWidget(QLabel("Change Bot Nickname:"), 5, 0)
        self.nickname_check = QCheckBox()
        self.nickname_check.setChecked(CHANGE_NICKNAME)
        config_grid.addWidget(self.nickname_check, 5, 1)
        
        layout.addLayout(config_grid)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self.save_config)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        # Style buttons
        for btn in [save_btn, cancel_btn]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {AcidTheme.BG_MEDIUM};
                    color: {AcidTheme.ACCENT_PRIMARY};
                    border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                    padding: 5px 15px;
                }}
                QPushButton:hover {{
                    background-color: {AcidTheme.ACCENT_PRIMARY};
                    color: {AcidTheme.BG_DARK};
                }}
            """)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        # Start timers to fetch both types of models
        QTimer.singleShot(100, self.fetch_models)
        QTimer.singleShot(100, self.fetch_vision_models)

    def fetch_vision_models(self):
        """Fetch models for the vision model combo box"""
        # Show loading state
        self.vision_model_combo.clear()
        self.vision_model_combo.addItem("Fetching models...")
        self.vision_model_combo.setEnabled(False)
        
        try:
            class VisionModelsFetchThread(QThread):
                models_fetched = pyqtSignal(object)
                error_occurred = pyqtSignal(str)
                
                def run(self):
                    try:
                        import ollama
                        models = ollama.list()
                        self.models_fetched.emit(models)
                    except Exception as e:
                        self.error_occurred.emit(str(e))
            
            # Create thread
            fetch_thread = VisionModelsFetchThread(self)
            fetch_thread.models_fetched.connect(self.process_vision_models)
            fetch_thread.error_occurred.connect(self.handle_vision_model_error)
            fetch_thread.start()
            
        except Exception as e:
            self.log_message(f"Error fetching vision models: {e}")
            self.vision_model_combo.clear()
            self.vision_model_combo.addItem("Error fetching models")
            self.vision_model_combo.setEnabled(False)

    def save_config(self):
        """Save the configuration"""
        try:
            # Only save non-model configuration
            global TEMPERATURE, TIMEOUT, DATA_DIR, CHANGE_NICKNAME
            
            # Create new configuration
            new_config = {
                "TEMPERATURE": float(self.temp_entry.text()),
                "TIMEOUT": float(self.timeout_entry.text()),
                "DATA_DIR": self.data_dir_entry.text(),
                "CHANGE_NICKNAME": self.nickname_check.isChecked()
            }
            
            # Read the config.py file
            with open("config.py", 'r') as f:
                config_content = f.read()
            
            # Update each config value
            for key, value in new_config.items():
                pattern = rf'{key}\s*=.*'
                
                # Format the new value based on type
                if isinstance(value, bool):
                    new_value = f"{key} = {str(value)}"
                elif isinstance(value, str):
                    new_value = f"{key} = '{value}'"
                else:
                    new_value = f"{key} = {value}"
                
                config_content = re.sub(pattern, new_value, config_content)
            
            # Write back the updated config
            with open("config.py", 'w') as f:
                f.write(config_content)
            
            # Update global variables
            TEMPERATURE = new_config['TEMPERATURE']
            TIMEOUT = new_config['TIMEOUT']
            DATA_DIR = new_config['DATA_DIR']
            CHANGE_NICKNAME = new_config['CHANGE_NICKNAME']
            
            QMessageBox.information(self, "Success", "Configuration saved.\nRestart the bot for changes to take effect.")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {str(e)}")

    def fetch_models(self):
        """Fetch available Ollama models"""
        try:
            class ModelsFetchThread(QThread):
                models_fetched = pyqtSignal(object)
                error_occurred = pyqtSignal(str)
                
                def run(self):
                    try:
                        import ollama
                        models = ollama.list()
                        self.models_fetched.emit(models)
                    except Exception as e:
                        self.error_occurred.emit(str(e))

            # Create and start thread
            thread = ModelsFetchThread(self)
            thread.models_fetched.connect(self.process_models)
            thread.error_occurred.connect(self.handle_model_error)
            thread.start()

        except Exception as e:
            self.log_message(f"Error fetching models: {e}")
            self.model_combo.clear()
            self.model_combo.addItem("Error fetching models")
            self.model_combo.setEnabled(False)

    def process_models(self, models_list):
        """Process fetched models list for regular model combo"""
        self.model_combo.clear()
        self.model_combo.setEnabled(True)
        
        try:
            # Get current model
            current_model = os.getenv('OLLAMA_MODEL', '')
            current_idx = 0
            
            # Extract model names
            model_names = []
            
            if hasattr(models_list, 'models'):
                models = models_list.models
            elif isinstance(models_list, dict) and 'models' in models_list:
                models = models_list['models']
            else:
                models = []

            for model in models:
                model_name = (model.get('model') or model.get('name') if isinstance(model, dict) 
                            else getattr(model, 'model', None) or getattr(model, 'name', None))
                
                if model_name:
                    model_names.append(model_name)
                    if model_name == current_model:
                        current_idx = len(model_names) - 1

            if not model_names:
                self.model_combo.addItem("No models found")
                return
                
            # Add models to combobox
            self.model_combo.addItems(model_names)
            
            # Select current model if set
            if current_idx < len(model_names):
                self.model_combo.setCurrentIndex(current_idx)

        except Exception as e:
            self.log_message(f"Error processing models: {e}")
            self.model_combo.addItem("Error processing models")

    def handle_model_error(self, error_message):
        """Handle model fetch error"""
        self.model_combo.clear()
        self.model_combo.addItem("Error fetching models")
        self.model_combo.setEnabled(False)
        self.log_message(f"Model fetch error: {error_message}")

class BotManagerApp(QMainWindow):
    """Main application window for the Bot Manager"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ollama Teacher Bot Manager")
        self.resize(1000, 700)
        self.setMinimumSize(800, 600)
        
        # Initialize members
        self.bot_process = None
        self.process_thread = None
        self.log_thread = None
        self.auto_refresh = False
        self.pulse_timer = QTimer()
        self.pulse_index = 0
        
        # Bot status variables
        self.bot_status = "Stopped"
        self.active_model = MODEL_NAME
        self.user_count = 0
        self.total_conversations = 0
        
        # Set the application style
        self.apply_theme()
        
        # Create UI components
        self.create_menu()
        self.create_central_widget()
        self.create_status_bar()
        
        # Initialize data directories
        self.ensure_data_directories()
        
        # Initial load of data
        self.load_data()
        
        # Set up timers for periodic refresh
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.periodic_refresh)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
        
        # Set up timer for the neon pulsing effect
        self.pulse_timer.timeout.connect(self.pulse_status)
        self.pulse_timer.start(800)  # Pulse every 800ms
        
        # Start log monitoring thread
        self.log_thread = LogMonitorThread(self)
        self.log_thread.log_updated.connect(self.update_log_content)
        self.log_thread.start()
        
    def setup_dashboard_tab(self):
        """Set up the dashboard tab with summary info and controls"""
        # Create layout
        layout = QVBoxLayout(self.dashboard_tab)
        
        # Control frame
        control_frame = QGroupBox("Bot Control")
        control_layout = QVBoxLayout(control_frame)
        
        # Model selection layout
        model_grid = QGridLayout()
        
        # Base Model Selection
        model_grid.addWidget(QLabel("Base Model:"), 0, 0)
        self.dashboard_model_combo = QComboBox()
        self.dashboard_model_combo.setMinimumWidth(200)
        self.dashboard_model_combo.setEnabled(False)
        self.dashboard_model_combo.addItem("Loading models...")
        model_grid.addWidget(self.dashboard_model_combo, 0, 1)
        
        # Base model refresh button
        refresh_base_btn = QPushButton("⟳")
        refresh_base_btn.setToolTip("Refresh Base Models")
        refresh_base_btn.setMaximumWidth(30)
        refresh_base_btn.clicked.connect(self.fetch_models_for_dashboard)
        model_grid.addWidget(refresh_base_btn, 0, 2)
        
        # Vision Model Selection
        model_grid.addWidget(QLabel("Vision Model:"), 1, 0)
        self.vision_model_combo = QComboBox()
        self.vision_model_combo.setMinimumWidth(200)
        self.vision_model_combo.setEnabled(False)
        self.vision_model_combo.addItem("Loading models...")
        model_grid.addWidget(self.vision_model_combo, 1, 1)
        
        # Vision model refresh button
        refresh_vision_btn = QPushButton("⟳")
        refresh_vision_btn.setToolTip("Refresh Vision Models")
        refresh_vision_btn.setMaximumWidth(30)
        refresh_vision_btn.clicked.connect(self.fetch_vision_models)
        model_grid.addWidget(refresh_vision_btn, 1, 2)
        
        control_layout.addLayout(model_grid)
        
        # Start/Stop buttons
        btn_layout = QHBoxLayout()
        
        # Store references to buttons as class attributes
        self.start_bot_button = QPushButton("Start Bot")
        self.start_bot_button.clicked.connect(self.start_bot)
        self.start_bot_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.SUCCESS};
                border: 1px solid {AcidTheme.SUCCESS};
            }}
            QPushButton:hover {{
                background-color: {AcidTheme.SUCCESS};
                color: {AcidTheme.BG_DARK};
            }}
        """)
        btn_layout.addWidget(self.start_bot_button)
        
        self.stop_bot_button = QPushButton("Stop Bot")
        self.stop_bot_button.clicked.connect(self.stop_bot)
        self.stop_bot_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.DANGER};
                border: 1px solid {AcidTheme.DANGER};
            }}
            QPushButton:hover {{
                background-color: {AcidTheme.DANGER};
                color: {AcidTheme.BG_DARK};
            }}
        """)
        btn_layout.addWidget(self.stop_bot_button)
        
        self.restart_bot_button = QPushButton("Restart Bot")
        self.restart_bot_button.clicked.connect(self.restart_bot)
        btn_layout.addWidget(self.restart_bot_button)
        
        # Set initial button states
        self.stop_bot_button.setEnabled(False)
        self.restart_bot_button.setEnabled(False)
        
        btn_layout.addStretch()
        control_layout.addLayout(btn_layout)
        layout.addWidget(control_frame)
        
        # Stats frame
        stats_frame = QGroupBox("Bot Statistics")
        stats_layout = QVBoxLayout(stats_frame)
        
        # Create grid for stats
        grid_layout = QGridLayout()
        
        # Row 1 - Bot Status and Base Model
        grid_layout.addWidget(QLabel("Bot Status:"), 0, 0)
        self.status_value = QLabel(self.bot_status)
        self.status_value.setStyleSheet(f"color: {AcidTheme.ACCENT_PRIMARY}; font-weight: bold;")
        grid_layout.addWidget(self.status_value, 0, 1)
        
        grid_layout.addWidget(QLabel("Base Model:"), 0, 2)
        self.model_value = QLabel(self.active_model)
        self.model_value.setStyleSheet(f"color: {AcidTheme.ACCENT_PRIMARY}; font-weight: bold;")
        grid_layout.addWidget(self.model_value, 0, 3)
        
        # Row 2 - Vision Model and Users
        grid_layout.addWidget(QLabel("Vision Model:"), 1, 0)
        self.vision_model_value = QLabel(os.getenv('OLLAMA_VISION_MODEL', 'Not Set'))
        self.vision_model_value.setStyleSheet(f"color: {AcidTheme.ACCENT_PRIMARY}; font-weight: bold;")
        grid_layout.addWidget(self.vision_model_value, 1, 1)
        
        grid_layout.addWidget(QLabel("Unique Users:"), 1, 2)
        self.users_value = QLabel(str(self.user_count))
        self.users_value.setStyleSheet(f"color: {AcidTheme.ACCENT_PRIMARY}; font-weight: bold;")
        grid_layout.addWidget(self.users_value, 1, 3)
        
        # Row 3 - Conversations
        grid_layout.addWidget(QLabel("Total Conversations:"), 2, 0)
        self.conversations_value = QLabel(str(self.total_conversations))
        self.conversations_value.setStyleSheet(f"color: {AcidTheme.ACCENT_PRIMARY}; font-weight: bold;")
        grid_layout.addWidget(self.conversations_value, 2, 1)
        
        stats_layout.addLayout(grid_layout)
        layout.addWidget(stats_frame)
        
        # Recent activity frame
        activity_frame = QGroupBox("Recent Activity")
        activity_layout = QVBoxLayout(activity_frame)
        
        # Activity list
        self.activity_text = QTextEdit()
        self.activity_text.setReadOnly(True)
        activity_layout.addWidget(self.activity_text)
        
        layout.addWidget(activity_frame)
    
        # Start a timer to fetch models
        QTimer.singleShot(100, self.fetch_models_for_dashboard)
        QTimer.singleShot(100, self.fetch_vision_models)

        self.dashboard_model_combo.currentTextChanged.connect(self.change_base_model)
        self.vision_model_combo.currentTextChanged.connect(self.change_vision_model)

    def fetch_models_for_dashboard(self):
        """Fetch models for the dashboard combo box"""
        # Show loading
        self.dashboard_model_combo.clear()
        self.dashboard_model_combo.addItem("Fetching models...")
        self.dashboard_model_combo.setEnabled(False)
        
        # Get current model to select it later
        current_model = os.getenv('OLLAMA_MODEL', MODEL_NAME)
        
        try:
            # Run in a separate thread
            import ollama
            
            class DashboardFetchModelsThread(QThread):
                models_fetched = pyqtSignal(object)
                error_occurred = pyqtSignal(str)
                
                def run(self):
                    try:
                        models = ollama.list()
                        self.models_fetched.emit(models)
                    except Exception as e:
                        self.error_occurred.emit(str(e))
            
            # Create thread
            fetch_thread = DashboardFetchModelsThread(self)
            fetch_thread.models_fetched.connect(self.process_dashboard_models)
            fetch_thread.error_occurred.connect(self.handle_dashboard_model_error)
            fetch_thread.start()
            
        except ImportError:
            self.dashboard_model_combo.clear()
            self.dashboard_model_combo.addItem("ollama package not installed")
            self.dashboard_model_combo.setEnabled(False)
        
        except Exception as e:
            self.dashboard_model_combo.clear()
            self.dashboard_model_combo.addItem("Error fetching models")
            self.dashboard_model_combo.setEnabled(False)

    def process_dashboard_models(self, models_list):
        """Process models for dashboard"""
        self.dashboard_model_combo.clear()
        self.dashboard_model_combo.setEnabled(True)
        
        # Get current model
        current_model = os.getenv('OLLAMA_MODEL', MODEL_NAME)
        current_idx = 0
        
        try:
            # Extract model names
            model_names = []
            
            # Check if models_list is a dataclass or similar object with 'models' attribute
            if hasattr(models_list, 'models'):
                models = models_list.models
                for i, model in enumerate(models):
                    if hasattr(model, 'model'):
                        model_name = model.model
                    elif hasattr(model, 'name'):
                        model_name = model.name
                    else:
                        continue
                    
                    model_names.append(model_name)
                    # Check if this is the current model
                    if model_name == current_model:
                        current_idx = len(model_names) - 1
            
            # Check if models_list is a dictionary with 'models' key
            elif isinstance(models_list, dict) and 'models' in models_list:
                models = models_list['models']
                for i, model in enumerate(models):
                    if isinstance(model, dict):
                        model_name = model.get('model') or model.get('name')
                        if not model_name:
                            continue
                        
                        model_names.append(model_name)
                        # Check if this is the current model
                        if model_name == current_model:
                            current_idx = len(model_names) - 1
            
            if not model_names:
                self.dashboard_model_combo.addItem("No models found")
                return
                
            # Add all models to combobox
            self.dashboard_model_combo.addItems(model_names)
            
            # Select the current model
            if current_idx < len(model_names):
                self.dashboard_model_combo.setCurrentIndex(current_idx)
            
            # Log the available models
            logger.info(f"Available models: {', '.join(model_names)}")
            
        except Exception as e:
            logger.error(f"Error processing models: {e}")
            self.dashboard_model_combo.addItem("Error processing models")

    def handle_dashboard_model_error(self, error_message):
        """Handle model fetch error in dashboard"""
        self.dashboard_model_combo.clear()
        self.dashboard_model_combo.addItem("Error fetching models")
        self.dashboard_model_combo.setEnabled(False)
        logger.error(f"Dashboard model fetch error: {error_message}")

    def change_active_model(self):
        """Change the active model without restarting the bot"""
        if self.dashboard_model_combo.currentText() in ["Fetching models...", "Loading models...", "Error fetching models", "No models found", "ollama package not installed", "Error processing models"]:
            return
            
        # Get the selected model
        selected_model = self.dashboard_model_combo.currentText()
        
        # Check if it's actually different from the current model
        if selected_model == self.active_model:
            return
        
        try:
            # Update .env file
            env_path = ".env"
            new_content = ""
            
            try:
                # Try to read existing .env file
                if (os.path.exists(env_path)):
                    with open(env_path, 'r') as f:
                        env_lines = f.readlines()
                    
                    # Keep all lines except OLLAMA_MODEL
                    preserved_lines = [line for line in env_lines if not line.startswith('OLLAMA_MODEL=')]
                    
                    # Add our model setting first, then the preserved lines
                    new_content = f"OLLAMA_MODEL={selected_model}\n" + ''.join(preserved_lines)
                else:
                    # File doesn't exist, create basic content
                    new_content = f"OLLAMA_MODEL={selected_model}\n"
                    # Add DISCORD_TOKEN if it exists in environment
                    discord_token = os.getenv('DISCORD_TOKEN', '')
                    if discord_token:
                        new_content += f"DISCORD_TOKEN={discord_token}\n"
            
            except Exception as e:
                logger.error(f"Error reading .env file: {e}")
                # Create basic content
                new_content = f"OLLAMA_MODEL={selected_model}\n"
                # Add DISCORD_TOKEN if it exists in environment
                discord_token = os.getenv('DISCORD_TOKEN', '')
                if (discord_token):
                    new_content += f"DISCORD_TOKEN={discord_token}\n"
            
            # Write updated content
            with open(env_path, 'w') as f:
                f.write(new_content)
            
            # Update OS environment variable
            os.environ['OLLAMA_MODEL'] = selected_model
            
            # Update UI
            self.active_model = selected_model
            self.model_value.setText(selected_model)
            
            # Add to activity log
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.activity_text.append(f"{timestamp} - Model changed to: {selected_model}")
            
            # Show notification
            self.status_label.setText(f"Active model changed to {selected_model}")
            
            # Optional: If bot is running, show restart recommendation
            if self.bot_process and self.bot_process.poll() is None:
                QMessageBox.information(self, "Model Changed", 
                    f"Active model changed to {selected_model}.\n\nYou may need to restart the bot for the change to take effect in conversations.")
        
        except Exception as e:
            logger.error(f"Error changing model: {e}")
            QMessageBox.critical(self, "Error", f"Failed to change model: {str(e)}")

    def setup_users_tab(self):
        """Set up the users tab with user list and details"""
        # Create layout
        layout = QVBoxLayout(self.users_tab)
        
        # Create users tree
        self.users_tree = QTreeWidget()
        self.users_tree.setHeaderLabels(['User ID', 'Name', 'Guild', 'Last Active'])
        self.users_tree.setAlternatingRowColors(True)
        self.users_tree.setAnimated(True)
        
        # Set column widths
        self.users_tree.setColumnWidth(0, 100)
        self.users_tree.setColumnWidth(1, 150)
        self.users_tree.setColumnWidth(2, 150)
        self.users_tree.setColumnWidth(3, 150)
        
        layout.addWidget(self.users_tree)
        
        # Connect double-click to view profile
        self.users_tree.itemDoubleClicked.connect(self.view_user_profile)
        
        # Add refresh button
        refresh_btn = QPushButton("Refresh Users")
        refresh_btn.clicked.connect(self.load_users)
        layout.addWidget(refresh_btn)
    
    def setup_conversations_tab(self):
        """Set up the conversations tab with conversation list"""
        # Create layout
        layout = QVBoxLayout(self.conversations_tab)
        
        # Create conversations tree
        self.conversations_tree = QTreeWidget()
        self.conversations_tree.setHeaderLabels(['ID', 'User', 'Timestamp', 'Messages'])
        self.conversations_tree.setAlternatingRowColors(True)
        
        # Set column widths
        self.conversations_tree.setColumnWidth(0, 50)
        self.conversations_tree.setColumnWidth(1, 150)
        self.conversations_tree.setColumnWidth(2, 150)
        self.conversations_tree.setColumnWidth(3, 300)
        
        layout.addWidget(self.conversations_tree)
        
        # Connect double-click to view conversation
        self.conversations_tree.itemDoubleClicked.connect(self.view_conversation_details)
        
        # Add refresh button
        refresh_btn = QPushButton("Refresh Conversations")
        refresh_btn.clicked.connect(self.load_conversations)
        layout.addWidget(refresh_btn)
    
    def setup_logs_tab(self):
        """Set up the logs tab with log viewer"""
        # Create layout
        layout = QVBoxLayout(self.logs_tab)
        
        # Create log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # Control buttons
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh Logs")
        refresh_btn.clicked.connect(self.update_logs)
        btn_layout.addWidget(refresh_btn)
        
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        btn_layout.addWidget(clear_btn)
        
        # Auto refresh toggle
        self.auto_refresh_check = QCheckBox("Auto Refresh")
        self.auto_refresh_check.setChecked(self.auto_refresh)
        self.auto_refresh_check.toggled.connect(self.toggle_auto_refresh)
        btn_layout.addWidget(self.auto_refresh_check)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def setup_arxiv_tab(self):
        """Set up the ArXiv papers tab with paper list"""
        # Create layout
        layout = QVBoxLayout(self.arxiv_tab)
        
        # Create arxiv tree
        self.arxiv_tree = QTreeWidget()
        self.arxiv_tree.setHeaderLabels(['ArXiv ID', 'Title', 'Authors', 'Published', 'Categories'])
        self.arxiv_tree.setAlternatingRowColors(True)
        
        # Set column widths
        self.arxiv_tree.setColumnWidth(0, 100)
        self.arxiv_tree.setColumnWidth(1, 300)
        self.arxiv_tree.setColumnWidth(2, 200)
        self.arxiv_tree.setColumnWidth(3, 100)
        self.arxiv_tree.setColumnWidth(4, 150)
        
        # Make columns resizable
        header = self.arxiv_tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        layout.addWidget(self.arxiv_tree)
        
        # Connect double-click to view paper
        self.arxiv_tree.itemDoubleClicked.connect(self.view_paper_details)
        
        # Add refresh button
        refresh_btn = QPushButton("Refresh Papers")
        refresh_btn.clicked.connect(self.load_papers)
        layout.addWidget(refresh_btn)
    
    def setup_links_tab(self):
        """Set up the links tab with collected links"""
        # Create layout
        layout = QVBoxLayout(self.links_tab)
        
        # Create links tree
        self.links_tree = QTreeWidget()
        self.links_tree.setHeaderLabels(['URL', 'Title', 'Source', 'Collected'])
        self.links_tree.setAlternatingRowColors(True)
        
        # Set column widths
        self.links_tree.setColumnWidth(0, 300)
        self.links_tree.setColumnWidth(1, 200)
        self.links_tree.setColumnWidth(2, 150)
        self.links_tree.setColumnWidth(3, 100)
        
        # Make columns resizable
        header = self.links_tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        layout.addWidget(self.links_tree)
        
        # Button layout
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh Links")
        refresh_btn.clicked.connect(self.load_links)
        btn_layout.addWidget(refresh_btn)
        
        open_btn = QPushButton("Open Selected URL")
        open_btn.clicked.connect(self.open_url)
        btn_layout.addWidget(open_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Connect double-click to open URL
        self.links_tree.itemDoubleClicked.connect(self.open_url)
    
    def create_status_bar(self):
        """Create status bar at bottom of window"""
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Add status label with glow effect
        self.status_label = QLabel("Ready")
        self.statusBar.addWidget(self.status_label)
        
        # Add separator with neon glow
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {AcidTheme.ACCENT_PRIMARY};")
        self.statusBar.addPermanentWidget(separator)
        
        # Version info
        version_label = QLabel("v1.0.0")
        self.statusBar.addPermanentWidget(version_label)
    
    def apply_theme(self):
        """Apply the acid green neon theme to the application"""
        # Set application palette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(AcidTheme.BG_DARK))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(AcidTheme.TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Base, QColor(AcidTheme.BG_MEDIUM))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(AcidTheme.BG_DARK))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(AcidTheme.BG_DARK))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(AcidTheme.ACCENT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Text, QColor(AcidTheme.TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Button, QColor(AcidTheme.BG_MEDIUM))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(AcidTheme.ACCENT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(AcidTheme.ACCENT_PRIMARY))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(AcidTheme.BG_DARK))
        
        self.setPalette(palette)
        
        # Set global stylesheet
        self.setStyleSheet(f"""
            QMainWindow, QDialog {{
                background-color: {AcidTheme.BG_DARK};
            }}
            
            QTabWidget::pane {{
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                background-color: {AcidTheme.BG_DARK};
            }}
            
            QTabBar::tab {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_SECONDARY};
                padding: 8px 15px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            
            QTabBar::tab:selected {{
                background-color: {AcidTheme.ACCENT_PRIMARY};
                color: {AcidTheme.BG_DARK};
            }}
            
            QPushButton {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.ACCENT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                padding: 5px 15px;
                border-radius: 2px;
            }}
            
            QPushButton:hover {{
                background-color: {AcidTheme.ACCENT_PRIMARY};
                color: {AcidTheme.BG_DARK};
            }}
            
            QTreeWidget {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                alternate-background-color: {AcidTheme.BG_DARK};
            }}
            
            QHeaderView::section {{
                background-color: {AcidTheme.BG_DARK};
                color: {AcidTheme.ACCENT_PRIMARY};
                padding: 5px;
                border: none;
            }}
            
            QTextEdit {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
                selection-background-color: {AcidTheme.ACCENT_PRIMARY};
                selection-color: {AcidTheme.BG_DARK};
            }}
            
            QLabel {{
                color: {AcidTheme.TEXT_PRIMARY};
            }}
            
            QCheckBox {{
                color: {AcidTheme.TEXT_PRIMARY};
            }}
            
            QStatusBar {{
                background-color: {AcidTheme.BG_DARK};
                color: {AcidTheme.TEXT_PRIMARY};
                border-top: 1px solid {AcidTheme.ACCENT_PRIMARY};
            }}
            
            QMenuBar {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border-bottom: 1px solid {AcidTheme.ACCENT_PRIMARY};
            }}
            
            QMenuBar::item:selected {{
                background-color: {AcidTheme.ACCENT_PRIMARY};
                color: {AcidTheme.BG_DARK};
            }}
            
            QMenu {{
                background-color: {AcidTheme.BG_MEDIUM};
                color: {AcidTheme.TEXT_PRIMARY};
                border: 1px solid {AcidTheme.ACCENT_PRIMARY};
            }}
            
            QMenu::item:selected {{
                background-color: {AcidTheme.ACCENT_PRIMARY};
                color: {AcidTheme.BG_DARK};
            }}
        """)
    
    def create_menu(self):
        """Create the application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        start_action = QAction("Start Bot", self)
        start_action.triggered.connect(self.start_bot)
        file_menu.addAction(start_action)
        
        stop_action = QAction("Stop Bot", self)
        stop_action.triggered.connect(self.stop_bot)
        file_menu.addAction(stop_action)
        
        file_menu.addSeparator()
        
        backup_action = QAction("Backup Data", self)
        backup_action.triggered.connect(self.backup_data)
        file_menu.addAction(backup_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        refresh_action = QAction("Refresh Data", self)
        refresh_action.triggered.connect(self.load_data)
        tools_menu.addAction(refresh_action)
        
        clear_logs_action = QAction("Clear Logs", self)
        clear_logs_action.triggered.connect(self.clear_logs)
        tools_menu.addAction(clear_logs_action)
        
        tools_menu.addSeparator()
        
        edit_prompt_action = QAction("Edit System Prompt", self)
        edit_prompt_action.triggered.connect(self.edit_system_prompt)
        tools_menu.addAction(edit_prompt_action)
        
        config_action = QAction("Configure Bot", self)
        config_action.triggered.connect(self.edit_config)
        tools_menu.addAction(config_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        docs_action = QAction("Documentation", self)
        docs_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/Leoleojames1/OllamaDiscordTeacher/tree/master")))
        help_menu.addAction(docs_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def start_bot(self):
        """Start the Discord bot process"""
        # Update model display before starting
        self.update_model_display()
    
        if self.bot_process and self.bot_process.poll() is None:
            QMessageBox.information(self, "Bot Status", "Bot is already running!")
            return
            
        try:
            # Get the path to main.py
            bot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
            
            # Ensure it exists
            if not os.path.exists(bot_script):
                QMessageBox.critical(self, "Error", f"Bot script not found at: {bot_script}")
                return
                
            # Create environment variables with the proper data directory and model
            env = os.environ.copy()
            
            # Make sure we're using the currently selected model
            if self.active_model:
                env["OLLAMA_MODEL"] = self.active_model
                logger.info(f"Starting with model: {self.active_model}")
            
            # Start the bot as a subprocess
            self.bot_process = subprocess.Popen(
                [sys.executable, bot_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Log the process start
            if self.bot_process:
                self.log_message(f"Bot started with PID: {self.bot_process.pid}")
                
                # Create a thread to monitor process output
                try:
                    self.output_thread = ProcessOutputThread(self.bot_process)
                    self.output_thread.output_received.connect(self.log_message)
                    
                    # Make sure handle_process_end exists before connecting
                    if hasattr(self, 'handle_process_end'):
                        self.output_thread.process_ended.connect(self.handle_process_end)
                    else:
                        logger.error("handle_process_end method not found in BotManagerApp")
                    
                    self.output_thread.start()
                    
                    # Update UI
                    self.bot_status = "Running"
                    self.status_value.setText(self.bot_status)
                    self.start_bot_button.setEnabled(False)
                    self.stop_bot_button.setEnabled(True)
                    self.restart_bot_button.setEnabled(True)
                except Exception as thread_error:
                    logger.error(f"Error creating output thread: {thread_error}")
                    self.log_message(f"Warning: Bot is running but output monitoring failed: {thread_error}")
                    
        except Exception as e:
            self.log_message(f"Error starting bot: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to start bot: {str(e)}")

    def handle_bot_output(self, line):
        """Handle output from the bot process"""
        logger.info(f"Bot output: {line.strip()}")
        
        # Update activity log
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.activity_text.append(f"{timestamp} - {line}")
        
    def handle_bot_exit(self, exit_code):
        """Handle bot process exit"""
        logger.info(f"Bot process exited with code: {exit_code}")
        self.bot_status = "Stopped"
        self.status_value.setText(self.bot_status)
        
        # Update activity log
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.activity_text.append(f"{timestamp} - Bot stopped (exit code: {exit_code})\n")
        
        # Clean up
        self.bot_process = None

    def stop_bot(self):
        """Stop the running Discord bot."""
        if self.bot_process:
            try:
                self.log_message("Stopping Discord bot...")
                self.bot_status = "Stopping..."
                self.status_value.setText(self.bot_status)
                
                # First try to terminate gracefully
                if os.name == 'nt':  # Windows
                    # On Windows, use CTRL+C signal through taskkill
                    subprocess.run(f"taskkill /PID {self.bot_process.pid} /F", shell=True)
                else:
                    # On Unix systems
                    self.bot_process.terminate()
                    
                # Set a reasonable timeout for process termination
                try:
                    self.bot_process.wait(timeout=5)
                    self.log_message("Bot stopped successfully.")
                except subprocess.TimeoutExpired:
                    self.log_message("Bot process did not terminate within timeout, forcing...")
                    # Force kill if needed
                    if self.bot_process.poll() is None:  # Check if process is still running
                        if os.name == 'nt':  # Windows
                            # Should already be killed by taskkill /F above
                            pass
                        else:
                            self.bot_process.kill()
                
                # Clean up
                self.bot_process = None
                
                # Update UI state
                self.bot_status = "Stopped"
                self.status_value.setText(self.bot_status)
                
                # Enable/disable buttons
                if hasattr(self, 'start_bot_button'):
                    self.start_bot_button.setEnabled(True)
                if hasattr(self, 'stop_bot_button'):
                    self.stop_bot_button.setEnabled(False)
                if hasattr(self, 'restart_bot_button'):
                    self.restart_bot_button.setEnabled(False)
                    
            except Exception as e:
                self.log_message(f"Error stopping bot: {str(e)}")
                # Still update the UI state to prevent it from getting stuck
                self.bot_process = None
                self.bot_status = "Stopped"
                self.status_value.setText(self.bot_status)
                
                # Update buttons
                if hasattr(self, 'start_bot_button'):
                    self.start_bot_button.setEnabled(True)
                if hasattr(self, 'stop_bot_button'):
                    self.stop_bot_button.setEnabled(False)
                if hasattr(self, 'restart_bot_button'):
                    self.restart_bot_button.setEnabled(False)
        else:
            self.log_message("No bot process to stop.")

    def restart_bot(self):
        """Restart the Discord bot safely"""
        if not self.bot_process or self.bot_process.poll() is not None:
            # Bot not running, just start it
            return self.start_bot()
            
        try:
            # Signal we're restarting
            self.activity_text.append(f"{datetime.now().strftime('%H:%M:%S')} - Attempting to restart bot...")
            self.status_label.setText("Restarting bot...")
            QApplication.processEvents()  # Force UI update
            
            # Kill process forcefully - safer and more reliable
            if self.bot_process:
                pid = self.bot_process.pid
                self.activity_text.append(f"{datetime.now().strftime('%H:%M:%S')} - Forcefully terminating PID: {pid}")
                QApplication.processEvents()  # Force UI update
                
                # Use OS-specific kill command
                if sys.platform == 'win32':
                    # Windows - use taskkill to force kill
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], 
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                else:
                    # Unix-like - use kill -9
                    os.kill(pid, signal.SIGKILL)
                    
                # Wait briefly to ensure process is gone
                time.sleep(1)
                
                # Clear the reference
                self.bot_process = None
                self.status_value.setText("Stopped")
            
            # Now start fresh
            time.sleep(1)  # Brief pause
            self.status_label.setText("Starting bot...")
            QApplication.processEvents()  # Force UI update
            self.start_bot()
            
        except Exception as e:
            logger.error(f"Error restarting bot: {e}")
            self.status_label.setText(f"Error restarting bot: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to restart bot: {str(e)}")

    def backup_data(self):
        """Backup bot data to a zip file"""
        try:
            backup_dir = QFileDialog.getExistingDirectory(
                self, "Select Backup Directory", os.path.expanduser("~"),
                QFileDialog.Option.ShowDirsOnly
            )
            
            if not backup_dir:
                return  # User canceled
                
            # Create timestamp for backup name
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"bot_backup_{timestamp}.zip"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            import zipfile
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Backup data directory
                data_root = Path(DATA_DIR)
                if (data_root.exists()):
                    for file_path in data_root.rglob('*'):
                        if file_path.is_file():
                            relative_path = file_path.relative_to(data_root.parent)
                            zipf.write(file_path, relative_path)
                
                # Backup config files
                config_files = ['config.py', '.env']
                for config_file in config_files:
                    if os.path.exists(config_file):
                        zipf.write(config_file)
                
            QMessageBox.information(self, "Backup Complete", f"Data backed up to {backup_path}")
            self.status_label.setText(f"Backup saved to {backup_path}")
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create backup: {str(e)}")

    def edit_system_prompt(self):
        """Open dialog to edit system prompt"""
        dialog = SystemPromptDialog(self)
        dialog.exec()

    def edit_config(self):
        """Open dialog to edit bot configuration"""
        dialog = ConfigDialog(self)
        dialog.exec()

    def show_about(self):
        """Display about information"""
        QMessageBox.about(self, "About Ollama Teacher Bot Manager", 
            """<h1>Ollama Teacher Bot Manager</h1>
            <p>Version 1.0.0</p>
            <p>A management interface for the Ollama Teacher Discord bot.</p>
            <p>Created for managing AI-powered education on Discord.</p>
            <p>&copy; 2025. All rights reserved.</p>"""
        )

    def create_central_widget(self):
        """Create the central widget with tabs"""
        # Create the tab widget
        self.tabs = QTabWidget()
        
        # Create individual tabs
        self.dashboard_tab = QWidget()
        self.users_tab = QWidget()
        self.conversations_tab = QWidget()
        self.logs_tab = QWidget()
        self.arxiv_tab = QWidget()
        self.links_tab = QWidget()
        
        # Add tabs to the widget
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.users_tab, "Users")
        self.tabs.addTab(self.conversations_tab, "Conversations")
        self.tabs.addTab(self.logs_tab, "Logs")
        self.tabs.addTab(self.arxiv_tab, "ArXiv Papers")
        self.tabs.addTab(self.links_tab, "Links")
        
        # Set up the individual tabs
        self.setup_dashboard_tab()
        self.setup_users_tab()
        self.setup_conversations_tab()
        self.setup_logs_tab()
        self.setup_arxiv_tab()
        self.setup_links_tab()
        
        # Set as central widget
        self.setCentralWidget(self.tabs)

    def load_data(self):
        """Load all data from the data directories."""
        try:
            logging.info(f"Loading data from {DATA_DIR}")
            self.ensure_data_directories()
            
            # Log directory existence
            logging.info(f"DATA_DIR exists: {os.path.exists(DATA_DIR)}")
            
            # Load papers
            self.load_papers()
            
            # Load links
            self.load_links()
            
            # Load user profiles
            self.load_users()
            
            # Load conversations
            self.load_conversations()
            
            # Load crawls
            self.load_crawls()
            
            # Load searches
            self.load_searches()
            
            # Update dashboard statistics
            self.update_dashboard_stats()
            
        except Exception as e:
            logging.error(f"Error loading data: {e}")
            QMessageBox.warning(self, "Data Loading Error", f"Error loading data: {str(e)}")

    def load_users(self):
        """Load user profiles from storage"""
        try:
            # Clear existing items
            self.users_tree.clear()
            
            # Get user profiles directory
            user_profiles_dir = Path(f"{DATA_DIR}/user_profiles")
            if not user_profiles_dir.exists():
                return
                
            # Find all profile files
            profile_files = list(user_profiles_dir.glob("*_profile.json"))
            
            # Load each profile
            user_count = 0
            for profile_file in profile_files:
                try:
                    with open(profile_file, 'r') as f:
                        profile_data = json.load(f)
                    
                    # Extract user ID from filename
                    user_id = profile_file.stem.replace('_profile', '')
                    
                    # Create tree item
                    item = QTreeWidgetItem([
                        user_id,
                        profile_data.get('username', 'Unknown'),
                        profile_data.get('guild', 'Unknown'),
                        profile_data.get('timestamp', '')[:19]  # Format timestamp
                    ])
                    
                    self.users_tree.addTopLevelItem(item)
                    user_count += 1
                    
                except Exception as e:
                    logger.error(f"Error loading profile {profile_file}: {e}")
            
            # Update user count on dashboard
            self.user_count = user_count
            self.users_value.setText(str(user_count))
            
        except Exception as e:
            logger.error(f"Error loading users: {e}")

    def load_conversations(self):
        """Load conversation history from storage"""
        try:
            # Clear existing items
            self.conversations_tree.clear()
            
            # Get guilds directory
            guilds_dir = Path(f"{DATA_DIR}/guilds")
            if not guilds_dir.exists():
                return
                
            # Find all conversation files across all guilds
            conversation_count = 0
            for guild_dir in guilds_dir.iterdir():
                if guild_dir.is_dir():
                    user_dirs = guild_dir.glob("*")
                    for user_dir in user_dirs:
                        if user_dir.is_dir():
                            conv_file = user_dir / "conversation.json"
                            if conv_file.exists():
                                try:
                                    with open(conv_file, 'r') as f:
                                        conversation = json.load(f)
                                    
                                    # Get user ID and guild ID
                                    user_id = user_dir.name
                                    guild_id = guild_dir.name
                                    
                                    # Get message count
                                    message_count = len(conversation.get('messages', []))
                                    
                                    # Get last timestamp
                                    last_timestamp = "Unknown"
                                    if message_count > 0:
                                        last_message = conversation['messages'][-1]
                                        last_timestamp = last_message.get('timestamp', '')[:19]
                                    
                                    # Create tree item
                                    item = QTreeWidgetItem([
                                        f"{guild_id[:8]}...",
                                        user_id,
                                        last_timestamp,
                                        str(message_count)
                                    ])
                                    
                                    self.conversations_tree.addTopLevelItem(item)
                                    conversation_count += 1
                                    
                                except Exception as e:
                                    logger.error(f"Error loading conversation {conv_file}: {e}")
            
            # Update conversation count on dashboard
            self.total_conversations = conversation_count
            self.conversations_value.setText(str(conversation_count))

        except Exception as e:
            logger.error(f"Error loading conversations: {e}")

    def load_papers(self):
        """Load ArXiv papers from storage"""
        try:
            # Clear existing items
            self.arxiv_tree.clear()
            
            # Get papers directory
            papers_dir = Path(f"{DATA_DIR}/papers")
            if not papers_dir.exists():
                logger.warning(f"Papers directory not found: {papers_dir}")
                return
                
            # Find all paper files, excluding the all_papers.parquet
            paper_files = [f for f in papers_dir.glob("*.parquet") if f.name != "all_papers.parquet"]
            
            # Load each paper
            papers_loaded = 0
            for paper_file in paper_files:
                try:
                    df = ParquetStorage.load_from_parquet(str(paper_file))
                    if df is not None and not df.empty:
                        # Get first row as paper data
                        paper_data = df.iloc[0].to_dict()
                        
                        # Extract ArXiv ID from filename
                        arxiv_id = paper_file.stem
                        
                        # Format authors and categories as comma-separated strings
                        authors = ", ".join(paper_data.get('authors', [])) if isinstance(paper_data.get('authors'), list) else str(paper_data.get('authors', ''))
                        categories = ", ".join(paper_data.get('categories', [])) if isinstance(paper_data.get('categories'), list) else str(paper_data.get('categories', ''))
                        
                        # Format published date (trim to just the date part)
                        published = paper_data.get('published', '')
                        if published and isinstance(published, str) and len(published) > 10:
                            published = published[:10]  # Get just YYYY-MM-DD part
                        
                        # Create tree item
                        item = QTreeWidgetItem([
                            arxiv_id,
                            paper_data.get('title', 'Unknown'),
                            authors,
                            published,
                            categories
                        ])
                        
                        self.arxiv_tree.addTopLevelItem(item)
                        papers_loaded += 1
                except Exception as e:
                    logger.error(f"Error loading paper {paper_file}: {e}")
            
            # Update status
            self.status_label.setText(f"Loaded {papers_loaded} papers")
            logger.info(f"Loaded {papers_loaded} papers from {len(paper_files)} paper files")
            
        except Exception as e:
            logger.error(f"Error loading papers: {e}")
            self.status_label.setText(f"Error loading papers: {str(e)}")

    def load_links(self):
        """Load collected links from storage"""
        try:
            # Clear existing items
            self.links_tree.clear()
            
            # Get links directory
            links_dir = Path(f"{DATA_DIR}/links")
            if not links_dir.exists():
                logger.warning(f"Links directory not found: {links_dir}")
                return
                
            # Find all links files
            link_files = list(links_dir.glob("*.parquet"))
            
            # Load each link file
            total_links = 0
            for link_file in link_files:
                try:
                            # Create tree item
                            item = QTreeWidgetItem([
                                row.get('url', ''),
                                row.get('title', 'Unknown'),
                                row.get('source', 'Unknown'),
                                row.get('timestamp', '')[:19]  # Format timestamp
                            ])
                            
                            self.links_tree.addTopLevelItem(item)
                            total_links += 1
                except Exception as e:
                    logger.error(f"Error loading links from {link_file}: {e}")
            
            # Update status
            self.status_label.setText(f"Loaded {total_links} links from {len(link_files)} files")
            logger.info(f"Loaded {total_links} links from {len(link_files)} files")
            
        except Exception as e:
            logger.error(f"Error loading links: {e}")
            self.status_label.setText(f"Error loading links: {str(e)}")

    def load_crawls(self):
        """Load crawled web pages data."""
        try:
            crawls_dir = os.path.join(DATA_DIR, "crawls")
            if not os.path.exists(crawls_dir):
                return
                
            # Clear the existing items
            self.crawls_tree.clear()
            
            # Get all parquet files
            crawl_files = list(Path(crawls_dir).glob("*.parquet"))
            
            for file_path in crawl_files:
                try:
                    # Load data
                    data = ParquetStorage.load_from_parquet(str(file_path))
                    if data is None or data.empty:
                        continue
                        
                    # Extract metadata
                    url = data.get('url', ['Unknown URL'])[0] if 'url' in data else "Unknown URL"
                    timestamp = data.get('timestamp', [''])[0] if 'timestamp' in data else ""
                    title = data.get('title', ['Unknown Title'])[0] if 'title' in data else "Unknown Title"
                    
                    # Create tree item
                    item = QTreeWidgetItem(self.crawls_tree)
                    item.setText(0, title)
                    item.setText(1, url)
                    item.setText(2, timestamp[:10] if timestamp else "")
                    item.setData(0, Qt.UserRole, str(file_path))
                    
                except Exception as e:
                    logging.error(f"Error loading crawl data from {file_path}: {e}")
                    
            # Update count
            self.crawls_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            self.crawls_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            
        except Exception as e:
            logging.error(f"Error loading crawls: {e}")

    def load_searches(self):
        """Load search results data."""
        try:
            searches_dir = os.path.join(DATA_DIR, "searches")
            if not os.path.exists(searches_dir):
                return
                
            # Clear the existing items
            self.searches_tree.clear()
            
            # Get all parquet files
            search_files = list(Path(searches_dir).glob("*.parquet"))
            
            for file_path in search_files:
                try:
                    # Load data
                    data = ParquetStorage.load_from_parquet(str(file_path))
                    if data is None or data.empty:
                        continue
                        
                    # Extract metadata
                    query = data.get('query', [''])[0] if 'query' in data else ""
                    timestamp = data.get('timestamp', [''])[0] if 'timestamp' in data else ""
                    
                    # Create tree item
                    item = QTreeWidgetItem(self.searches_tree)
                    item.setText(0, query)
                    item.setText(1, timestamp[:19] if timestamp else "")
                    item.setData(0, Qt.UserRole, str(file_path))
                    
                except Exception as e:
                    logging.error(f"Error loading search data from {file_path}: {e}")
                    
            # Update count
            self.searches_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            
        except Exception as e:
            logging.error(f"Error loading searches: {e}")

    def update_logs(self):
        """Update log content from the log file"""
        try:
            if os.path.exists("bot_manager.log"):
                with open("bot_manager.log", 'r') as f:
                    self.log_text.setText(f.read())
                    # Scroll to bottom
                    self.log_text.moveCursor(QTextCursor.MoveOperation.End)
            
        except Exception as e:
            logger.error(f"Error updating logs: {e}")

    def clear_logs(self):
        """Clear the log content"""
        try:
            # Clear the log viewer
            self.log_text.clear()
            
            # Optionally truncate the log file
            with open("bot_manager.log", 'w') as f:
                f.write("Log cleared at " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "\n")
            
            self.status_label.setText("Logs cleared")
            
        except Exception as e:
            logger.error(f"Error clearing logs: {e}")
            self.status_label.setText(f"Error clearing logs: {str(e)}")

    def update_log_content(self, content):
        """Update log content from the log monitor thread"""
        self.log_text.setText(content)
        # Scroll to bottom
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def toggle_auto_refresh(self):
        """Toggle auto refresh for logs"""
        self.auto_refresh = self.auto_refresh_check.isChecked()
        
        if self.auto_refresh:
            # Start timer to auto-refresh logs
            self.refresh_timer.start(5000)  # 5 seconds
        else:
            # Stop timer
            self.refresh_timer.stop()

    def periodic_refresh(self):
        """Perform periodic refresh of data"""
        if self.auto_refresh:
            self.update_logs()

    def update_dashboard_stats(self):
        """Update dashboard statistics"""
        try:
            # Count users from profiles
            user_profiles_dir = Path(f"{DATA_DIR}/user_profiles")
            if user_profiles_dir.exists():
                profiles = list(user_profiles_dir.glob("*_profile.json"))
                self.user_count = len(profiles)
                self.users_value.setText(str(self.user_count))
            
            # Count conversations
            conversations_count = 0
            guilds_dir = Path(f"{DATA_DIR}/guilds")
            if guilds_dir.exists():
                for guild_dir in guilds_dir.iterdir():
                    if guild_dir.is_dir():
                        user_dirs = guild_dir.glob("*")
                        for user_dir in user_dirs:
                            if user_dir.is_dir():
                                conv_file = user_dir / "conversation.json"
                                if conv_file.exists():
                                    conversations_count += 1
                                    
            self.total_conversations = conversations_count
            self.conversations_value.setText(str(conversations_count))
            
            # Update model info
            self.model_value.setText(self.active_model)
            
        except Exception as e:
            logger.error(f"Error updating dashboard stats: {e}")

    def view_user_profile(self, item):
        """View user profile details"""
        user_id = item.text(0)
        
        try:
            # Load profile data
            profile_path = Path(f"{DATA_DIR}/user_profiles/{user_id}_profile.json")
            if not profile_path.exists():
                QMessageBox.warning(self, "Profile Not Found", f"No profile found for user {user_id}")
                return
                
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
                
            # Show profile dialog
            dialog = ProfileDialog(profile_data, user_id, self)
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error viewing user profile: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load profile: {str(e)}")

    def view_conversation_details(self, item):
        """View conversation details"""
        guild_id = item.text(0).replace("...", "")  # Remove truncation
        user_id = item.text(1)
        
        try:
            # Load conversation data
            conv_path = Path(f"{DATA_DIR}/guilds/{guild_id}/{user_id}/conversation.json")
            if not conv_path.exists():
                QMessageBox.warning(self, "Conversation Not Found", "Conversation file not found")
                return
                
            with open(conv_path, 'r') as f:
                conversation = json.load(f)
                
            # Format conversation for display
            formatted_text = f"# Conversation with {user_id} in guild {guild_id}\n\n"
            
            for msg in conversation.get('messages', []):
                role = msg.get('role', 'unknown')
                timestamp = msg.get('timestamp', '')[:19]  # Format timestamp
                content = msg.get('content', '')
                
                formatted_text += f"**{role}** ({timestamp}):\n{content}\n\n"
                
            # Show in a dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Conversation: {user_id}")
            dialog.resize(700, 500)
            
            layout = QVBoxLayout(dialog)
            
            # Conversation text area
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setMarkdown(formatted_text)
            layout.addWidget(text_edit)
            
            # Close button
            btn_layout = QHBoxLayout()
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            btn_layout.addStretch()
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)
            
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error viewing conversation: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load conversation: {str(e)}")

    def view_paper_details(self, item):
        """View ArXiv paper details"""
        arxiv_id = item.text(0)
        
        try:
            # Load paper data
            paper_path = Path(f"{DATA_DIR}/papers/{arxiv_id}.parquet")
            if not paper_path.exists():
                QMessageBox.warning(self, "Paper Not Found", f"No paper found with ID {arxiv_id}")
                return
                
            df = ParquetStorage.load_from_parquet(str(paper_path))
            if df is None or df.empty:
                QMessageBox.warning(self, "Paper Data Error", f"Paper file exists but data could not be loaded")
                return
                
            paper_data = df.iloc(0).to_dict()
            
            # Show paper dialog
            dialog = PaperDialog(paper_data, arxiv_id, self)
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error viewing paper details: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load paper details: {str(e)}")

    def open_url(self, item=None):
        """Open the selected URL in default browser"""
        try:
            # Get selected item from tree
            if item is None:
                selected_items = self.links_tree.selectedItems()
                if not selected_items:
                    QMessageBox.information(self, "No Selection", "Please select a URL to open")
                    return
                item = selected_items[0]
                
            # Get URL from first column
            url = item.text(0)
            
            # Open in browser
            QDesktopServices.openUrl(QUrl(url))
            
        except Exception as e:
            logger.error(f"Error opening URL: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open URL: {str(e)}")

    def ensure_data_directories(self):
        """Ensure all required data directories exist"""
        try:
            data_root = Path(DATA_DIR)
            data_root.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories
            subdirs = ["papers", "searches", "crawls", "links", "user_profiles", "guilds"]
            for subdir in subdirs:
                (data_root / subdir).mkdir(exist_ok=True)
                
        except Exception as e:
            logger.error(f"Error creating data directories: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create data directories: {str(e)}")

    def pulse_status(self):
        """Create a pulsing effect for the status label"""
        # Define pulse colors (gradual fading between accent color and text color)
        pulse_colors = [
            f"color: {AcidTheme.ACCENT_PRIMARY};",
            f"color: rgba(57, 255, 20, 0.9);",
            f"color: rgba(57, 255, 20, 0.8);",
            f"color: rgba(57, 255, 20, 0.7);",
            f"color: rgba(57, 255, 20, 0.6);",
            f"color: rgba(57, 255, 20, 0.5);",
            f"color: rgba(57, 255, 20, 0.6);",
            f"color: rgba(57, 255, 20, 0.7);",
            f"color: rgba(57, 255, 20, 0.8);",
            f"color: rgba(57, 255, 20, 0.9);"
        ]
        
        # Set the color based on current pulse index
        self.status_label.setStyleSheet(pulse_colors[self.pulse_index])
        
        # Increment pulse index
        self.pulse_index = (self.pulse_index + 1) % len(pulse_colors)

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop bot if it's running
        if self.bot_process and self.bot_process.poll() is None:
            try:
                # Try to stop gracefully
                self.stop_bot()
            except:
                # Force kill if necessary
                if self.bot_process:
                    self.bot_process.kill()
        
        # Stop threads
        if self.log_thread:
            self.log_thread.stop()
        
        if self.process_thread:
            self.process_thread.quit()
            self.process_thread.wait()
        
        # Stop timers
        self.refresh_timer.stop()
        self.pulse_timer.stop()
        
        # Accept the close event
        event.accept()

    def update_model_display(self):
        """Update the displayed model names from environment variables"""
        try:
            # Get base model from environment
            base_model = os.getenv('OLLAMA_MODEL', '')
            if not base_model:
                self.model_value.setText("Not set in .env")
            else:
                self.model_value.setText(base_model)
                self.active_model = base_model
                
            # Get vision model from environment
            vision_model = os.getenv('OLLAMA_VISION_MODEL', '')
            if not vision_model:
                self.vision_model_value.setText("Not set in .env")
            else:
                self.vision_model_value.setText(vision_model)
                
            logger.info(f"Updated models display - Base: {base_model}, Vision: {vision_model}")
            
        except Exception as e:
            logger.error(f"Error updating model display: {e}")
            self.model_value.setText("Error retrieving models")
            self.vision_model_value.setText("Error retrieving models")

    def log_message(self, message):
        """Add a message to the activity log."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Make sure the activity_text widget exists
        if hasattr(self, 'activity_text'):
            self.activity_text.append(f"{timestamp} - {message}")
            # Ensure the newest message is visible
            self.activity_text.moveCursor(QTextCursor.MoveOperation.End)
        
        # Also log to the logger
        logger.info(message)
        
        # Update the status bar briefly
        if hasattr(self, 'status_label'):
            self.status_label.setText(message)
            # Reset after a delay
            QTimer.singleShot(5000, lambda: self.status_label.setText("Ready"))

    def handle_process_end(self, exit_code):
        """Handle bot process exit"""
        logger.info(f"Bot process exited with code: {exit_code}")
        self.bot_status = "Stopped"
        self.status_value.setText(self.bot_status)
        
        # Update activity log
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.activity_text.append(f"{timestamp} - Bot stopped (exit code: {exit_code})\n")
        
        # Clean up
        self.bot_process = None
        
        # Re-enable start button, disable stop and restart buttons
        self.start_bot_button.setEnabled(True)
        self.stop_bot_button.setEnabled(False)
        self.restart_bot_button.setEnabled(False)

    def change_base_model(self, selected_model):
        """Handle base model selection change"""
        if selected_model in ["Fetching models...", "Loading models...", "Error fetching models", "No models found"]:
            return
            
        try:
            # Update .env file
            env_path = ".env"
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    lines = f.readlines()
                # Remove existing base model line
                lines = [line for line in lines if not line.startswith('OLLAMA_MODEL=')]
                # Add new base model line
                lines.append(f"OLLAMA_MODEL={selected_model}\n")
                with open(env_path, 'w') as f:
                    f.writelines(lines)
            else:
                with open(env_path, 'w') as f:
                    f.write(f"OLLAMA_MODEL={selected_model}\n")
                    
            # Update environment variable
            os.environ['OLLAMA_MODEL'] = selected_model
            
            # Update UI
            self.active_model = selected_model
            self.model_value.setText(selected_model)
            self.log_message(f"Base model changed to: {selected_model}")
            
        except Exception as e:
            self.log_message(f"Error changing base model: {e}")

    def change_vision_model(self, selected_model):
        """Handle vision model selection change"""
        if selected_model in ["Fetching models...", "Loading models...", "Error fetching models", "No models found"]:
            return
            
        try:
            # Update .env file
            env_path = ".env"
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    lines = f.readlines()
                # Remove existing vision model line
                lines = [line for line in lines if not line.startswith('OLLAMA_VISION_MODEL=')]
                # Add new vision model line
                lines.append(f"OLLAMA_VISION_MODEL={selected_model}\n")
                with open(env_path, 'w') as f:
                    f.writelines(lines)
            else:
                with open(env_path, 'w') as f:
                    f.write(f"OLLAMA_VISION_MODEL={selected_model}\n")
                    
            # Update environment variable
            os.environ['OLLAMA_VISION_MODEL'] = selected_model
            
            # Update UI
            self.vision_model_value.setText(selected_model)
            self.log_message(f"Vision model changed to: {selected_model}")
            
        except Exception as e:
            self.log_message(f"Error changing vision model: {e}")

    def fetch_vision_models(self):
        """Fetch available models for vision tasks"""
        try:
            # Show loading state
            self.vision_model_combo.clear()
            self.vision_model_combo.addItem("Fetching models...")
            self.vision_model_combo.setEnabled(False)
            
            class VisionModelsFetchThread(QThread):
                models_fetched = pyqtSignal(object)
                error_occurred = pyqtSignal(str)
                
                def run(self):
                    try:
                        import ollama
                        models = ollama.list()
                        self.models_fetched.emit(models)
                    except Exception as e:
                        self.error_occurred.emit(str(e))

            # Create and start thread
            thread = VisionModelsFetchThread(self)
            thread.models_fetched.connect(self.process_vision_models)
            thread.error_occurred.connect(lambda e: self.log_message(f"Vision model fetch error: {e}"))
            thread.start()

        except Exception as e:
            self.log_message(f"Error fetching vision models: {e}")
            self.vision_model_combo.clear()
            self.vision_model_combo.addItem("Error fetching models")
            self.vision_model_combo.setEnabled(False)

    def process_vision_models(self, models_list):
        """Process fetched models for vision model dropdown"""
        try:
            self.vision_model_combo.clear()
            self.vision_model_combo.setEnabled(True)
            
            # Get current vision model
            current_model = os.getenv('OLLAMA_VISION_MODEL', '')
            current_idx = 0
            
            # Extract model names
            model_names = []
            
            if hasattr(models_list, 'models'):
                models = models_list.models
            elif isinstance(models_list, dict) and 'models' in models_list:
                models = models_list['models']
            else:
                models = []

            for model in models:
                model_name = (model.get('model') or model.get('name') if isinstance(model, dict) 
                            else getattr(model, 'model', None) or getattr(model, 'name', None))
                
                if model_name:
                    model_names.append(model_name)
                    if model_name == current_model:
                        current_idx = len(model_names) - 1

            if not model_names:
                self.vision_model_combo.addItem("No models found")
                return
                
            # Add all models to combobox
            self.vision_model_combo.addItems(model_names)
            
            # Select current model if set
            if current_idx < len(model_names):
                self.vision_model_combo.setCurrentIndex(current_idx)
            
            logger.info(f"Loaded {len(model_names)} vision models")
            
        except Exception as e:
            self.log_message(f"Error processing vision models: {e}")
            self.vision_model_combo.addItem("Error processing models")

def main():
    """Main function to start the Bot Manager application"""
    app = QApplication(sys.argv)
    
    # Create and show the main window
    window = BotManagerApp()
    window.show()
    
    # Start the event loop
    sys.exit(app.exec())

if __name__ == '__main__':
    main()