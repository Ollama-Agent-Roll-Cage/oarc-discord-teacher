"""
Bot manager module for handling the bot process lifecycle.
"""

import os
import sys
import subprocess
import logging
import signal
import time
from datetime import datetime
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BotManager")

class BotManager:
    """
    Manages the Discord bot process with start, stop, and monitoring capabilities
    """
    
    def __init__(self, script_path=None):
        """Initialize the bot manager"""
        self.bot_process = None
        self.script_path = script_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "main.py"
        )
        self.process_id = None
        
    def start_bot(self):
        """Start the Discord bot process"""
        try:
            # Check if bot is already running and return success if it is
            if self.bot_process and self._is_process_running():
                logger.info(f"Bot is already running with PID: {self.process_id}")
                return True
            
            # Check if script exists
            if not os.path.exists(self.script_path):
                logger.error(f"Bot script not found at: {self.script_path}")
                return False
            
            # Start the bot process
            self.bot_process = subprocess.Popen(
                [sys.executable, self.script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=os.environ.copy()
            )
            
            self.process_id = self.bot_process.pid
            logger.info(f"Bot process started with PID: {self.process_id} using script: {self.script_path}")
            
            # Start monitoring output
            self._monitor_output()
            
            # Wait briefly to confirm process started successfully
            time.sleep(1)
            if not self._is_process_running():
                logger.error("Bot process failed to start or terminated immediately")
                return False
                
            return True
        
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            return False
            
    def stop_bot(self):
        """Stop the Discord bot process"""
        try:
            if not self.bot_process and not self.process_id:
                logger.info("No bot process to stop")
                return True
                
            if not self._is_process_running():
                logger.info("Bot process is not running")
                self.bot_process = None
                self.process_id = None
                return True
            
            # Attempt graceful termination
            pid = self.process_id
            
            if sys.platform == "win32":
                # Windows: use taskkill to terminate process tree
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(pid)], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Unix: use SIGTERM followed by SIGKILL if needed
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(3)  # Give it time to terminate
                    if self._is_process_running():
                        os.kill(pid, signal.SIGKILL)  # Force kill if still running
                except ProcessLookupError:
                    pass  # Process already terminated
                
            self.bot_process = None
            self.process_id = None
            logger.info(f"Bot process with PID {pid} has been terminated")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
            return False
    
    def restart_bot(self):
        """Restart the Discord bot process"""
        self.stop_bot()
        time.sleep(2)  # Allow time for cleanup
        return self.start_bot()
            
    def _is_process_running(self):
        """Check if the bot process is still running"""
        if not self.process_id:
            return False
            
        try:
            # Check if process exists
            import psutil
            try:
                process = psutil.Process(self.process_id)
                return process.is_running()
            except psutil.NoSuchProcess:
                return False
        except ImportError:
            # Fallback if psutil is not available
            logger.warning("psutil module not available, using basic process check")
            if not self.bot_process:
                return False
            return self.bot_process.poll() is None
        except Exception as e:
            logger.error(f"Error checking process status: {e}")
            return False
        
    def _monitor_output(self):
        """Monitor and log the output from the bot process"""
        if not self.bot_process:
            return
            
        # Start a background thread to read output
        def output_reader():
            while self._is_process_running():
                line = self.bot_process.stdout.readline().strip()
                if line:
                    logger.info(f"Bot output: {line}")
                    
        import threading
        thread = threading.Thread(target=output_reader)
        thread.daemon = True  # Thread will exit when main program exits
        thread.start()

# Standalone usage
if __name__ == "__main__":
    manager = BotManager()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "start":
            manager.start_bot()
        elif command == "stop":
            manager.stop_bot()
        elif command == "restart":
            manager.restart_bot()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python bot_manager.py [start|stop|restart]")
    else:
        # Interactive mode
        print("Bot Manager started. Commands: start, stop, restart, exit")
        while True:
            cmd = input("Command: ").lower()
            
            if cmd == "start":
                manager.start_bot()
            elif cmd == "stop":
                manager.stop_bot()
            elif cmd == "restart":
                manager.restart_bot()
            elif cmd == "exit":
                if manager.bot_process:
                    manager.stop_bot()
                break
            else:
                print("Unknown command. Available: start, stop, restart, exit")
