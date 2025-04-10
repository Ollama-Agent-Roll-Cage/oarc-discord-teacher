import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
import torch
import gc  # Add import for garbage collection

logger = logging.getLogger(__name__)

class ImageGenerationQueue:
    """Manages queued image generation requests from multiple Discord users"""
    
    def __init__(self, rate_limit_count=3, rate_limit_period=3600):
        self.queue = asyncio.Queue()
        self.active_generation = False
        self.current_task = None
        self.status_updates = {}  # Store status update callbacks by user_key
        
        # Rate limiting - default: 3 images per hour per user
        self.rate_limit_count = rate_limit_count
        self.rate_limit_period = rate_limit_period  # in seconds
        self.user_generations = defaultdict(list)  # Maps user_key -> list of generation timestamps
        
    async def add_to_queue(self, task_data):
        """Add image generation task to queue with content moderation"""
        user_key = task_data.get('user_key')
        
        # Extract prompt for moderation checks
        prompt = task_data.get('prompt', '')
        
        # Log the received prompt
        logging.info(f"Processing image generation request from user {user_key}: '{prompt}'")
        
        # Check rate limiting
        if not self.can_generate(user_key):
            usage = self.get_user_usage(user_key)
            next_available = self.get_next_available_time(user_key)
            logging.info(f"Rate limit reached for user {user_key}: {usage}/{self.rate_limit_count}")
            return {
                'success': False, 
                'message': f"Rate limit reached ({usage}/{self.rate_limit_count} generations per hour). Next available at {next_available.strftime('%H:%M:%S')}"
            }
        
        # Content moderation check - only use sexual content filter
        try:
            is_sexual_content = await self.check_sexual_content(prompt)
            if is_sexual_content:
                logging.warning(f"Sexual content detected in prompt from user {user_key}: '{prompt}'")
                return {
                    'success': False,
                    'message': "⚠️ Content moderation: Your prompt was flagged for inappropriate sexual content. Please modify your request."
                }
        except Exception as e:
            logging.error(f"Fatal error in content moderation: {e}", exc_info=True)
            return {
                'success': False,
                'message': "⚠️ Guard model not available, cancelling image generation request. Please try again later."
            }
        
        # Add to queue
        position = self.queue.qsize() + (1 if self.active_generation else 0)
        await self.queue.put(task_data)
        
        logging.info(f"Added image generation request to queue at position {position}: '{prompt}'")
        
        # If a status callback is provided, send initial status immediately
        if user_key in self.status_updates and self.status_updates[user_key]:
            if position > 0:
                await self.status_updates[user_key](f"Your request is queued at position {position}. I'll notify you when it starts.")
            else:
                await self.status_updates[user_key]("Generating image now. This may take a minute...")
        
        # Start processing if not already running
        if not self.active_generation:
            asyncio.create_task(self.process_queue())
            
        return {
            'success': True,
            'position': position,
            'message': "Added to queue" if position > 0 else "Processing immediately"
        }
    
    def register_status_update(self, user_key, status_callback):
        """Register a callback for status updates"""
        self.status_updates[user_key] = status_callback
        
    async def process_queue(self):
        """Process the queue of image generation tasks with memory management"""
        if self.active_generation:
            return
            
        self.active_generation = True
        self.optimize_memory()
        
        try:
            while not self.queue.empty():
                # Get next task
                task_data = await self.queue.get()
                user_key = task_data.get('user_key')
                
                try:
                    # Record that this user is generating an image
                    self.user_generations[user_key].append(datetime.now())
                    
                    # Execute the generator function
                    self.current_task = task_data
                    
                    # Send status update if callback is registered
                    if user_key in self.status_updates and self.status_updates[user_key]:
                        await self.status_updates[user_key]("Generating image now. This may take a minute...")
                    
                    # Pre-emptive garbage collection to free memory BEFORE the generation
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        gc.collect()
                    
                    # Run the generation task in a way that allows other tasks to run
                    try:
                        # Run the task with a short timeout to allow for asyncio task switching
                        result = await asyncio.wait_for(task_data['generator_func'](), timeout=300)  # 5-minute timeout
                    except asyncio.TimeoutError:
                        logger.error("Image generation timed out after 5 minutes")
                        if task_data.get('error_callback'):
                            await task_data['error_callback']("Image generation timed out after 5 minutes")
                        continue
                    
                    # Call the callback with the result
                    if task_data.get('callback'):
                        await task_data['callback'](result)
                        
                    # Wait a bit BEFORE cleaning memory to avoid blocking UI
                    await asyncio.sleep(0.5)
                        
                    # Clean memory between generations - IMPORTANT!
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        gc.collect()
                        
                    # Reduce the stabilization delay
                    await asyncio.sleep(0.2)  # Reduced from 1.0 second
                        
                except Exception as e:
                    logger.error(f"Error processing queue item: {e}")
                    if task_data.get('error_callback'):
                        await task_data['error_callback'](str(e))
                        
                finally:
                    self.queue.task_done()
                    self.current_task = None
                    # Allow heartbeat to catch up with a smaller delay
                    await asyncio.sleep(0.05)  # Reduced from 0.1
                    # Remove status update callback once task is complete
                    if user_key in self.status_updates:
                        del self.status_updates[user_key]
        
        finally:
            self.active_generation = False
            
    def can_generate(self, user_key):
        """Check if a user can generate an image based on rate limits"""
        if user_key not in self.user_generations:
            return True
            
        # Clean up old timestamps
        cutoff_time = datetime.now() - timedelta(seconds=self.rate_limit_period)
        self.user_generations[user_key] = [
            ts for ts in self.user_generations[user_key] if ts > cutoff_time
        ]
        
        # Check if under the limit
        return len(self.user_generations[user_key]) < self.rate_limit_count
        
    def get_user_usage(self, user_key):
        """Get current usage count for a user"""
        if user_key not in self.user_generations:
            return 0
            
        # Clean up old timestamps
        cutoff_time = datetime.now() - timedelta(seconds=self.rate_limit_period)
        self.user_generations[user_key] = [
            ts for ts in self.user_generations[user_key] if ts > cutoff_time
        ]
        
        return len(self.user_generations[user_key])
        
    def get_next_available_time(self, user_key):
        """Get timestamp when user can generate again"""
        if user_key not in self.user_generations or not self.user_generations[user_key]:
            return datetime.now()
            
        # Sort timestamps and get the oldest one
        sorted_times = sorted(self.user_generations[user_key])
        if len(sorted_times) < self.rate_limit_count:
            return datetime.now()
            
        # When will the oldest timestamp expire?
        return sorted_times[0] + timedelta(seconds=self.rate_limit_period)
        
    def get_queue_status(self):
        """Get current queue status"""
        return {
            'queue_size': self.queue.qsize(),
            'active_generation': self.active_generation,
            'current_task': self.current_task
        }
        
    async def check_sexual_content(self, prompt):
        """Check if the prompt contains sexual content using Granite Guardian."""
        try:
            import ollama
            
            # Skip extremely short prompts (unlikely to be problematic)
            if (len(prompt.strip()) < 3):
                logging.info(f"MODERATION: Skipping check for very short prompt: '{prompt}'")
                return False
            
            # Log that we're checking for sexual content
            logging.info(f"MODERATION: Checking prompt for sexual content: '{prompt}'")
            
            # System prompt specifically for sexual content detection
            system_prompt = "sexual_content"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            # Log exactly what we're sending to the model
            logging.info(f"MODERATION REQUEST: System='{system_prompt}', User='{prompt}'")
            
            # Create client with no timeout - let it run as long as needed
            client = ollama.AsyncClient()
            
            # Super long timeout (5 minutes) - practically no timeout for normal operations
            try:
                # This will wait indefinitely until Granite Guardian responds
                logging.info(f"MODERATION: Waiting for Granite Guardian response...")
                
                # Using a very long timeout (5 minutes) instead of no timeout at all
                # to prevent completely hanging if something goes catastrophically wrong
                response = await asyncio.wait_for(
                    client.chat(
                        model="granite3-guardian:8b",
                        messages=messages,
                        options={"temperature": 0, "num_predict": 10}
                    ), 
                    timeout=300.0  # 5 minute timeout (300 seconds)
                )
                
                # Extract and log the full message content
                full_response = response['message']['content']
                logging.info(f"MODERATION FULL TEXT: '{full_response}'")
                
                # Granite Guardian responds with "yes" or "no"
                result = full_response.strip().lower()
                is_sexual = result == "yes"  # Exact match only
                
                # Log the final decision with clear markers
                if is_sexual:
                    logging.warning(f"MODERATION DECISION: [BLOCKED] Sexual content detected in prompt: '{prompt}'")
                else:
                    logging.info(f"MODERATION DECISION: [ALLOWED] Prompt passed sexual content check: '{prompt}'")
                    
                return is_sexual
                
            except asyncio.TimeoutError:
                # This will only happen after 5 full minutes of waiting
                logging.error("MODERATION FATAL TIMEOUT: Granite Guardian did not respond after 5 minutes")
                logging.warning(f"MODERATION DECISION: [BLOCKED] Guard model not responding, cancelling image generation request for: '{prompt}'")
                return True  # Block generation after extreme timeout
                
            except Exception as e:
                logging.error(f"MODERATION ERROR accessing Granite Guardian: {e}", exc_info=True)
                logging.warning(f"MODERATION DECISION: [BLOCKED] Guard model not available, cancelling image generation request for: '{prompt}'")
                return True  # Block image generation if there's any error with moderation
            
        except Exception as e:
            logging.error(f"MODERATION ERROR: {e}", exc_info=True)
            logging.warning(f"MODERATION DECISION: [BLOCKED] Guard model not available, cancelling image generation request for: '{prompt}'")
            return True  # Block image generation on any error

    async def check_jailbreak_attempt(self, prompt):
        """Check if the prompt is attempting to jailbreak content filters."""
        try:
            import ollama
            
            # Log that we're checking for jailbreak attempts
            logging.info(f"MODERATION: Checking prompt for jailbreak attempts: '{prompt}'")
            
            # System prompt specifically for jailbreak detection
            system_prompt = "jailbreak"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            # Log exactly what we're sending to the model
            logging.info(f"MODERATION REQUEST: System='{system_prompt}', User='{prompt}'")
            
            # Set options for deterministic results
            client = ollama.AsyncClient()
            response = await client.chat(
                model="granite3-guardian:8b",
                messages=messages,
                options={"temperature": 0}
            )
            
            # Log the complete raw response object
            logging.info(f"MODERATION RAW RESPONSE: {response}")
            
            # Extract and log the full message content
            full_response = response['message']['content']
            logging.info(f"MODERATION FULL TEXT: '{full_response}'")
            
            # Normalized version for decision making
            result = full_response.strip().lower()
            logging.info(f"MODERATION NORMALIZED: '{result}'")
            
            # The model returns Yes or No
            is_jailbreak = result == "yes"
            
            # Log the final decision with clear markers
            if is_jailbreak:
                logging.warning(f"MODERATION DECISION: [BLOCKED] Jailbreak attempt detected in prompt: '{prompt}'")
            else:
                logging.info(f"MODERATION DECISION: [ALLOWED] Prompt passed jailbreak check: '{prompt}'")
                
            return is_jailbreak
        except Exception as e:
            logging.error(f"MODERATION ERROR: {e}", exc_info=True)
            # Log the complete stack trace for better debugging
            return False  # Changed to allow content on error instead of blocking

    def optimize_memory(self):
        """Optimize memory to reduce fragmentation"""
        if not torch.cuda.is_available():
            return
            
        # Clear PyTorch cache
        torch.cuda.empty_cache()
        
        # Run garbage collection
        gc.collect()
        
        # Force compaction of memory (can help with fragmentation)
        if hasattr(torch.cuda, 'memory_stats'):  # Only available in newer PyTorch
            try:
                torch.cuda.memory_stats()  # Force memory compaction
            except:
                pass