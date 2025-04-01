import os
import sys
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime, timezone, UTC
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import subprocess
import signal
import webbrowser

# use pyqy6 instead of tkinter

# Import bot modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import ParquetStorage
from config import DATA_DIR, MODEL_NAME, SYSTEM_PROMPT

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

# Define theme colors for the acid green neon goop theme
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

class BotManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ollama Teacher Bot Manager")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # Set dark background
        self.root.configure(bg=AcidTheme.BG_DARK)
        
        # Configure ttk style for modern look
        self.setup_theme()
        
        self.bot_process = None
        self.log_update_job = None
        self.auto_refresh = tk.BooleanVar(value=False)  # Initialize here
        
        # Bot status variables
        self.bot_status = tk.StringVar(value="Stopped")
        self.active_model = tk.StringVar(value=MODEL_NAME)
        self.user_count = tk.IntVar(value=0)
        self.total_conversations = tk.IntVar(value=0)
        
        # Create the UI components - REORDERED for proper initialization
        self.create_menu()
        self.create_status_bar()  # Create status bar FIRST
        self.create_notebook()    # Then create notebook with tabs
        
        # Initialize data directories if they don't exist
        self.ensure_data_directories()
        
        # Initial load
        self.load_data()
        
        # Set up periodic refresh
        self.root.after(5000, self.periodic_refresh)
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Call this to start the neon pulsing effect
        self.root.after(800, self.pulse_status)
        
    def setup_theme(self):
        """Set up the enhanced ultra-hyper modern acid green neon goop theme"""
        style = ttk.Style()
        style.theme_use('default')
        
        # Configure frames with neon glow effect
        style.configure('TFrame', background=AcidTheme.BG_DARK)
        style.configure('Glow.TFrame', background=AcidTheme.BG_DARK, borderwidth=1, 
                       relief='solid', bordercolor=AcidTheme.ACCENT_PRIMARY)
        
        # Configure LabelFrame with neon border and glowing effect
        style.configure('TLabelframe', background=AcidTheme.BG_DARK)
        style.configure('TLabelframe.Label', background=AcidTheme.BG_DARK, foreground=AcidTheme.ACCENT_PRIMARY,
                       font=('Segoe UI', 10, 'bold'))
        
        # Configure buttons with neon glow effect and rounded corners (where supported)
        style.configure('TButton', 
                      background=AcidTheme.BG_MEDIUM, 
                      foreground=AcidTheme.ACCENT_PRIMARY,
                      borderwidth=1,
                      relief='flat',
                      focusthickness=3,
                      focuscolor=AcidTheme.ACCENT_SECONDARY)
        
        # Button hover effects
        style.map('TButton', 
                background=[('active', AcidTheme.ACCENT_PRIMARY),
                          ('hover', AcidTheme.BG_MEDIUM)],
                foreground=[('active', AcidTheme.BG_DARK),
                          ('hover', AcidTheme.ACCENT_SECONDARY)])
                      
        # Configure special buttons
        style.configure('Start.TButton', 
                      background=AcidTheme.ACCENT_PRIMARY, 
                      foreground=AcidTheme.BG_DARK,
                      font=('Segoe UI', 9, 'bold'))
                      
        style.configure('Stop.TButton', 
                      background=AcidTheme.DANGER, 
                      foreground=AcidTheme.TEXT_PRIMARY,
                      font=('Segoe UI', 9, 'bold'))
        
        # Configure labels with neon text
        style.configure('TLabel', background=AcidTheme.BG_DARK, foreground=AcidTheme.TEXT_PRIMARY)
        style.configure('Status.TLabel', foreground=AcidTheme.ACCENT_PRIMARY, font=('Segoe UI', 9, 'bold'))
        style.configure('Title.TLabel', foreground=AcidTheme.ACCENT_PRIMARY, font=('Segoe UI', 14, 'bold'))
        
        # Configure notebook with neon tabs
        style.configure('TNotebook', background=AcidTheme.BG_DARK, borderwidth=0)
        style.configure('TNotebook.Tab', 
                      background=AcidTheme.BG_MEDIUM,
                      foreground=AcidTheme.TEXT_SECONDARY,
                      padding=[15, 5],
                      font=('Segoe UI', 9),
                      borderwidth=0)
        
        style.map('TNotebook.Tab',
                background=[('selected', AcidTheme.ACCENT_PRIMARY)],
                foreground=[('selected', AcidTheme.BG_DARK)],
                expand=[('selected', [1, 1, 1, 0])])
        
        # Configure treeview with neon highlights
        style.configure('Treeview', 
                      background=AcidTheme.BG_MEDIUM,
                      foreground=AcidTheme.TEXT_PRIMARY,
                      fieldbackground=AcidTheme.BG_MEDIUM,
                      font=('Segoe UI', 9),
                      borderwidth=0,
                      rowheight=25)
        
        style.map('Treeview', 
                background=[('selected', AcidTheme.ACCENT_SECONDARY)],
                foreground=[('selected', AcidTheme.BG_DARK)])
                      
        # Configure separators with neon glow
        style.configure('TSeparator', background=AcidTheme.ACCENT_PRIMARY)
        
        # Configure scrollbars with neon style
        style.configure('TScrollbar', 
                      background=AcidTheme.BG_MEDIUM, 
                      troughcolor=AcidTheme.BG_DARK,
                      borderwidth=0,
                      arrowcolor=AcidTheme.ACCENT_PRIMARY)
        style.map('TScrollbar',
                background=[('active', AcidTheme.ACCENT_PRIMARY)],
                arrowcolor=[('active', AcidTheme.BG_DARK)])
        
    def create_menu(self):
        """Create the application menu bar"""
        menubar = tk.Menu(self.root, bg=AcidTheme.BG_MEDIUM, fg=AcidTheme.TEXT_PRIMARY, 
                          activebackground=AcidTheme.ACCENT_PRIMARY, activeforeground=AcidTheme.BG_DARK,
                          borderwidth=0)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=AcidTheme.BG_MEDIUM, fg=AcidTheme.TEXT_PRIMARY,
                           activebackground=AcidTheme.ACCENT_PRIMARY, activeforeground=AcidTheme.BG_DARK)
        file_menu.add_command(label="Start Bot", command=self.start_bot)
        file_menu.add_command(label="Stop Bot", command=self.stop_bot)
        file_menu.add_separator()
        file_menu.add_command(label="Backup Data", command=self.backup_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0, bg=AcidTheme.BG_MEDIUM, fg=AcidTheme.TEXT_PRIMARY,
                            activebackground=AcidTheme.ACCENT_PRIMARY, activeforeground=AcidTheme.BG_DARK)
        tools_menu.add_command(label="Refresh Data", command=self.load_data)
        tools_menu.add_command(label="Clear Logs", command=self.clear_logs)
        tools_menu.add_separator()
        tools_menu.add_command(label="Edit System Prompt", command=self.edit_system_prompt)
        tools_menu.add_command(label="Configure Bot", command=self.edit_config)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=AcidTheme.BG_MEDIUM, fg=AcidTheme.TEXT_PRIMARY,
                           activebackground=AcidTheme.ACCENT_PRIMARY, activeforeground=AcidTheme.BG_DARK)
        help_menu.add_command(label="Documentation", command=lambda: webbrowser.open("https://github.com/Leoleojames1/OllamaDiscordTeacher/tree/master"))
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def create_notebook(self):
        """Create tabbed interface"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.dashboard_tab = ttk.Frame(self.notebook)
        self.users_tab = ttk.Frame(self.notebook)
        self.conversations_tab = ttk.Frame(self.notebook)
        self.logs_tab = ttk.Frame(self.notebook)
        self.arxiv_tab = ttk.Frame(self.notebook)
        self.links_tab = ttk.Frame(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.users_tab, text="Users")
        self.notebook.add(self.conversations_tab, text="Conversations")
        self.notebook.add(self.logs_tab, text="Logs")
        self.notebook.add(self.arxiv_tab, text="ArXiv Papers")
        self.notebook.add(self.links_tab, text="Links")
        
        # Setup tab content
        self.setup_dashboard_tab()
        self.setup_users_tab()
        self.setup_conversations_tab()
        self.setup_logs_tab()
        self.setup_arxiv_tab()
        self.setup_links_tab()
    
    def setup_dashboard_tab(self):
        """Set up the dashboard tab with summary info and controls"""
        # Control frame
        control_frame = ttk.LabelFrame(self.dashboard_tab, text="Bot Control")
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Start/Stop buttons
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        start_btn = ttk.Button(btn_frame, text="Start Bot", command=self.start_bot, style='Start.TButton')
        start_btn.pack(side=tk.LEFT, padx=5)
        
        stop_btn = ttk.Button(btn_frame, text="Stop Bot", command=self.stop_bot, style='Stop.TButton')
        stop_btn.pack(side=tk.LEFT, padx=5)
        
        restart_btn = ttk.Button(btn_frame, text="Restart Bot", command=self.restart_bot)
        restart_btn.pack(side=tk.LEFT, padx=5)
        
        # Stats frame
        stats_frame = ttk.LabelFrame(self.dashboard_tab, text="Bot Statistics")
        stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create grid for stats
        grid_frame = ttk.Frame(stats_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Row 1
        ttk.Label(grid_frame, text="Bot Status:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        status_label = ttk.Label(grid_frame, textvariable=self.bot_status, style='Status.TLabel')
        status_label.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(grid_frame, text="Active Model:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Label(grid_frame, textvariable=self.active_model, style='Status.TLabel').grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        
        # Row 2
        ttk.Label(grid_frame, text="Unique Users:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(grid_frame, textvariable=self.user_count, style='Status.TLabel').grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(grid_frame, text="Total Conversations:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Label(grid_frame, textvariable=self.total_conversations, style='Status.TLabel').grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        
        # Recent activity frame
        activity_frame = ttk.LabelFrame(self.dashboard_tab, text="Recent Activity")
        activity_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Activity list
        self.activity_text = scrolledtext.ScrolledText(activity_frame, height=10, bg=AcidTheme.BG_MEDIUM, 
                                                     fg=AcidTheme.TEXT_PRIMARY, insertbackground=AcidTheme.ACCENT_PRIMARY,
                                                     borderwidth=0, highlightthickness=1, highlightcolor=AcidTheme.ACCENT_PRIMARY)
        self.activity_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
    # Add more UI setup methods here...
    
    def start_bot(self):
        """Start the Discord bot process"""
        if self.bot_process and self.bot_process.poll() is None:
            messagebox.showinfo("Bot Status", "Bot is already running!")
            return
            
        try:
            # Find main.py in the same directory
            bot_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
            
            # Check if it exists, fallback to bot.py
            if not os.path.exists(bot_script_path):
                bot_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
                
            if not os.path.exists(bot_script_path):
                messagebox.showerror("Error", "Bot script not found. Looked for main.py and bot.py in the current directory.")
                return
                
            # Start the bot process
            self.bot_process = subprocess.Popen(
                [sys.executable, bot_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # Windows-specific
            )
            
            logger.info(f"Bot process started with PID: {self.bot_process.pid} using script: {bot_script_path}")
            self.bot_status.set("Running")
            
            # Start monitoring bot output
            threading.Thread(target=self._monitor_bot_output, daemon=True).start()
            
            # Update activity log with acid green timestamp
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.activity_text.insert(tk.END, f"{timestamp} - Bot started\n")
            self.activity_text.see(tk.END)
            
            # Update status label
            self.status_label.config(text=f"Bot started with PID: {self.bot_process.pid}")
            
            # Enable auto-refresh for logs
            self.auto_refresh.set(True)
            self.toggle_auto_refresh()
            
            # Update with safety check
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Bot started with PID: {self.bot_process.pid}")
            
        except Exception as e:
            logger.error(f"Error loading paper {paper_file}: {e}")
            logger.error(f"Error loading paper {paper_file}: {e}")
            logger.error(f"Error loading paper {paper_file}: {e}")
            logger.error(f"Error starting bot: {e}")
            messagebox.showerror("Error", f"Failed to start bot: {str(e)}")
    
    def _monitor_bot_output(self):
        """Monitor the bot process output in a separate thread"""
        if not self.bot_process:
            return
            
        try:
            for line in iter(self.bot_process.stdout.readline, ''):
                if not line:
                    break
                logger.info(f"Bot output: {line.strip()}")
                
                # Update activity log on the main thread
                self.root.after(0, lambda msg=line: self.activity_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {msg}"))
                self.root.after(0, self.activity_text.see, tk.END)
                
            # Process has ended
            self.root.after(0, self._on_bot_exit)
            
        except Exception as e:
            logger.error(f"Error monitoring bot output: {e}")
    
    def _on_bot_exit(self):
        """Called when the bot process exits"""
        if self.bot_process:
            exit_code = self.bot_process.poll()
            logger.info(f"Bot process exited with code: {exit_code}")
            self.bot_status.set("Stopped")
            
            # Update activity log
            self.activity_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - Bot stopped (exit code: {exit_code})\n")
            self.activity_text.see(tk.END)
            
            # Clean up
            self.bot_process = None
    
    def stop_bot(self):
        """Stop the Discord bot process"""
        if not self.bot_process or self.bot_process.poll() is not None:
            messagebox.showinfo("Bot Status", "Bot is not running!")
            return
            
        try:
            # Send CTRL+C signal on Windows
            if sys.platform == 'win32':
                os.kill(self.bot_process.pid, signal.CTRL_C_EVENT)
            else:
                self.bot_process.terminate()
                
            # Wait for process to terminate with timeout
            try:
                self.bot_process.wait(timeout=5)
                logger.info("Bot process terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Bot process did not terminate within timeout, forcing...")
                self.bot_process.kill()
                
            self.bot_status.set("Stopped")
            self.status_label.config(text="Bot stopped successfully")
            
        except subprocess.TimeoutExpired:
            # Force kill if it doesn't terminate
            self.bot_process.kill()
            self.bot_process = None
            self.bot_status.set("Stopped (forced)")
            self.status_label.config(text="Bot forcefully terminated")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop bot: {str(e)}")
        
        # Update with safety check
        if hasattr(self, 'status_label'):
            self.status_label.config(text="Bot stopped successfully")
    
    def restart_bot(self):
        """Restart the Discord bot"""
        self.stop_bot()
        # Wait a moment before starting again
        self.root.after(1000, self.start_bot)
    
    def monitor_bot_process(self):
        """Monitor the bot process for output and status"""
        if not self.bot_process:
            return
            
        # Read output from the process
        for line in iter(self.bot_process.stdout.readline, ''):
            if line:
                logger.info(f"Bot output: {line.strip()}")
                
        # Check if process has terminated
        if self.bot_process and self.bot_process.poll() is not None:
            # Process has ended
            self.bot_process = None
            self.root.after(0, lambda: self.bot_status.set("Stopped"))
            self.root.after(0, lambda: self.status_label.config(text="Bot has stopped"))
    
    # Other methods
    def backup_data(self):
        """Backup all data to a zip file"""
        try:
            backup_dir = filedialog.askdirectory(title="Select Backup Directory")
            if not backup_dir:
                return
                
            # Create timestamp for backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"bot_data_backup_{timestamp}.zip")
            
            import shutil
            
            # Create zip file
            shutil.make_archive(
                os.path.splitext(backup_file)[0],  # Remove .zip extension
                'zip',
                DATA_DIR
            )
            
            messagebox.showinfo("Backup Complete", f"Data backed up to {backup_file}")
            
        except Exception as e:
            messagebox.showerror("Backup Error", f"Failed to backup data: {str(e)}")
    
    def edit_system_prompt(self):
        """Open a dialog to edit the system prompt"""
        def save_prompt():
            new_prompt = prompt_text.get("1.0", tk.END).strip()
            try:
                # Read the config.py file
                with open("config.py", 'r') as f:
                    config_content = f.read()
                
                # Find the SYSTEM_PROMPT section
                import re
                pattern = r'SYSTEM_PROMPT\s*=\s*""".*?"""'
                new_config = re.sub(pattern, f'SYSTEM_PROMPT = """\n{new_prompt}\n"""', config_content, flags=re.DOTALL)
                
                # Write back the updated config
                with open("config.py", 'w') as f:
                    f.write(new_config)
                    
                messagebox.showinfo("Success", "System prompt updated.\nRestart the bot for changes to take effect.")
                prompt_dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update system prompt: {str(e)}")
        
        # Create dialog
        prompt_dialog = tk.Toplevel(self.root)
        prompt_dialog.title("Edit System Prompt")
        prompt_dialog.geometry("600x400")
        prompt_dialog.minsize(500, 300)
        
        # Create text area with the current prompt
        prompt_frame = ttk.Frame(prompt_dialog, padding=10)
        prompt_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(prompt_frame, text="Edit System Prompt:").pack(anchor=tk.W)
        
        prompt_text = scrolledtext.ScrolledText(prompt_frame, wrap=tk.WORD)
        prompt_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Load current prompt
        prompt_text.insert(tk.END, SYSTEM_PROMPT.strip())
        
        # Buttons
        btn_frame = ttk.Frame(prompt_dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        save_btn = ttk.Button(btn_frame, text="Save Changes", command=save_prompt)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=prompt_dialog.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)
    
    def edit_config(self):
        """Open a dialog to edit bot configuration"""
        def save_config():
            try:
                new_config = {
                    "MODEL_NAME": model_var.get(),
                    "TEMPERATURE": float(temp_var.get()),
                    "TIMEOUT": float(timeout_var.get()),
                    "DATA_DIR": data_dir_var.get(),
                    "CHANGE_NICKNAME": nickname_var.get()
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
                    
                messagebox.showinfo("Success", "Configuration updated.\nRestart the bot for changes to take effect.")
                config_dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update configuration: {str(e)}")
        
        # Create dialog
        config_dialog = tk.Toplevel(self.root)
        config_dialog.title("Bot Configuration")
        config_dialog.geometry("500x300")
        config_dialog.minsize(400, 250)
        
        # Create config form
        config_frame = ttk.Frame(config_dialog, padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True)
        
        # Model selection
        ttk.Label(config_frame, text="Ollama Model:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        model_var = tk.StringVar(value=MODEL_NAME)
        model_combo = ttk.Combobox(config_frame, textvariable=model_var, 
                                   values=["llama3", "tinyllama", "phi", "gemma", "mistral"])
        model_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Temperature
        ttk.Label(config_frame, text="Temperature:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        temp_var = tk.StringVar(value=str(TEMPERATURE))
        temp_entry = ttk.Entry(config_frame, textvariable=temp_var)
        temp_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Timeout
        ttk.Label(config_frame, text="Timeout (seconds):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        timeout_var = tk.StringVar(value=str(TIMEOUT))
        timeout_entry = ttk.Entry(config_frame, textvariable=timeout_var)
        timeout_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Data directory
        ttk.Label(config_frame, text="Data Directory:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        data_dir_var = tk.StringVar(value=DATA_DIR)
        data_dir_entry = ttk.Entry(config_frame, textvariable=data_dir_var)
        data_dir_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Change nickname option
        ttk.Label(config_frame, text="Change Bot Nickname:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        nickname_var = tk.BooleanVar(value=CHANGE_NICKNAME)
        nickname_check = ttk.Checkbutton(config_frame, variable=nickname_var)
        nickname_check.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(config_dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        save_btn = ttk.Button(btn_frame, text="Save Changes", command=save_config)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=config_dialog.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)
    
    def view_user_profile(self, event):
        """View details for a selected user"""
        # Get the selected item
        selection = self.users_tree.selection()
        if not selection:
            return
            
        # Get user ID
        item = self.users_tree.item(selection[0])
        user_id = item['values'][0]
        
        # Find all profile files for this user
        profiles_dir = Path(f"{DATA_DIR}/user_profiles")
        profile_files = list(profiles_dir.glob(f"*_{user_id}_profile.json"))
        
        if not profile_files:
            messagebox.showinfo("Profile", "No profile found for this user")
            return
            
        # Load the profile
        with open(profile_files[0], 'r', encoding='utf-8') as f:
            profile_data = json.load(f)
        
        # Create profile dialog
        profile_dialog = tk.Toplevel(self.root)
        profile_dialog.title(f"User Profile: {profile_data.get('username', 'Unknown')}")
        profile_dialog.geometry("600x400")
        profile_dialog.minsize(500, 300)
        
        # Create scrollable text area with the profile data
        profile_frame = ttk.Frame(profile_dialog, padding=10)
        profile_frame.pack(fill=tk.BOTH, expand=True)
        
        profile_text = scrolledtext.ScrolledText(profile_frame, wrap=tk.WORD)
        profile_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Format profile data
        formatted_profile = f"# User Profile: {profile_data.get('username', 'Unknown')}\n\n"
        formatted_profile += f"**User ID:** {user_id}\n"
        formatted_profile += f"**Last Active:** {profile_data.get('timestamp', 'Unknown')}\n\n"
        formatted_profile += "## Learning Analysis\n\n"
        formatted_profile += profile_data.get('analysis', 'No analysis available')
        
        profile_text.insert(tk.END, formatted_profile)
        
        # Close button
        ttk.Button(profile_dialog, text="Close", command=profile_dialog.destroy).pack(pady=10)
    
    def view_conversation_details(self, event):
        """View details for a selected conversation"""
        # Placeholder function - would need actual conversation data
        messagebox.showinfo("Conversation", "Conversation details would be displayed here")
    
    def view_paper_details(self, event):
        """View details for a selected paper"""
        # Get the selected item
        selection = self.arxiv_tree.selection()
        if not selection:
            return
            
        # Get ArXiv ID
        item = self.arxiv_tree.item(selection[0])
        arxiv_id = item['values'][0]
        
        # Find the paper file
        paper_file = Path(f"{DATA_DIR}/papers/{arxiv_id}.parquet")
        
        if not paper_file.exists():
            messagebox.showinfo("Paper", "Paper details not found")
            return
            
        # Load the paper data
        df = ParquetStorage.load_from_parquet(str(paper_file))
        if df is None or df.empty:
            messagebox.showinfo("Paper", "Paper data could not be loaded")
            return
            
        paper_data = df.iloc[0].to_dict()
        
        # Create paper dialog
        paper_dialog = tk.Toplevel(self.root)
        paper_dialog.title(f"Paper: {paper_data.get('title', 'Unknown')}")
        paper_dialog.geometry("700x500")
        paper_dialog.minsize(600, 400)
        
        # Create scrollable text area with the paper data
        paper_frame = ttk.Frame(paper_dialog, padding=10)
        paper_frame.pack(fill=tk.BOTH, expand=True)
        
        paper_text = scrolledtext.ScrolledText(paper_frame, wrap=tk.WORD)
        paper_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
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
        
        paper_text.insert(tk.END, formatted_paper)
        
        # Button frame
        btn_frame = ttk.Frame(paper_dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Open links buttons
        ttk.Button(btn_frame, text="Open ArXiv Page", 
                  command=lambda: webbrowser.open(paper_data.get('arxiv_url', ''))).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Open PDF", 
                  command=lambda: webbrowser.open(paper_data.get('pdf_link', ''))).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", 
                  command=paper_dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def open_url(self, event):
        """Open the selected URL in a browser"""
        # Get the selected item
        selection = self.links_tree.selection()
        if not selection:
            return
            
        # Get URL
        item = self.links_tree.item(selection[0])
        url = item['values'][0]
        
        # Open URL in browser
        if url:
            webbrowser.open(url)
    
    def show_about(self):
        """Show about dialog"""
        about_text = """
        Ollama Teacher Bot Manager v1.0.0
        
        A management interface for the Ollama Discord Teacher bot.
        
        This tool allows you to monitor and control your Discord bot,
        view user interactions, and manage the collected data.
        
        © 2025 - Based on OllamaDiscordTeacher
        https://github.com/Leoleojames1/OllamaDiscordTeacher
        """
        
        messagebox.showinfo("About", about_text.strip())
    
    def periodic_refresh(self):
        """Periodically refresh data"""
        # Update bot status
        if self.bot_process and self.bot_process.poll() is None:
            self.bot_status.set("Running")
        else:
            self.bot_status.set("Stopped")
        
        # Schedule next refresh
        self.root.after(5000, self.periodic_refresh)
    
    def on_close(self):
        """Handle window closing"""
        if self.bot_process and self.bot_process.poll() is None:
            if messagebox.askyesno("Exit", "Bot is still running. Stop the bot and exit?"):
                self.stop_bot()
                self.root.destroy()
        else:
            self.root.destroy()

    def ensure_data_directories(self):
        """Ensure all required data directories exist"""
        # Create main data directory if it doesn't exist
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        Path(f"{DATA_DIR}/searches").mkdir(parents=True, exist_ok=True)
        Path(f"{DATA_DIR}/papers").mkdir(parents=True, exist_ok=True)
        Path(f"{DATA_DIR}/crawls").mkdir(parents=True, exist_ok=True)
        Path(f"{DATA_DIR}/links").mkdir(parents=True, exist_ok=True)
        Path(f"{DATA_DIR}/user_profiles").mkdir(parents=True, exist_ok=True)
        
        # Log directory creation
        logger.info(f"Data directories initialized at {DATA_DIR}")

    def toggle_auto_refresh(self):
        """Toggle automatic log refresh"""
        if self.log_update_job:
            # Cancel existing job if it exists
            self.root.after_cancel(self.log_update_job)
            self.log_update_job = None
        else:
            # Create new refresh job
            self.update_logs()

    def create_status_bar(self):
        """Create status bar at bottom of window"""
        self.status_bar = ttk.Frame(self.root)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Add status label with glow effect
        self.status_label = ttk.Label(self.status_bar, text="Ready", padding=(10, 5))
        self.status_label.pack(side=tk.LEFT)
        
        # Add separator with neon glow
        separator = ttk.Separator(self.status_bar, orient='horizontal')
        separator.pack(side=tk.TOP, fill=tk.X, pady=1)
        
        # Version info
        version_label = ttk.Label(self.status_bar, text="v1.0.0", padding=(10, 5))
        version_label.pack(side=tk.RIGHT)

    def load_data(self):
        """Load data from storage"""
        try:
            # Count users from profiles
            user_profiles_dir = Path(f"{DATA_DIR}/user_profiles")
            if user_profiles_dir.exists():
                profiles = list(user_profiles_dir.glob("*_profile.json"))
                self.user_count.set(len(profiles))
            
            # Count conversations
            conversations_count = 0
            if hasattr(self, 'conversations_tree') and Path(f"{DATA_DIR}/guilds").exists():
                # Implement conversation counting logic here
                self.total_conversations.set(conversations_count)
            
            # Update activity log
            self.activity_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - Data refreshed\n")
            self.activity_text.see(tk.END)
            
            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.config(text="Data loaded successfully")
                
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Error: {str(e)}")

    def clear_logs(self):
        """Clear the log display and optionally log files"""
        # Clear activity text
        self.activity_text.delete(1.0, tk.END)
        
        # Clear log tab if it exists
        if hasattr(self, 'log_text'):
            self.log_text.delete(1.0, tk.END)
        
        # Ask about clearing log file
        if messagebox.askyesno("Clear Logs", "Do you want to clear the log file as well?"):
            try:
                with open("bot_manager.log", 'w') as f:
                    f.write("")
                messagebox.showinfo("Success", "Log file cleared")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear log file: {str(e)}")

    def setup_users_tab(self):
        """Set up the users tab with user list and details"""
        # Create users tree
        columns = ('id', 'name', 'guild', 'last_active')
        self.users_tree = ttk.Treeview(self.users_tab, columns=columns, show='headings')
        
        # Configure columns
        self.users_tree.heading('id', text='User ID')
        self.users_tree.heading('name', text='Name')
        self.users_tree.heading('guild', text='Guild')
        self.users_tree.heading('last_active', text='Last Active')
        
        # Column widths
        self.users_tree.column('id', width=100)
        self.users_tree.column('name', width=150)
        self.users_tree.column('guild', width=150)
        self.users_tree.column('last_active', width=150)
        
        # Add scrollbars
        users_scroll_y = ttk.Scrollbar(self.users_tab, orient=tk.VERTICAL, command=self.users_tree.yview)
        self.users_tree.configure(yscrollcommand=users_scroll_y.set)
        
        # Pack widgets
        users_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.users_tree.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        # Bind events
        self.users_tree.bind('<Double-1>', self.view_user_profile)

    def setup_logs_tab(self):
        """Set up the logs tab with log viewer"""
        # Create log text area
        self.log_text = scrolledtext.ScrolledText(self.logs_tab, wrap=tk.WORD, bg=AcidTheme.BG_MEDIUM,
                                                fg=AcidTheme.TEXT_PRIMARY, insertbackground=AcidTheme.ACCENT_PRIMARY,
                                                borderwidth=0, highlightthickness=1, highlightcolor=AcidTheme.ACCENT_PRIMARY)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Control buttons
        btn_frame = ttk.Frame(self.logs_tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        refresh_btn = ttk.Button(btn_frame, text="Refresh Logs", command=self.update_logs)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        clear_btn = ttk.Button(btn_frame, text="Clear Logs", command=self.clear_logs)
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Auto refresh toggle
        self.auto_refresh = tk.BooleanVar(value=False)
        auto_cb = ttk.Checkbutton(btn_frame, text="Auto Refresh", variable=self.auto_refresh, 
                                 command=self.toggle_auto_refresh)
        auto_cb.pack(side=tk.LEFT, padx=20)

    def setup_conversations_tab(self):
        """Set up the conversations tab with conversation list"""
        columns = ('id', 'user', 'timestamp', 'messages')
        self.conversations_tree = ttk.Treeview(self.conversations_tab, columns=columns, show='headings')
        
        # Configure columns
        self.conversations_tree.heading('id', text='ID')
        self.conversations_tree.heading('user', text='User')
        self.conversations_tree.heading('timestamp', text='Timestamp')
        self.conversations_tree.heading('messages', text='Messages')
        
        # Column widths
        self.conversations_tree.column('id', width=50)
        self.conversations_tree.column('user', width=150)
        self.conversations_tree.column('timestamp', width=150)
        self.conversations_tree.column('messages', width=300)
        
        # Add scrollbars
        conv_scroll_y = ttk.Scrollbar(self.conversations_tab, orient=tk.VERTICAL, command=self.conversations_tree.yview)
        self.conversations_tree.configure(yscrollcommand=conv_scroll_y.set)
        
        # Pack widgets
        conv_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.conversations_tree.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        # Bind events
        self.conversations_tree.bind('<Double-1>', self.view_conversation_details)

    def update_logs(self):
        """Update the log display with contents of the log file"""
        if hasattr(self, 'log_text'):
            try:
                with open("bot_manager.log", 'r') as f:
                    log_content = f.read()
                
                # Clear and update content
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, log_content)
                self.log_text.see(tk.END)
                
                # Schedule next update if auto-refresh is on
                if self.auto_refresh.get():
                    self.log_update_job = self.root.after(5000, self.update_logs)
                    
            except Exception as e:
                self.log_text.insert(tk.END, f"Error reading log file: {str(e)}\n")
                logger.error(f"Error reading log file: {e}")

    def setup_arxiv_tab(self):
        """Set up the ArXiv papers tab with paper list"""
        columns = ('id', 'title', 'authors', 'date', 'categories')
        self.arxiv_tree = ttk.Treeview(self.arxiv_tab, columns=columns, show='headings')
        
        # Configure columns
        self.arxiv_tree.heading('id', text='ArXiv ID')
        self.arxiv_tree.heading('title', text='Title')
        self.arxiv_tree.heading('authors', text='Authors')
        self.arxiv_tree.heading('date', text='Published')
        self.arxiv_tree.heading('categories', text='Categories')
        
        # Column widths
        self.arxiv_tree.column('id', width=100)
        self.arxiv_tree.column('title', width=300)
        self.arxiv_tree.column('authors', width=200)
        self.arxiv_tree.column('date', width=100)
        self.arxiv_tree.column('categories', width=150)
        
        # Add scrollbars with neon styling
        arxiv_scroll_y = ttk.Scrollbar(self.arxiv_tab, orient=tk.VERTICAL, command=self.arxiv_tree.yview)
        self.arxiv_tree.configure(yscrollcommand=arxiv_scroll_y.set)
        
        # Pack widgets
        arxiv_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.arxiv_tree.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        # Add control frame with neon glow
        control_frame = ttk.Frame(self.arxiv_tab, style='Glow.TFrame')
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Add refresh button with acid glow
        refresh_btn = ttk.Button(control_frame, text="Refresh Papers", 
                               command=lambda: self.load_papers())
        refresh_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Bind events
        self.arxiv_tree.bind('<Double-1>', self.view_paper_details)
        
        # Load papers if available
        self.load_papers()

    def setup_links_tab(self):
        """Set up the links tab with collected links"""
        columns = ('url', 'title', 'source', 'date')
        self.links_tree = ttk.Treeview(self.links_tab, columns=columns, show='headings')
        
        # Configure columns
        self.links_tree.heading('url', text='URL')
        self.links_tree.heading('title', text='Title')
        self.links_tree.heading('source', text='Source')
        self.links_tree.heading('date', text='Collected')
        
        # Column widths
        self.links_tree.column('url', width=300)
        self.links_tree.column('title', width=200)
        self.links_tree.column('source', width=150)
        self.links_tree.column('date', width=100)
        
        # Add scrollbars with neon styling
        links_scroll_y = ttk.Scrollbar(self.links_tab, orient=tk.VERTICAL, command=self.links_tree.yview)
        self.links_tree.configure(yscrollcommand=links_scroll_y.set)
        
        # Pack widgets
        links_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.links_tree.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        # Add control frame with neon glow
        control_frame = ttk.Frame(self.links_tab, style='Glow.TFrame')
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Add refresh button with acid glow
        refresh_btn = ttk.Button(control_frame, text="Refresh Links", 
                               command=lambda: self.load_links())
        refresh_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Add open button
        open_btn = ttk.Button(control_frame, text="Open Selected URL", 
                             command=lambda: self.open_url(None))
        open_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Bind events
        self.links_tree.bind('<Double-1>', self.open_url)
        
        # Load links if available
        self.load_links()

    def load_papers(self):
        """Load ArXiv papers from storage"""
        try:
            papers_dir = Path(f"{DATA_DIR}/papers")
            if not papers_dir.exists():
                return
                
            # Clear existing items
            for item in self.arxiv_tree.get_children():
                self.arxiv_tree.delete(item)
            
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
                        
                        # Insert into treeview
                        self.arxiv_tree.insert('', tk.END, values=(
                            arxiv_id,
                            paper_data.get('title', 'Unknown'),
                            authors,
                            published,
                            categories
                        ))
                        papers_loaded += 1
                except Exception as e:
                    logger.error(f"Error loading paper {paper_file}: {e}")
                    
            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Loaded {papers_loaded} papers")
                    
        except Exception as e:
            logger.error(f"Error loading papers: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Error loading papers: {str(e)}")

    def load_links(self):
        """Load collected links from storage"""
        try:
            links_dir = Path(f"{DATA_DIR}/links")
            if not links_dir.exists():
                return
                
            # Find all links files
            link_files = list(links_dir.glob("*.parquet"))
            
            # Clear existing items
            for item in self.links_tree.get_children():
                self.links_tree.delete(item)
            
            # Load each link file
            total_links = 0
            for link_file in link_files:
                try:
                    df = ParquetStorage.load_from_parquet(str(link_file))
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            total_links += 1
                            # Insert into tree
                            self.links_tree.insert('', tk.END, values=(
                                row.get('url', ''),
                                row.get('title', 'Unknown'),
                                row.get('source', 'Unknown'),
                                row.get('timestamp', '')[:19]  # Format timestamp
                            ))
                except Exception as e:
                    logger.error(f"Error loading links from {link_file}: {e}")
                    
            # Update status with safety check
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Loaded {total_links} links from {len(link_files)} files")
                    
        except Exception as e:
            logger.error(f"Error loading links: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.config(text=f"Error loading links: {str(e)}")

    # Add this method for neon pulsing effect
    def pulse_status(self):
        colors = [AcidTheme.ACCENT_PRIMARY, AcidTheme.ACCENT_SECONDARY, AcidTheme.ACCENT_TERTIARY]
        current = getattr(self, '_pulse_index', 0)
        if hasattr(self, 'status_label'):
            self.status_label.configure(foreground=colors[current])
        self._pulse_index = (current + 1) % len(colors)
        self.root.after(800, self.pulse_status)  # Call again after 800ms

def main():
    root = tk.Tk()
    app = BotManagerApp(root)
    
    # Handle window close
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    
    # Start the application
    root.mainloop()

if __name__ == "__main__":
    main()
