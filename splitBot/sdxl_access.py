from diffusers import StableDiffusionXLPipeline
import torch
import os
import asyncio  # Add this import
from PIL import Image
import logging
import gc  # For garbage collection
import time
from io import BytesIO  # Add this import

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Only log warnings and errors

class SDXLGenerator:
    """Stable Diffusion XL image generation module"""
    
    def __init__(self, model_path=None):
        # Default model path if not provided
        self.model_path = model_path or os.path.join("M:\\", "SDXL_MOD", "randommaxxArtMerge_v10.safetensors")
        self.pipe = None
        
    def load_model(self):
        """Load the SDXL model into memory with optimizations"""
        try:
            # Clear CUDA cache and run garbage collection first
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
                
            # Verify the file exists
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model file not found at {self.model_path}")
                
            logger.info(f"Loading SDXL model from: {self.model_path}")
            
            # Load the model with memory optimizations
            self.pipe = StableDiffusionXLPipeline.from_single_file(
                self.model_path,
                torch_dtype=torch.float16,  # Use half precision
                use_safetensors=True,
                variant="fp16"  # Explicitly request fp16 variant
            )
            
            # Enable memory efficient attention
            self.pipe.enable_attention_slicing(slice_size="auto")
            
            # Enable VAE slicing for memory efficiency
            self.pipe.enable_vae_slicing()
            
            # Move to GPU with specific options
            self.pipe.to("cuda")
            
            logger.info("SDXL model loaded successfully with memory optimizations!")
            return True
            
        except Exception as e:
            logger.error(f"Error loading SDXL model: {e}")
            return False
            
    def unload_model(self):
        """Unload model to free up VRAM"""
        try:
            if self.pipe is not None:
                self.pipe = None
                torch.cuda.empty_cache()
                gc.collect()
                logger.info("SDXL model unloaded to free memory")
            return True
        except Exception as e:
            logger.error(f"Error unloading SDXL model: {e}")
            return False
    
    def generate_image(self, prompt, negative_prompt=None, width=768, height=768, 
                      steps=20, guidance_scale=7.5, output_path=None, callback=None):
        """Generate an image with the specified parameters"""
        try:
            # Load model if not already loaded
            if self.pipe is None:
                if not self.load_model():
                    raise Exception("Failed to load SDXL model")
        
            # Set default negative prompt if not provided
            if negative_prompt is None:
                negative_prompt = "low quality, blurry, distorted, deformed, ugly, bad anatomy"
                
            # Generate the image
            logger.info(f"Generating SDXL image with prompt: {prompt[:50]}...")
            
            # Optimize for speed with smaller batch size
            generator = torch.Generator(device="cuda").manual_seed(int(time.time()))
            
            # These parameters boost speed with minimal quality loss
            results = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                generator=generator,
                callback=callback,
                callback_steps=5,  # Only call callback every 5 steps
                use_resolution_binning=True,  # Speed optimization
                output_type="pil"
            )
            
            # Process the image
            image = results.images[0]
            
            # Save to disk if path is provided
            if output_path:
                image.save(output_path)
                
            # Return image data
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            return img_byte_arr
        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            raise e
            
    def __del__(self):
        """Destructor to ensure memory is freed"""
        if hasattr(self, 'pipe') and self.pipe is not None:
            self.pipe = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()