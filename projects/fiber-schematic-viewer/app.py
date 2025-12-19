"""
Fiber Schematic Viewer - Flask Application
Generates fiber implant schematics from AIND metadata.
"""

import argparse
import io
import base64
from flask import Flask, render_template, request, jsonify
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Circle
import numpy as np
from typing import List, Dict, Optional

# Import configuration
import config

app = Flask(__name__, 
            template_folder='params/templates',
            static_folder='params/static')


def get_procedures_for_subject(subject_id: str, db_host: str) -> Optional[Dict]:
    """
    Search for procedures record for a subject across multiple databases.
    
    Search order:
    1. metadata_index_v2 (DocDB)
    2. metadata_index (DocDB V1)
    3. Metadata service (stub for now - slow)
    
    Args:
        subject_id: Subject ID to search for
        db_host: MongoDB host
        
    Returns:
        Procedures dictionary if found, None otherwise
    """
    from aind_data_access_api.document_db import MetadataDbClient
    
    # Stage 1: Try V2 database first
    print(f"[Stage 1] Searching for subject {subject_id} in metadata_index_v2...")
    try:
        client_v2 = MetadataDbClient(
            host=db_host,
            database='metadata_index_v2',
            collection='data_assets',
        )
        
        pipeline = [
            {"$match": {"subject.subject_id": subject_id}},
            {"$project": {"procedures": 1, "subject.subject_id": 1}},
            {"$limit": 1}
        ]
        
        records = client_v2.aggregate_docdb_records(pipeline)
        
        if records and len(records) > 0:
            print(f"[Stage 1] Found record in V2 database")
            return {'procedures': records[0].get('procedures', {})}
    except Exception as e:
        print(f"[Stage 1] Error querying V2 database: {e}")
    
    # Stage 2: Try V1 database
    print(f"[Stage 2] Searching for subject {subject_id} in metadata_index (V1)...")
    try:
        client_v1 = MetadataDbClient(
            host=db_host,
            database='metadata_index',
            collection='data_assets',
        )
        
        pipeline = [
            {"$match": {"subject.subject_id": subject_id}},
            {"$project": {"procedures": 1, "subject.subject_id": 1}},
            {"$limit": 1}
        ]
        
        records = client_v1.aggregate_docdb_records(pipeline)
        
        if records and len(records) > 0:
            print(f"[Stage 2] Found record in V1 database")
            return {'procedures': records[0].get('procedures', {})}
    except Exception as e:
        print(f"[Stage 2] Error querying V1 database: {e}")
    
    # Stage 3: Try metadata service (stub for now - will be slow)
    print(f"[Stage 3] Would query metadata service for subject {subject_id} (not implemented yet)")
    # TODO: Implement metadata service query here
    # This will be slow (~30 seconds) but will find subjects that haven't run experiments yet
    # from aind_data_access_api.metadata_service import MetadataServiceClient
    # client = MetadataServiceClient()
    # procedures = client.get_procedures(subject_id)
    
    print(f"No procedures record found for subject {subject_id} in any database")
    return None


