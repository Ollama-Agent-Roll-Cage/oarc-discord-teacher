from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QUrl, QObject
from PyQt6.QtGui import QColor, QPalette, QFont, QDesktopServices, QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QMessageBox,
    QSystemTrayIcon, QMenu, QStyle
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from datetime import datetime, timezone, UTC
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import sys
import signal
import logging
import subprocess
import time
import json
import threading
import importlib.util

# Make sure project root is in path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("OllamaTeacherUI")

# Define fallback values
SYSTEM_PROMPT = """
You are Ollama Teacher a highly intelligent, friendly, and versatile learning assistant residing on Discord. 
Your primary goal is to help users learn about AI, ML, and programming concepts.
You specialize in explaining complex technical concepts in simple terms and providing code examples.
"""
DATA_DIR = os.getenv('DATA_DIR', 'data')
MODEL_NAME = os.getenv('OLLAMA_MODEL', 'llama3')
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))
TIMEOUT = float(os.getenv('TIMEOUT', '120.0'))
CHANGE_NICKNAME = True
USER_CONVERSATIONS = {}
USER_PROFILES_DIR = os.path.join(DATA_DIR, 'user_profiles')

# Import bot modules - use absolute imports with full paths to avoid conflicts
try:
    # Import from splitBot module with explicit paths
    from splitBot.utils import ParquetStorage, SYSTEM_PROMPT, send_in_chunks, get_user_key
    from splitBot.config import DATA_DIR, MODEL_NAME, TEMPERATURE, TIMEOUT, CHANGE_NICKNAME
    
    # Try to import the user conversations from main
    try:
        from splitBot.main import USER_CONVERSATIONS
    except ImportError:
        logger.warning("Could not import USER_CONVERSATIONS from splitBot.main, using empty dict")
        USER_CONVERSATIONS = {}

    # Update USER_PROFILES_DIR from config
    USER_PROFILES_DIR = os.path.join(DATA_DIR, 'user_profiles')
    logger.info(f"Successfully imported modules from splitBot")
    
except ImportError as e:
    logger.warning(f"Could not import from splitBot modules: {e}")

# Import BotManager dynamically
try:
    from splitBot.bot_manager import BotManager
    HAVE_BOT_MANAGER = True
    logger.info("Successfully imported BotManager from splitBot.bot_manager")
except ImportError:
    HAVE_BOT_MANAGER = False
    logger.warning("Could not import BotManager from splitBot.bot_manager")

# Custom WebEnginePage to handle SSL errors
class WebEnginePage(QWebEnginePage):
    def certificateError(self, error):
        # Ignore SSL errors for local content
        if error.url().isLocalFile():
            return True
        return super().certificateError(error)

# Import fallback models
try:
    from ui.fallback_models import BASE_MODELS, VISION_MODELS
except ImportError:
    # Define fallback models inline if the import fails
    BASE_MODELS = [{'name': 'llama3', 'size': 'Unknown', 'modified': 'N/A'}]
    VISION_MODELS = [{'name': 'llava', 'size': 'Unknown', 'modified': 'N/A'}]

class APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the web API"""
    
    def __init__(self, *args, bot_manager=None, **kwargs):
        self.bot_manager = bot_manager
        # Add project root path reference
        self.project_root = PROJECT_ROOT
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            if self.path == "/api/dashboard/stats":
                self.handle_dashboard_stats_request()
            elif self.path == "/api/models/base":
                self.handle_models_request("base")
            elif self.path == "/api/models/vision":
                self.handle_models_request("vision")
            elif self.path == "/api/users":
                self.handle_users_request()
            elif self.path == "/api/conversations":
                self.handle_conversations_request()
            elif self.path == "/api/papers":
                self.handle_papers_request()
            elif self.path == "/api/logs":
                self.handle_logs_request()
            elif self.path == "/api/settings":
                self.handle_settings_request()
            elif self.path == "/api/system/info":
                self.handle_system_info_request()
            else:
                self.send_error_json(404, f"Endpoint not found: {self.path}")
        except Exception as e:
            logger.error(f"Error handling GET request: {e}", exc_info=True)
            self.send_error_json(500, f"Internal server error: {str(e)}")
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        self.send_cors_headers()
        self.send_response(200)
        self.end_headers()
    
    def do_POST(self):
        """Handle POST requests"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = json.loads(self.rfile.read(content_length).decode('utf-8')) if content_length > 0 else {}
            
            if self.path == "/api/bot/start":
                self.handle_bot_start_request(post_data)
            elif self.path == "/api/bot/stop":
                self.handle_bot_stop_request(post_data)
            elif self.path == "/api/config":
                self.handle_config_request(post_data)
            elif self.path == "/api/settings":
                self.handle_settings_save_request(post_data)
            else:
                self.send_error_json(404, f"Endpoint not found: {self.path}")
        except Exception as e:
            logger.error(f"Error handling POST request: {e}", exc_info=True)
            self.send_error_json(500, f"Internal server error: {str(e)}")
    
    def do_DELETE(self):
        """Handle DELETE requests"""
        try:
            if self.path == "/api/logs":
                self.handle_logs_clear_request()
            else:
                self.send_error_json(404, f"Endpoint not found: {self.path}")
        except Exception as e:
            logger.error(f"Error handling DELETE request: {e}", exc_info=True)
            self.send_error_json(500, f"Internal server error: {str(e)}")
    
    def send_cors_headers(self):
        """Send CORS headers for cross-origin requests"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def send_json_response(self, data):
        """Send a JSON response with proper headers"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.write_json_response(data)
    
    def send_error_json(self, code, message):
        """Send an error response as JSON"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.write_json_response({"error": message})
    
    def write_json_response(self, data):
        """Write JSON data to response"""
        response = json.dumps(data).encode('utf-8')
        self.wfile.write(response)
    
    def handle_dashboard_stats_request(self):
        """Handle GET request for dashboard statistics"""
        try:
            bot_status = "UNKNOWN"
            
            # Check if bot manager is available to determine bot status
            if self.bot_manager:
                # Check if the _is_process_running method exists and is callable
                if hasattr(self.bot_manager, '_is_process_running'):
                    try:
                        running = self.bot_manager._is_process_running()
                        bot_status = "RUNNING" if running else "STOPPED"
                        logger.info(f"Bot status: {bot_status}")
                    except Exception as e:
                        logger.error(f"Error checking bot status: {e}")
                        bot_status = "ERROR"
            
            # Get user statistics
            user_count = len(USER_CONVERSATIONS) if USER_CONVERSATIONS else 0
            
            # Get conversation statistics
            conversation_count = sum(len(convs) for convs in USER_CONVERSATIONS.values()) if USER_CONVERSATIONS else 0
            
            # Get paper count
            papers_dir = os.path.join(DATA_DIR, "papers")
            if os.path.exists(papers_dir):
                paper_count = len([f for f in os.listdir(papers_dir) if f.endswith('.parquet')])
            else:
                paper_count = 0
                
            stats = {
                "botStatus": bot_status,
                "users": user_count,
                "conversations": conversation_count,
                "papers": paper_count
            }
            
            logger.info("Sent dashboard stats with real data")
            self.send_json_response(stats)
            
        except Exception as e:
            logger.error(f"Error handling dashboard stats request: {e}")
            # Send default values on error
            self.send_json_response({
                "botStatus": "UNKNOWN",
                "users": 0,
                "conversations": 0,
                "papers": 0
            })
    
    def handle_bot_start_request(self, post_data):
        """Handle POST request to start the bot"""
        try:
            if not self.bot_manager:
                self.send_error_json(500, "Bot manager not available")
                return
            
            # Check if the bot is already running
            if hasattr(self.bot_manager, '_is_process_running') and self.bot_manager._is_process_running():
                logger.info("Bot is already running, returning success")
                self.send_json_response({"success": True, "message": "Bot is already running"})
                return
            
            # Try to start the bot with proper error handling
            logger.info("Using BotManager to start bot")
            result = self.bot_manager.start_bot()
            
            if result:
                self.send_json_response({"success": True, "message": "Bot started successfully"})
            else:
                self.send_error_json(500, "Failed to start bot - bot manager returned False")
                
        except Exception as e:
            logger.error(f"Error starting bot: {e}", exc_info=True)
            self.send_error_json(500, f"Error starting bot: {str(e)}")
    
    def handle_bot_stop_request(self, post_data):
        """Handle POST request to stop the bot"""
        try:
            if not self.bot_manager:
                self.send_error_json(500, "Bot manager not available")
                return
            
            # Check if the bot is running
            is_running = False
            if hasattr(self.bot_manager, '_is_process_running'):
                is_running = self.bot_manager._is_process_running()
            
            if not is_running:
                logger.info("Bot is not running, returning success")
                self.send_json_response({"success": True, "message": "Bot is not running"})
                return
                
            # Try to stop the bot with proper error handling
            logger.info("Using BotManager to stop bot")
            result = self.bot_manager.stop_bot()
            
            if result:
                self.send_json_response({"success": True, "message": "Bot stopped successfully"})
            else:
                self.send_error_json(500, "Failed to stop bot - bot manager returned False")
                
        except Exception as e:
            logger.error(f"Error stopping bot: {e}", exc_info=True)
            self.send_error_json(500, f"Error stopping bot: {str(e)}")
    
    def handle_models_request(self, model_type):
        """Handle GET request for models"""
        try:
            if model_type == "base":
                # Try to detect models dynamically if available
                try:
                    from ui.fallback_models import detect_vision_models
                    base_models, _ = detect_vision_models(refresh=True)
                    logger.info(f"Sending {len(base_models)} base models")
                    self.send_json_response(base_models)
                except Exception as e:
                    logger.error(f"Error detecting base models: {e}")
                    # Fall back to hardcoded list
                    self.send_json_response(BASE_MODELS)
            elif model_type == "vision":
                try:
                    from ui.fallback_models import detect_vision_models
                    _, vision_models = detect_vision_models(refresh=True)
                    logger.info(f"Sending {len(vision_models)} vision models")
                    self.send_json_response(vision_models)
                except Exception as e:
                    logger.error(f"Error detecting vision models: {e}")
                    # Fall back to hardcoded list
                    self.send_json_response(VISION_MODELS)
            else:
                self.send_error_json(400, f"Invalid model type: {model_type}")
        except Exception as e:
            logger.error(f"Error handling {model_type} models request: {e}")
            self.send_error_json(500, f"Error retrieving models: {str(e)}")
    
    def handle_dashboard_stats_request(self):
        """Handle GET request for dashboard statistics"""
        try:
            bot_status = "UNKNOWN"
            
            # Check if bot manager is available to determine bot status
            if self.bot_manager:
                # Check if the _is_process_running method exists and is callable
                if hasattr(self.bot_manager, '_is_process_running'):
                    try:
                        running = self.bot_manager._is_process_running()
                        bot_status = "RUNNING" if running else "STOPPED"
                        logger.info(f"Bot status: {bot_status}")
                    except Exception as e:
                        logger.error(f"Error checking bot status: {e}")
                        bot_status = "ERROR"
            
            # Get user statistics
            user_count = len(USER_CONVERSATIONS) if USER_CONVERSATIONS else 0
            
            # Get conversation statistics
            conversation_count = sum(len(convs) for convs in USER_CONVERSATIONS.values()) if USER_CONVERSATIONS else 0
            
            # Get paper count
            papers_dir = os.path.join(DATA_DIR, "papers")
            if os.path.exists(papers_dir):
                paper_count = len([f for f in os.listdir(papers_dir) if f.endswith('.parquet')])
            else:
                paper_count = 0
                
            stats = {
                "botStatus": bot_status,
                "users": user_count,
                "conversations": conversation_count,
                "papers": paper_count
            }
            
            logger.info("Sent dashboard stats with real data")
            self.send_json_response(stats)
            
        except Exception as e:
            logger.error(f"Error handling dashboard stats request: {e}")
            # Send default values on error
            self.send_json_response({
                "botStatus": "UNKNOWN",
                "users": 0,
                "conversations": 0,
                "papers": 0
            })
    
    def handle_users_request(self):
        """Handle GET request for users"""
        try:
            users = []
            if os.path.exists(USER_PROFILES_DIR):
                for filename in os.listdir(USER_PROFILES_DIR):
                    if filename.endswith('_profile.json'):
                        try:
                            with open(os.path.join(USER_PROFILES_DIR, filename), 'r', encoding='utf-8') as f:
                                profile = json.load(f)
                                user_id = filename.replace('_profile.json', '')
                                users.append({
                                    'id': user_id,
                                    'name': profile.get('username', 'Unknown'),
                                    'timestamp': profile.get('timestamp', 'Unknown'),
                                    'messageCount': len(USER_CONVERSATIONS.get(user_id, [])) - 1 if user_id in USER_CONVERSATIONS else 0
                                })
                        except Exception as e:
                            logger.error(f"Error reading profile {filename}: {e}")
            
            self.send_json_response(users)
        except Exception as e:
            logger.error(f"Error handling users request: {e}")
            self.send_json_response([])
    
    def handle_conversations_request(self):
        """Handle GET request for conversations"""
        try:
            conversations = []
            # Loop through user conversations
            for user_id, messages in USER_CONVERSATIONS.items():
                if len(messages) > 1:  # Skip users with just the system message
                    user_conversations = []
                    for msg in messages:
                        if msg.get('role') != 'system':
                            user_conversations.append({
                                'role': msg.get('role', 'unknown'),
                                'content': msg.get('content', '')[:100] + ('...' if len(msg.get('content', '')) > 100 else ''),
                                'timestamp': msg.get('timestamp', 'Unknown')
                            })
                    
                    conversations.append({
                        'userId': user_id,
                        'messages': user_conversations,
                        'count': len(user_conversations)
                    })
            
            self.send_json_response(conversations)
        except Exception as e:
            logger.error(f"Error handling conversations request: {e}")
            self.send_json_response([])
    
    def handle_papers_request(self):
        """Handle GET request for papers"""
        try:
            papers = []
            papers_dir = os.path.join(DATA_DIR, "papers")
            if os.path.exists(papers_dir):
                for filename in os.listdir(papers_dir):
                    if filename.endswith('.parquet') and filename != 'all_papers.parquet':
                        try:
                            # Use ParquetStorage to load paper data
                            from splitBot.utils import ParquetStorage
                            file_path = os.path.join(papers_dir, filename)
                            paper_df = ParquetStorage.load_from_parquet(file_path)
                            if paper_df is not None and len(paper_df) > 0:
                                paper_data = paper_df.iloc[0].to_dict()
                                papers.append({
                                    'arxiv_id': paper_data.get('arxiv_id', 'Unknown'),
                                    'title': paper_data.get('title', 'Unknown'),
                                    'authors': paper_data.get('authors', [])[:2],  # First 2 authors only
                                    'published': paper_data.get('published', 'Unknown')[:10],
                                    'categories': paper_data.get('categories', [])[:3]  # First 3 categories only
                                })
                        except Exception as e:
                            logger.error(f"Error reading paper {filename}: {e}")
            
            self.send_json_response(papers)
        except Exception as e:
            logger.error(f"Error handling papers request: {e}")
            self.send_json_response([])
    
    def handle_logs_request(self):
        """Handle GET request for logs"""
        try:
            log_file = "bot_manager.log"
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    # Read last 100 lines
                    lines = f.readlines()[-100:]
                    
                logs = []
                for line in lines:
                    try:
                        # Parse log line
                        parts = line.split(' - ', 3)
                        if len(parts) >= 4:
                            timestamp, name, level, message = parts
                            logs.append({
                                'timestamp': timestamp,
                                'name': name,
                                'level': level.lower(),
                                'message': message.strip()
                            })
                    except Exception:
                        # If parsing fails, add raw line
                        logs.append({
                            'timestamp': '',
                            'name': 'parser',
                            'level': 'error',
                            'message': line.strip()
                        })
                
                self.send_json_response(logs)
            else:
                self.send_json_response([])
        except Exception as e:
            logger.error(f"Error handling logs request: {e}")
            self.send_json_response([])
    
    def handle_system_info_request(self):
        """Handle GET request for system info"""
        try:
            import platform
            import psutil
            
            # Get system info
            python_version = platform.python_version()
            os_platform = platform.platform()
            architecture = platform.architecture()[0]
            
            # Get memory usage
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_usage = f"{memory_info.rss / (1024 * 1024):.2f} MB"
            
            # Get CPU usage
            cpu_usage = f"{psutil.cpu_percent()}%"
            
            # Get directory info
            directories = {
                'papers': os.path.join(DATA_DIR, 'papers'),
                'users': USER_PROFILES_DIR,
                'conversations': os.path.join(DATA_DIR, 'conversations'),
                'logs': os.path.abspath('.')
            }
            
            system_info = {
                'pythonVersion': python_version,
                'platform': os_platform,
                'architecture': architecture,
                'memoryUsage': memory_usage,
                'cpuUsage': cpu_usage,
                'dataDir': DATA_DIR,
                'directories': directories
            }
            
            self.send_json_response(system_info)
        except Exception as e:
            logger.error(f"Error handling system info request: {e}")
            self.send_json_response({
                'pythonVersion': platform.python_version(),
                'error': str(e)
            })
    
    def update_env_file(self, updates):
        """Update the .env file with new values"""
        env_file = os.path.join(self.project_root, '.env')
        
        # Read existing file
        env_lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        
        # Process updates
        updated_keys = set()
        for i, line in enumerate(env_lines):
            if '=' in line:
                key = line.split('=')[0].strip()
                if key in updates:
                    env_lines[i] = f"{key}={updates[key]}\n"
                    updated_keys.add(key)
        
        # Add new keys
        for key, value in updates.items():
            if key not in updated_keys:
                env_lines.append(f"{key}={value}\n")
        
        # Write back to file
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)
            
        return True

    def handle_config_request(self, post_data):
        """Handle POST request to update configuration"""
        try:
            # Validate input
            for key in ['temperature', 'timeout']:
                if key in post_data:
                    try:
                        post_data[key] = float(post_data[key])
                    except ValueError:
                        self.send_error_json(400, f"Invalid value for {key}: must be a number")
                        return
            
            # Update environment variables
            updates = {}
            if 'baseModel' in post_data:
                updates['OLLAMA_MODEL'] = post_data['baseModel']
            if 'visionModel' in post_data:
                updates['OLLAMA_VISION_MODEL'] = post_data['visionModel']
            if 'temperature' in post_data:
                updates['TEMPERATURE'] = str(post_data['temperature'])
            if 'timeout' in post_data:
                updates['TIMEOUT'] = str(post_data['timeout'])
            if 'dataDir' in post_data:
                updates['DATA_DIR'] = post_data['dataDir']
                
            # Update the .env file
            if updates:
                self.update_env_file(updates)
                
                # Update module variables
                try:
                    from importlib import reload
                    import splitBot.config
                    reload(splitBot.config)
                    logger.info("Successfully reloaded config module with new values")
                except ImportError:
                    logger.warning("Could not reload config module - changes will apply on next restart")
                
            self.send_json_response({"success": True, "message": "Configuration updated successfully"})
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            self.send_error_json(500, f"Error updating configuration: {str(e)}")

    def handle_settings_request(self):
        """Handle GET request for settings"""
        try:
            # Get settings from environment variables with safe defaults
            settings = {
                "systemPrompt": os.getenv("SYSTEM_PROMPT", 
                    "You are Ollama Teacher a highly intelligent, friendly, and versatile learning assistant residing on Discord."),
                "discordToken": os.getenv("DISCORD_TOKEN", ""),
                "groqApiKey": os.getenv("GROQ_API_KEY", ""),
                "temperature": float(os.getenv("TEMPERATURE", "0.7")),
                "timeout": float(os.getenv("TIMEOUT", "120.0")),
                "dataDir": os.getenv("DATA_DIR", "data"),
                "changeNickname": os.getenv("CHANGE_NICKNAME", "True").lower() in ("true", "1", "yes", "t")
            }
            
            logger.info("Sending settings with data")
            self.send_json_response(settings)
            
        except Exception as e:
            logger.error(f"Error handling settings request: {e}")
            # Send default values on error
            default_settings = {
                "systemPrompt": "You are Ollama Teacher a highly intelligent, friendly, and versatile learning assistant residing on Discord.",
                "discordToken": "",
                "groqApiKey": "",
                "temperature": 0.7,
                "timeout": 120.0,
                "dataDir": "data",
                "changeNickname": True
            }
            self.send_json_response(default_settings)
    
    def handle_settings_save_request(self, post_data):
        """Handle POST request to save settings"""
        try:
            # Validate input
            updates = {}
            if 'systemPrompt' in post_data:
                updates['SYSTEM_PROMPT'] = post_data['systemPrompt']
            if 'discordToken' in post_data:
                updates['DISCORD_TOKEN'] = post_data['discordToken']
            if 'groqApiKey' in post_data:
                updates['GROQ_API_KEY'] = post_data['groqApiKey']
                
            # Update the .env file
            if updates:
                self.update_env_file(updates)
            
            self.send_json_response({"success": True, "message": "Settings saved successfully"})
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            self.send_error_json(500, f"Error saving settings: {str(e)}")
    
    def handle_logs_clear_request(self):
        """Handle DELETE request to clear logs"""
        try:
            log_file = "bot_manager.log"
            with open(log_file, 'w') as f:
                f.write(f"Logs cleared at {datetime.now().isoformat()}\n")
                
            self.send_json_response({"success": True, "message": "Logs cleared successfully"})
        except Exception as e:
            logger.error(f"Error clearing logs: {e}")
            self.send_error_json(500, f"Error clearing logs: {str(e)}")
    
    def log_message(self, format, *args):
        """Override default log message to avoid console spam"""
        pass

class HTTPServerThread(QThread):
    """Thread to run the HTTP server"""
    
    def __init__(self, port=8080, bot_manager=None):
        super().__init__()
        self.port = port
        self.bot_manager = bot_manager
        self.server = None
        self.keep_running = True
    
    def run(self):
        """Run the HTTP server in a separate thread"""
        try:
            # Create a custom handler factory that includes the bot_manager reference
            def handler_factory(*args, **kwargs):
                return APIHandler(*args, bot_manager=self.bot_manager, **kwargs)
            
            # Create and run the server
            self.server = HTTPServer(('127.0.0.1', self.port), handler_factory)
            logger.info(f"HTTP server started on port {self.port}")
            
            # Handle requests until stopped
            while self.keep_running:
                self.server.handle_request()
                
        except Exception as e:
            logger.error(f"HTTP server error: {e}")
    
    def stop_server(self):
        """Stop the HTTP server"""
        self.keep_running = False
        if self.server:
            self.server.server_close()
            logger.info("HTTP server stopped")


class BotProcessThread(QThread):
    """Thread to monitor bot process"""
    process_ended = pyqtSignal(int)
    output_received = pyqtSignal(str)
    
    def __init__(self, process):
        super().__init__()
        self.process = process
        self.stopped = False
    
    def run(self):
        """Monitor the bot process"""
        try:
            # Read output line by line
            for line in iter(self.process.stdout.readline, ""):
                if not line or self.stopped:
                    break
                self.output_received.emit(line.strip())
                
            # Wait for process to end
            return_code = self.process.wait()
            self.process_ended.emit(return_code)
            
        except Exception as e:
            logger.error(f"Error monitoring bot process: {e}")
            self.process_ended.emit(-1)
    
    def stop(self):
        """Stop monitoring"""
        self.stopped = True


class OllamaTeacherUI(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize variables
        self.bot_process = None
        self.bot_thread = None
        self.http_server_thread = None
        self.tray_icon = None
        self.web_view = None
        self.server_port = 8080
        
        # Create BotManager instance if available
        self.bot_manager = None
        if HAVE_BOT_MANAGER:
            try:
                self.bot_manager = BotManager()
                logger.info("Created BotManager instance")
            except Exception as e:
                logger.error(f"Error creating BotManager: {e}")
        
        # Set up UI
        self.setup_ui()
        
        # Set up HTTP server
        self.start_http_server()
        
        # Set up periodic updates
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.periodic_update)
        self.update_timer.start(10000)  # Update every 10 seconds
    
    def setup_ui(self):
        """Set up the main UI window"""
        # Configure window
        self.setWindowTitle("Ollama Teacher Bot Manager")
        self.setMinimumSize(1200, 800)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create web view
        self.web_view = QWebEngineView(self)
        
        # Configure WebEngine settings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        
        # Safely try to set additional attributes
        try:
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
        except AttributeError:
            logger.warning("AllowGeolocationOnInsecureOrigins attribute not available in this version of PyQt")
            
        try:
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowUniversalAccessFromFileUrls, True)
        except AttributeError:
            logger.warning("AllowUniversalAccessFromFileUrls attribute not available in this version of PyQt")
        
        # Use custom page to handle SSL errors
        custom_page = WebEnginePage(self.web_view.page().profile(), self.web_view)
        self.web_view.setPage(custom_page)
        
        # Set up environment variables to bypass security restrictions
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --allow-file-access-from-files --ignore-certificate-errors"
        logger.info("Set WebEngine environment variables to bypass security restrictions")
        
        # Add web view to layout
        layout.addWidget(self.web_view)
        
        # Create HTML file with the UI
        html_path = self.create_html_file()
        
        # Load the HTML file
        self.web_view.load(QUrl.fromLocalFile(html_path))
        
        # Set up system tray
        self.setup_system_tray()
        
        # Set up menu bar
        self.setup_menu_bar()
    
    def create_html_file(self):
        """Create the HTML file with the UI"""
        html_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        html_path = os.path.join(html_dir, "ollama_teacher_ui.html")
        return html_path
    
    def setup_system_tray(self):
        """Set up system tray icon"""
        # Create tray icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        
        # Create tray menu
        tray_menu = QMenu()
        
        # Add actions
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        # Set menu and activate
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
    
    def setup_menu_bar(self):
        """Set up menu bar"""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        # Add actions
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        file_menu.addAction(quit_action)
        
        # Tools menu
        tools_menu = menu_bar.addMenu("Tools")
        
        # Add actions
        diagnostic_action = QAction("Run API Diagnostic", self)
        diagnostic_action.triggered.connect(self.run_api_diagnostic)
        tools_menu.addAction(diagnostic_action)
        
        refresh_action = QAction("Refresh UI", self)
        refresh_action.triggered.connect(self.refresh_ui)
        tools_menu.addAction(refresh_action)
        
        # Help menu
        help_menu = menu_bar.addMenu("Help")
        
        # Add actions
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
    
    def run_api_diagnostic(self):
        """Run API diagnostic test"""
        try:
            # Run the test script in a subprocess
            script_path = os.path.join(PROJECT_ROOT, "tools", "test_web_api.py")
            if not os.path.exists(script_path):
                QMessageBox.warning(self, "Error", "Diagnostic script not found")
                return
                
            import subprocess
            subprocess.Popen([sys.executable, script_path, str(self.server_port)])
            
            QMessageBox.information(self, "Diagnostic Started", "API diagnostic test started. Check console for results.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run diagnostic: {e}")
    
    def refresh_ui(self):
        """Refresh the web UI"""
        self.web_view.reload()
    
    def show_about_dialog(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Ollama Teacher Bot", 
                         "Ollama Teacher Bot Manager\n\n"
                         "Version: 2.0.0\n"
                         "A Discord bot for teaching using Ollama LLMs")
    
    def apply_dark_theme(self):
        """Apply dark theme to the application"""
        # Create dark palette
        dark_palette = QPalette()
        
        # Set colors
        dark_color = QColor(45, 45, 45)
        dark_palette.setColor(QPalette.ColorRole.Window, dark_color)
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, dark_color)
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, dark_color)
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        # Apply palette
        QApplication.setPalette(dark_palette)
    
    def start_http_server(self):
        """Start the HTTP server"""
        try:
            logger.info(f"Starting HTTP server on port {self.server_port}")
            self.http_server_thread = HTTPServerThread(port=self.server_port, bot_manager=self)
            self.http_server_thread.start()
            
            # Inject server port into web page
            script = f"window.serverPort = {self.server_port};"
            self.web_view.page().runJavaScript(script)
            
            logger.info(f"HTTP server started on port {self.server_port}")
        except Exception as e:
            logger.error(f"Error starting HTTP server: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start HTTP server: {e}")
    
    def start_bot(self):
        """Start the Discord bot process"""
        try:
            # Use BotManager if available
            if self.bot_manager:
                logger.info("Using BotManager to start bot")
                return self.bot_manager.start_bot()
                
            # Fall back to direct process management
            # Check if already running
            if self.bot_process and self._is_process_running():
                logger.info("Bot is already running")
                return True
                
            # Run the bot script
            bot_script = os.path.join(PROJECT_ROOT, "splitBot", "main.py")
            if not os.path.exists(bot_script):
                logger.error(f"Bot script not found at: {bot_script}")
                return False
                
            # Start the process
            self.bot_process = subprocess.Popen(
                [sys.executable, bot_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start monitoring thread
            self.bot_thread = BotProcessThread(self.bot_process)
            self.bot_thread.process_ended.connect(self.on_bot_process_ended)
            self.bot_thread.output_received.connect(self.on_bot_output)
            self.bot_thread.start()
            
            logger.info(f"Bot process started with PID: {self.bot_process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            return False

    def stop_bot(self):
        """Stop the Discord bot process"""
        try:
            # Use BotManager if available
            if self.bot_manager:
                logger.info("Using BotManager to stop bot")
                return self.bot_manager.stop_bot()
                
            # Fall back to direct process management
            if not self.bot_process:
                logger.info("No bot process to stop")
                return True
                
            if not self._is_process_running():
                logger.info("Bot process is not running")
                self.bot_process = None
                self.bot_thread = None
                return True
                
            # Stop monitoring
            if self.bot_thread:
                self.bot_thread.stop()
                
            # Terminate process
            try:
                pid = self.bot_process.pid
                self.bot_process.terminate()
                time.sleep(2)
                if self._is_process_running():
                    self.bot_process.kill()  # Force kill if still running
            except Exception as e:
                logger.error(f"Error terminating process: {e}")
                
            logger.info("Bot process stopped")
            self.bot_process = None
            return True
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
            return False
    
    def _is_process_running(self):
        """Check if the bot process is running"""
        # Use BotManager if available
        if self.bot_manager and hasattr(self.bot_manager, '_is_process_running'):
            try:
                return self.bot_manager._is_process_running()
            except Exception as e:
                logger.warning(f"Error using BotManager._is_process_running: {e}")
                # Fall through to direct process check
        
        # Direct process check
        if not self.bot_process:
            return False
            
        try:
            return self.bot_process.poll() is None
        except Exception as e:
            logger.error(f"Error checking process status: {e}")
            return False
    
    def on_bot_process_ended(self, exit_code):
        """Handle bot process ending"""
        logger.info(f"Bot process ended with exit code: {exit_code}")
        self.bot_process = None
        self.bot_thread = None
    
    def on_bot_output(self, output):
        """Handle output from bot process"""
        logger.info(f"Bot output: {output}")
    
    def periodic_update(self):
        """Periodic updates for the UI"""
        try:
            # Check bot status
            is_running = self._is_process_running()
            
            # Update UI with bot status via JavaScript
            script = f"if (window.updateBotStatus) window.updateBotStatus('{is_running}')"
            self.web_view.page().runJavaScript(script)
        except Exception as e:
            logger.error(f"Error in periodic update: {e}")
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Hide window instead of closing
        if self.tray_icon and self.tray_icon.isVisible():
            QMessageBox.information(self, "Information", "The application will keep running in the system tray.")
            self.hide()
            event.ignore()
        else:
            self.quit_application()
            event.accept()
    
    def quit_application(self):
        """Quit the application"""
        # Stop bot if running
        if self._is_process_running():
            self.stop_bot()
            
        # Stop HTTP server
        if self.http_server_thread:
            self.http_server_thread.stop_server()
            self.http_server_thread.quit()
            self.http_server_thread.wait()
            
        # Exit application
        QApplication.quit()


def main():
    """Main function"""
    # Set up application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running when window is closed
    
    # Set application properties
    app.setApplicationName("Ollama Teacher Bot")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("OllamaTeacher")
    
    # Create and show main window
    window = OllamaTeacherUI()
    window.show()

    # Handle SIGINT gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: window.quit_application())    
    
    # Start event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()