import logging
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio
import re
import gc  # Add import for garbage collection

logger = logging.getLogger(__name__)

class ImageGenerationQueue:
    """Manages image generation requests with rate limiting and content moderation"""
    
    def __init__(self, rate_limit_count=3, rate_limit_period=3600):
        """Initialize the queue with rate limiting parameters
        
        Args:
            rate_limit_count (int): Maximum number of generations allowed in the period
            rate_limit_period (int): Time period for rate limiting in seconds
        """
        self.queue = []
        self.user_requests = defaultdict(list)
        self.rate_limit_count = rate_limit_count
        self.rate_limit_period = rate_limit_period
        self.processing = False
        self.banned_terms = [
            'nude', 'naked', 'porn', 'pornography', 'sex', 'sexual', 'nsfw', 
            'explicit', 'adult', 'xxx', 'hentai', 'erotic', 'arousing',
            'intercourse', 'genitals', 'genitalia', 'penis', 'vagina'
        ]
        self.jailbreak_patterns = [
            r'ignore.*?previous.*?(instructions|prompt)',
            r'disregard.*?(instructions|guidelines|filters)',
            r'bypass.*?(filter|moderation|detection)',
            r'(don\'t|do not|never).*?(follow|obey).*?(instructions|guidelines)',
            r'generate.*?(inappropriate|nsfw|explicit|harmful)',
            r'pretend.*?(different|new).*?(instructions|guidelines)'
        ]
        logger.info("Image Generation Queue initialized")
    
    async def add_request(self, user_id, prompt, callback, **kwargs):
        """Add an image generation request to the queue"""
        try:
            # Check if user is rate limited
            if self.is_rate_limited(user_id):
                return False, "You've reached your image generation limit. Please try again later."
            
            # Check if user is on cooldown
            if self.is_on_cooldown(user_id):
                return False, "Please wait before generating another image."
                
            # Check if user has too many pending requests
            if len(self.requests[user_id]) >= self.max_queue_size:
                return False, f"You have too many pending requests (max {self.max_queue_size})."
                
            # Check prompt for safety
            is_safe, reason = await self.check_prompt_safety(prompt)
            if not is_safe:
                return False, f"Prompt rejected: {reason}"
                
            # Add request to queue
            self.requests[user_id].append({
                "prompt": prompt,
                "callback": callback,
                "timestamp": datetime.now(),
                "kwargs": kwargs
            })
            
            # Update generation count for rate limiting
            self.user_generations[user_id].append(datetime.now())
            
            # Start processing if not already running
            if not self.processing:
                asyncio.create_task(self.process_queue())
                
            return True, "Your image request has been added to the queue."
            
        except Exception as e:
            logger.error(f"Error adding request to queue: {e}")
            return False, f"Error: {str(e)}"
    
    def is_on_cooldown(self, user_id):
        """Check if user is on generation cooldown"""
        if not self.requests[user_id]:
            return False
        
        last_request = max(req["timestamp"] for req in self.requests[user_id])
        elapsed = (datetime.now() - last_request).total_seconds()
        return elapsed < self.generation_cooldown
    
    def _get_cooldown_time(self, user_id):
        """Get remaining cooldown time in seconds"""
        if not self.user_requests[user_id]:
            return 0
            
        last_request = max(self.user_requests[user_id])
        cooldown_time = 60  # 60 seconds cooldown between requests
        time_since_last = (datetime.now() - last_request).total_seconds()
        
        return max(0, cooldown_time - time_since_last)
    
    def is_rate_limited(self, user_id):
        """Check if user has exceeded their rate limit"""
        # Remove old timestamps outside the rate limit period
        cutoff_time = datetime.now() - timedelta(seconds=self.rate_limit_period)
        self.user_generations[user_id] = [
            ts for ts in self.user_generations[user_id] if ts > cutoff_time
        ]
        
        # Check if user has exceeded their rate limit
        return len(self.user_generations[user_id]) >= self.rate_limit_count
    
    async def check_prompt_safety(self, prompt):
        """Check if the prompt contains inappropriate content"""
        # Check for sexual content
        sexual_result = await self.check_sexual_content(prompt)
        if sexual_result:
            return {
                'safe': False,
                'message': "Your prompt was rejected as it appears to request sexual or NSFW content"
            }
            
        # Check for jailbreak attempts
        jailbreak_result = await self.check_jailbreak_attempt(prompt)
        if jailbreak_result:
            return {
                'safe': False,
                'message': "Your prompt was rejected as it appears to attempt to bypass content guidelines"
            }
        
        return {'safe': True, 'message': "Prompt passed safety checks"}
    
    async def check_sexual_content(self, prompt):
        """Check if the prompt contains inappropriate sexual content"""
        prompt_lower = prompt.lower()
        
        # Check for banned terms
        for term in self.banned_terms:
            if term in prompt_lower:
                logger.warning(f"Banned term detected in prompt: {term}")
                return True
                
        return False
    
    async def check_jailbreak_attempt(self, prompt):
        """Check if the prompt attempts to jailbreak or bypass filters"""
        prompt_lower = prompt.lower()
        
        # Check for jailbreak patterns
        for pattern in self.jailbreak_patterns:
            if re.search(pattern, prompt_lower):
                logger.warning(f"Jailbreak attempt detected in prompt with pattern: {pattern}")
                return True
                
        # Count suspicious phrases
        suspicious_phrases = [
            "ignore", "bypass", "don't follow", "do not follow", 
            "disregard", "override", "new instructions"
        ]
        
        suspicion_count = sum(phrase in prompt_lower for phrase in suspicious_phrases)
        if suspicion_count >= 2:
            logger.warning(f"Multiple suspicious phrases detected in prompt: {suspicion_count}")
            return True
            
        return False
    
    async def process_queue(self):
        """Process pending image generation requests"""
        self.processing = True
        
        try:
            # Process all user queues
            for user_id, requests in list(self.requests.items()):
                if not requests:
                    continue
                    
                # Process the oldest request first
                requests.sort(key=lambda r: r["timestamp"])
                request = requests[0]
                
                try:
                    # Call the callback function to generate the image
                    callback = request["callback"]
                    await callback(request["prompt"], **request["kwargs"])
                except Exception as e:
                    logger.error(f"Error processing image request: {e}")
                
                # Remove the processed request
                self.requests[user_id].pop(0)
        finally:
            self.processing = False
            
            # If there are still requests, schedule another processing run
            for requests in self.requests.values():
                if requests:
                    asyncio.create_task(self.process_queue())
                    break