class FiberSchematicGenerator:
    """Generate fiber implant schematics from procedures metadata."""
    
    def extract_fiber_implants(self, procedures_data: Dict) -> List[Dict]:
        """
        Extract fiber implant information from procedures.json data.
        Handles both V1 and V2 database schemas.
        
        Args:
            procedures_data: Parsed procedures.json data
            
        Returns:
            List of fiber implant dictionaries with standardized fields
        """
        fibers = []
        
        # Navigate through the procedures structure
        subject_procedures = procedures_data.get('procedures', {}).get('subject_procedures', [])
        
        for surgery in subject_procedures:
            # Check both V1 (procedure_type) and V2 (object_type) schemas
            surgery_type = surgery.get('procedure_type') or surgery.get('object_type')
            
            if surgery_type == 'Surgery':
                procedures = surgery.get('procedures', [])
                
                for procedure in procedures:
                    # Check both V1 and V2 schemas for procedure type
                    proc_type = procedure.get('procedure_type') or procedure.get('object_type')
                    
                    # V1: procedure_type == 'Fiber implant'
                    if proc_type == 'Fiber implant':
                        probes = procedure.get('probes', [])
                        
                        for probe in probes:
                            fiber_info = {
                                'name': probe['ophys_probe'].get('name', 'Unknown'),
                                'ap': float(probe.get('stereotactic_coordinate_ap', 0)),
                                'ml': float(probe.get('stereotactic_coordinate_ml', 0)),
                                'dv': float(probe.get('stereotactic_coordinate_dv', 0)),
                                'angle': float(probe.get('angle', 0)),
                                'unit': probe.get('stereotactic_coordinate_unit', 'millimeter'),
                                'reference': probe.get('stereotactic_coordinate_reference', 'Bregma'),
                                'targeted_structure': probe.get('targeted_structure', 'Unknown'),
                            }
                            fibers.append(fiber_info)
                    
                    # V2: object_type == 'Probe implant' with implanted_device.object_type == 'Fiber probe'
                    elif proc_type == 'Probe implant':
                        implanted_device = procedure.get('implanted_device', {})
                        device_type = implanted_device.get('object_type', '')
                        
                        if device_type == 'Fiber probe':
                            # In V2, coordinates are in device_config.transform
                            device_config = procedure.get('device_config', {})
                            
                            # Default values
                            ml = 0
                            dv = 0
                            ap = 0
                            angle = 0
                            
                            # Extract coordinates from transform array
                            transform = device_config.get('transform', [])
                            
                            for transform_obj in transform:
                                obj_type = transform_obj.get('object_type', '')
                                
                                # Translation contains [AP, ML, DV]
                                if obj_type == 'Translation':
                                    translation = transform_obj.get('translation', [])
                                    if len(translation) >= 3:
                                        ap = float(translation[0])  # Anterior-Posterior
                                        ml = float(translation[1])  # Medial-Lateral
                                        dv = float(translation[2])  # Dorsal-Ventral
                                
                                # Rotation contains angles
                                elif obj_type == 'Rotation':
                                    angles = transform_obj.get('angles', [])
                                    if angles:
                                        # Use first non-zero angle if available
                                        for a in angles:
                                            if a != 0:
                                                angle = float(a)
                                                break
                            
                            # Get targeted structure
                            primary_target = device_config.get('primary_targeted_structure', {})
                            target_name = primary_target.get('name', 'Unknown')
                            
                            fiber_info = {
                                'name': device_config.get('device_name', 'Unknown'),
                                'ap': ap,
                                'ml': ml,
                                'dv': dv,
                                'angle': angle,
                                'unit': 'millimeter',
                                'reference': device_config.get('coordinate_system', {}).get('origin', 'Bregma'),
                                'targeted_structure': target_name,
                            }
                            fibers.append(fiber_info)
        
        return fibers
    
    def create_skull_outline(self, ax: plt.Axes):
        """Draw a stylized mouse skull outline (top-down view)."""
        # Main skull oval
        skull = patches.Ellipse(
            (0, 0), 
            width=config.SKULL_WIDTH_MM, 
            height=config.SKULL_LENGTH_MM,
            facecolor=config.SKULL_FILL_COLOR, 
            edgecolor=config.SKULL_EDGE_COLOR,
            linewidth=2,
            alpha=config.SKULL_ALPHA,
            zorder=1
        )
        ax.add_patch(skull)
        
        # Bregma marker (origin)
        bregma = Circle(
            (0, 0), 
            radius=config.BREGMA_RADIUS, 
            facecolor=config.BREGMA_COLOR, 
            edgecolor=config.BREGMA_EDGE_COLOR, 
            linewidth=1.5, 
            zorder=5
        )
        ax.add_patch(bregma)
        ax.text(
            0, -0.8, 'Bregma', 
            ha='center', va='top', 
            fontsize=config.REFERENCE_FONTSIZE, 
            fontweight='bold', 
            color=config.BREGMA_EDGE_COLOR
        )
        
        # Lambda marker (posterior reference point, typically ~4mm behind Bregma)
        lambda_ap = -4.0
        lambda_marker = Circle(
            (0, lambda_ap), 
            radius=config.LAMBDA_RADIUS, 
            facecolor=config.LAMBDA_COLOR, 
            edgecolor=config.LAMBDA_EDGE_COLOR, 
            linewidth=1.5, 
            zorder=5, 
            alpha=0.7
        )
        ax.add_patch(lambda_marker)
        ax.text(
            0, lambda_ap - 0.6, 'Lambda', 
            ha='center', va='top', 
            fontsize=config.REFERENCE_FONTSIZE, 
            color=config.LAMBDA_EDGE_COLOR, 
            alpha=0.7
        )
        
        # Add coordinate grid
        self._add_coordinate_grid(ax)
    
    def _add_coordinate_grid(self, ax: plt.Axes):
        """Add a subtle coordinate grid for reference."""
        # Vertical gridlines (ML axis)
        for ml in range(-6, 7, 2):
            ax.axvline(
                ml, 
                color=config.GRID_COLOR, 
                linestyle=config.GRID_LINESTYLE, 
                linewidth=0.5, 
                alpha=config.GRID_ALPHA
            )
        
        # Horizontal gridlines (AP axis)
        for ap in range(-10, 11, 2):
            ax.axhline(
                ap, 
                color=config.GRID_COLOR, 
                linestyle=config.GRID_LINESTYLE, 
                linewidth=0.5, 
                alpha=config.GRID_ALPHA
            )
    
    def draw_fiber(self, ax: plt.Axes, fiber: Dict, fiber_index: int):
        """Draw a single fiber implant on the schematic."""
        ml = fiber['ml']
        ap = fiber['ap']
        angle = fiber['angle']
        name = fiber['name']
        
        # Choose color
        color = config.FIBER_COLORS[fiber_index % len(config.FIBER_COLORS)]
        
        # Draw fiber insertion point
        fiber_point = Circle(
            (ml, ap), 
            radius=config.FIBER_MARKER_RADIUS, 
            facecolor=color, 
            edgecolor='black',
            linewidth=2, 
            zorder=10
        )
        ax.add_patch(fiber_point)
        
        # Draw angle indicator if fiber is angled
        if abs(angle) > 1:
            length = 1.5  # Length of angle indicator line
            angle_rad = np.radians(angle)
            dx = length * np.sin(angle_rad)
            dy = 0
            
            ax.plot(
                [ml, ml + dx], [ap, ap + dy], 
                color=color, linewidth=2, alpha=0.7, zorder=9
            )
            
            ax.text(
                ml + dx * 1.2, ap + dy, f'{angle}°', 
                fontsize=7, color=color, fontweight='bold',
                ha='center', va='center'
            )
        
        # Label the fiber - position based on left/right side to avoid overlap
        label_offset_y = 0.9
        if ml < 0:  # Left side - align to right corner
            ha = 'right'
        else:  # Right side - align to left corner
            ha = 'left'
        
        ax.text(
            ml, ap + label_offset_y, name, 
            ha=ha, va='bottom', 
            fontsize=config.FIBER_LABEL_FONTSIZE,
            fontweight='bold', color='black',
            bbox=dict(
                boxstyle='round,pad=0.3', 
                facecolor=color, alpha=0.7, edgecolor='black'
            )
        )
    
    def create_schematic(self, fibers: List[Dict], subject_id: str) -> str:
        """
        Create the complete fiber implant schematic.
        Returns base64-encoded PNG image.
        """
        # Create figure
        fig, ax = plt.subplots(
            figsize=(config.FIGURE_WIDTH, config.FIGURE_HEIGHT)
        )
        
        # Draw skull outline
        self.create_skull_outline(ax)
        
        # Draw each fiber
        for idx, fiber in enumerate(fibers):
            self.draw_fiber(ax, fiber, idx)
        
        # Set up axes
        ax.set_xlim(
            -config.SKULL_WIDTH_MM/2 - 2, 
            config.SKULL_WIDTH_MM/2 + 2
        )
        ax.set_ylim(
            -config.SKULL_LENGTH_MM/2 - 2, 
            config.SKULL_LENGTH_MM/2 + 2
        )
        ax.set_aspect('equal')
        
        # Labels
        ax.set_xlabel(
            'Medial-Lateral (mm)', 
            fontsize=config.LABEL_FONTSIZE, 
            fontweight='bold'
        )
        ax.set_ylabel(
            'Anterior-Posterior (mm)', 
            fontsize=config.LABEL_FONTSIZE, 
            fontweight='bold'
        )
        
        # Title
        title = f'Fiber Implant Locations - Top View\nSubject: {subject_id}'
        ax.set_title(
            title, 
            fontsize=config.TITLE_FONTSIZE, 
            fontweight='bold', 
            pad=20
        )
        
        # Add legend with fiber details
        legend_text = self._create_legend_text(fibers)
        ax.text(
            0.02, 0.98, legend_text, 
            transform=ax.transAxes,
            fontsize=config.LEGEND_FONTSIZE, 
            verticalalignment='top',
            bbox=dict(
                boxstyle='round', facecolor='white', 
                alpha=0.8, edgecolor='gray'
            )
        )
        
        # Grid
        ax.grid(True, alpha=config.GRID_ALPHA, linestyle='--')
        
        # Tight layout
        plt.tight_layout()
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=config.DPI, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Encode as base64
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return img_base64
    
    def _create_legend_text(self, fibers: List[Dict]) -> str:
        """Create legend text with fiber details."""
        lines = ['Fiber Details:\n']
        for fiber in fibers:
            lines.append(
                f"{fiber['name']}: "
                f"AP={fiber['ap']:.2f}, "
                f"ML={fiber['ml']:.2f}, "
                f"DV={fiber['dv']:.2f} mm"
            )
            if abs(fiber['angle']) > 1:
                lines.append(f"  ∠{fiber['angle']}°")
        return '\n'.join(lines)


