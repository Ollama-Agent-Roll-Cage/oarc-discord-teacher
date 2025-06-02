import os
import svgwrite
from svgwrite import animate
import cairosvg
from PIL import Image
import imageio
import numpy as np
from pathlib import Path
import subprocess
import tempfile
import shutil

class SVGAnimationBuilder:
    def __init__(self, output_dir, width=800, height=600, duration=5):
        """
        Initialize the SVG Animation Builder
        
        Args:
            output_dir (str): Directory to save SVG and exported files
            width (int): SVG canvas width
            height (int): SVG canvas height
            duration (float): Animation duration in seconds
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.width = width
        self.height = height
        self.duration = duration
        self.svg = svgwrite.Drawing(size=(width, height))
        self.elements = []
        
    def add_text(self, text, x=50, y=50, font_size=30, fill='black', 
                 animation=None):
        """
        Add text element with optional animation
        
        Args:
            text (str): Text content
            x, y (int): Position coordinates
            font_size (int): Font size
            fill (str): Text color
            animation (dict): Animation parameters
        """
        text_elem = self.svg.text(text, insert=(x, y), 
                                 font_size=font_size, fill=fill)
        
        if animation:
            self._add_animation(text_elem, animation)
            
        self.svg.add(text_elem)
        self.elements.append(text_elem)
        return text_elem
    
    def add_circle(self, cx=100, cy=100, r=50, fill='red', 
                   stroke='black', stroke_width=2, animation=None):
        """
        Add circle element with optional animation
        """
        circle = self.svg.circle(center=(cx, cy), r=r, fill=fill,
                               stroke=stroke, stroke_width=stroke_width)
        
        if animation:
            self._add_animation(circle, animation)
            
        self.svg.add(circle)
        self.elements.append(circle)
        return circle
    
    def add_rectangle(self, x=50, y=50, width=100, height=50, 
                     fill='blue', stroke='black', stroke_width=2, 
                     animation=None):
        """
        Add rectangle element with optional animation
        """
        rect = self.svg.rect(insert=(x, y), size=(width, height),
                           fill=fill, stroke=stroke, 
                           stroke_width=stroke_width)
        
        if animation:
            self._add_animation(rect, animation)
            
        self.svg.add(rect)
        self.elements.append(rect)
        return rect
    
    def add_path(self, path_data, fill='none', stroke='black', 
                stroke_width=2, animation=None):
        """
        Add path element with optional animation
        
        Args:
            path_data (str): SVG path data string
        """
        path = self.svg.path(d=path_data, fill=fill, stroke=stroke,
                           stroke_width=stroke_width)
        
        if animation:
            self._add_animation(path, animation)
            
        self.svg.add(path)
        self.elements.append(path)
        return path
    
    def add_custom_svg(self, svg_content):
        """
        Add custom SVG content from string or file
        
        Args:
            svg_content (str): SVG content or file path
        """
        if os.path.isfile(svg_content):
            with open(svg_content, 'r') as f:
                svg_content = f.read()
        
        # Add as a group element
        group = self.svg.g()
        group.add(self.svg.raw(svg_content))
        self.svg.add(group)
        self.elements.append(group)
        return group
    
    def _add_animation(self, element, animation):
        """
        Add animation to an element
        
        Args:
            element: SVG element
            animation (dict): Animation parameters
                - attribute: Attribute to animate
                - from_val: Starting value
                - to_val: Ending value
                - dur: Duration (default: self.duration)
                - repeat: Repeat count (default: 'indefinite')
        """
        anim_params = {
            'attributeName': animation.get('attribute'),
            'from': animation.get('from_val'),
            'to': animation.get('to_val'),
            'dur': animation.get('dur', f"{self.duration}s"),
            'repeatCount': animation.get('repeat', 'indefinite')
        }
        
        anim = animate.Animate(**anim_params)
        element.add(anim)
    
    def save_svg(self, filename=None):
        """Save SVG file"""
        if filename is None:
            filename = 'animation.svg'
        
        filepath = self.output_dir / filename
        self.svg.saveas(str(filepath))
        return filepath
    
    def export_to_png_sequence(self, fps=30):
        """
        Export SVG animation to PNG sequence
        """
        png_dir = self.output_dir / 'png_sequence'
        png_dir.mkdir(exist_ok=True)
        
        # Save SVG first
        svg_path = self.save_svg('temp_animation.svg')
        
        # Calculate frames
        total_frames = int(self.duration * fps)
        
        for frame in range(total_frames):
            # This is simplified - in reality, you'd need to modify the SVG
            # for each frame to capture the animation state
            png_path = png_dir / f'frame_{frame:04d}.png'
            cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))
        
        return png_dir
    
    def export_to_gif(self, filename='animation.gif', fps=30):
        """
        Export SVG animation to GIF
        """
        # First export to PNG sequence
        png_dir = self.export_to_png_sequence(fps)
        
        # Create GIF from PNG sequence
        images = []
        for frame in sorted(png_dir.glob('*.png')):
            images.append(imageio.imread(frame))
        
        gif_path = self.output_dir / filename
        imageio.mimsave(gif_path, images, duration=1/fps)
        
        # Cleanup PNG sequence
        shutil.rmtree(png_dir)
        
        return gif_path
    
    def export_to_mp4(self, filename='animation.mp4', fps=30):
        """
        Export SVG animation to MP4 using ffmpeg
        """
        # First export to PNG sequence
        png_dir = self.export_to_png_sequence(fps)
        
        mp4_path = self.output_dir / filename
        
        # Use ffmpeg to create MP4
        ffmpeg_cmd = [
            'ffmpeg',
            '-framerate', str(fps),
            '-pattern_type', 'glob',
            '-i', str(png_dir / '*.png'),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(mp4_path)
        ]
        
        try:
            subprocess.run(ffmpeg_cmd, check=True, 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("ffmpeg not found or error occurred. Please install ffmpeg.")
            return None
        
        # Cleanup PNG sequence
        shutil.rmtree(png_dir)
        
        return mp4_path

# Example usage
if __name__ == "__main__":
    # Create builder instance
    builder = SVGAnimationBuilder('output', width=800, height=600, duration=5)
    
    # Add animated text
    builder.add_text(
        "Hello Animation!", 
        x=100, y=200, 
        font_size=40, 
        fill='blue',
        animation={
            'attribute': 'x',
            'from_val': '100',
            'to_val': '600',
            'dur': '5s',
            'repeat': 'indefinite'
        }
    )
    
    # Add animated circle
    builder.add_circle(
        cx=400, cy=300, r=50, 
        fill='red',
        animation={
            'attribute': 'r',
            'from_val': '50',
            'to_val': '100',
            'dur': '2s',
            'repeat': 'indefinite'
        }
    )
    
    # Add animated rectangle
    builder.add_rectangle(
        x=200, y=400, width=100, height=50,
        fill='green',
        animation={
            'attribute': 'width',
            'from_val': '100',
            'to_val': '300',
            'dur': '3s',
            'repeat': 'indefinite'
        }
    )
    
    # Add custom path with animation
    builder.add_path(
        "M 100 100 L 300 100 L 200 300 z",
        fill='yellow',
        stroke='black',
        animation={
            'attribute': 'opacity',
            'from_val': '1',
            'to_val': '0.2',
            'dur': '2s',
            'repeat': 'indefinite'
        }
    )
    
    # Save SVG
    svg_file = builder.save_svg('animated_demo.svg')
    print(f"SVG saved to: {svg_file}")
    
    # Export to GIF
    gif_file = builder.export_to_gif('animated_demo.gif', fps=30)
    if gif_file:
        print(f"GIF saved to: {gif_file}")
    
    # Export to MP4
    mp4_file = builder.export_to_mp4('animated_demo.mp4', fps=30)
    if mp4_file:
        print(f"MP4 saved to: {mp4_file}")