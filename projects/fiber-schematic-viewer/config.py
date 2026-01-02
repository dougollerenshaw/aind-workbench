"""
Configuration for fiber schematic visual parameters.
Edit these values to customize the appearance of generated schematics.
"""

# Skull dimensions (mm)
SKULL_LENGTH_MM = 25
SKULL_WIDTH_MM = 15

# Fiber marker colors (supports up to 8 fibers)
# Use hex color codes: https://htmlcolorcodes.com/
FIBER_COLORS = [
    '#FF6B6B',  # Red
    '#4ECDC4',  # Teal
    '#45B7D1',  # Blue
    '#FFA07A',  # Light Salmon
    '#98D8C8',  # Mint
    '#F7DC6F',  # Yellow
    '#BB8FCE',  # Purple
    '#85C1E2',  # Sky Blue
]

# Fiber marker size
FIBER_MARKER_RADIUS = 0.4  # mm

# Bregma marker (origin point)
BREGMA_COLOR = '#000000'  # Black
BREGMA_EDGE_COLOR = '#000000'  # Black
BREGMA_RADIUS = 0.3  # mm

# Lambda marker (posterior reference point)
LAMBDA_COLOR = '#000000'  # Black
LAMBDA_EDGE_COLOR = '#000000'  # Black
LAMBDA_RADIUS = 0.25  # mm

# Skull appearance
SKULL_FILL_COLOR = '#F5F5F5'  # Light gray
SKULL_EDGE_COLOR = '#333333'  # Dark gray
SKULL_ALPHA = 0.3  # Transparency (0-1)

# Grid and coordinate lines
GRID_COLOR = 'gray'
GRID_ALPHA = 0.2
GRID_LINESTYLE = ':'

# Font sizes
TITLE_FONTSIZE = 8.4
LABEL_FONTSIZE = 7.2
FIBER_LABEL_FONTSIZE = 6
LEGEND_FONTSIZE = 5.4
REFERENCE_FONTSIZE = 4.8

# Figure dimensions
FIGURE_WIDTH = 4  # inches
FIGURE_HEIGHT = 5  # inches
DPI = 300  # Resolution for saved images

# Flask app configuration
PORT = 8081
HOST = '0.0.0.0'  # Listen on all interfaces
DEBUG = True  # Set to False for production