# Flask routes

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate_schematic():
    """Generate schematic for a given subject ID."""
    try:
        data = request.get_json()
        subject_id = data.get('subject_id', '').strip()
        
        if not subject_id:
            return jsonify({'error': 'Subject ID is required'}), 400
        
        # Search for procedures across multiple databases
        db_host = app.config.get('DB_HOST', 'api.allenneuraldynamics.org')
        procedures_data = get_procedures_for_subject(subject_id, db_host)
        
        if not procedures_data:
            return jsonify({
                'error': f'Could not find a procedures record for subject {subject_id}. '
                         f'This subject may not have any data assets in the database yet.'
            }), 404
        
        # Generate schematic
        generator = FiberSchematicGenerator()
        fibers = generator.extract_fiber_implants(procedures_data)
        
        if not fibers:
            return jsonify({
                'error': f'Found procedures record for subject {subject_id}, but no fiber implants were found in the procedures data. '
                         f'This subject may not have had fiber implant surgery yet.'
            }), 404
        
        # Create schematic image
        img_base64 = generator.create_schematic(fibers, subject_id)
        
        return jsonify({
            'success': True,
            'image': img_base64,
            'fiber_count': len(fibers),
            'subject_id': subject_id
        })
        
    except Exception as e:
        print(f"Error generating schematic: {e}")
        return jsonify({'error': f'Error generating schematic: {str(e)}'}), 500


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fiber Schematic Viewer')
    parser.add_argument(
        '--host', 
        type=str, 
        default=config.HOST,
        help=f'Host address to bind to (default: {config.HOST})'
    )
    parser.add_argument(
        '--port', 
        type=int, 
        default=config.PORT,
        help=f'Port to bind to (default: {config.PORT})'
    )
    parser.add_argument(
        '--debug', 
        action='store_true',
        default=config.DEBUG,
        help=f'Enable debug mode (default: {config.DEBUG})'
    )
    parser.add_argument(
        '--db_host', 
        type=str, 
        default='api.allenneuraldynamics.org',
        help='MongoDB host (default: api.allenneuraldynamics.org)'
    )
    parser.add_argument(
        '--database', 
        type=str, 
        default='metadata_index',
        help='MongoDB database name (default: metadata_index)'
    )
    
    args = parser.parse_args()
    
    # Store configuration in Flask app config
    app.config['DB_HOST'] = args.db_host
    app.config['DATABASE'] = args.database
    
    print(f"Starting Fiber Schematic Viewer on {args.host}:{args.port}")
    print(f"MongoDB: {args.db_host}/{args.database}")
    print(f"Access at: http://localhost:{args.port}")
    
    app.run(
        host=args.host, 
        port=args.port, 
        debug=args.debug
    )