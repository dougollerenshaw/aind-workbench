"""
Fiber Schematic Viewer - Flask Application
Generates fiber implant schematics from AIND metadata.
"""

import argparse
import io
import base64
import json
import os
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify
import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Circle, FancyBboxPatch
import numpy as np
from typing import List, Dict, Optional

# Import configuration
import config

app = Flask(__name__, template_folder="params/templates", static_folder="params/static")


def get_cache_path(subject_id: str, cache_dir: str) -> Path:
    """Get the cache file path for a subject."""
    return Path(cache_dir) / f"{subject_id}.json"


def get_cached_procedures(subject_id: str, cache_dir: str, cache_ttl_hours: int) -> Optional[Dict]:
    """
    Try to get procedures from cache.
    
    Args:
        subject_id: Subject ID
        cache_dir: Cache directory path
        cache_ttl_hours: Cache time-to-live in hours
        
    Returns:
        Cached procedures dict if found and not expired, None otherwise
    """
    cache_path = get_cache_path(subject_id, cache_dir)
    
    if not cache_path.exists():
        return None
    
    try:
        # Check if cache is expired
        cache_age_seconds = time.time() - cache_path.stat().st_mtime
        cache_age_hours = cache_age_seconds / 3600
        
        if cache_age_hours > cache_ttl_hours:
            print(f"Cache expired for subject {subject_id} (age: {cache_age_hours:.1f}h)")
            return None
        
        # Load from cache
        with open(cache_path, 'r') as f:
            data = json.load(f)
        
        print(f"Cache hit for subject {subject_id} (age: {cache_age_hours:.1f}h)")
        return data
        
    except Exception as e:
        print(f"Error reading cache for subject {subject_id}: {e}")
        return None


def save_to_cache(subject_id: str, procedures_data: Dict, cache_dir: str) -> None:
    """
    Save procedures data to cache.
    
    Args:
        subject_id: Subject ID
        procedures_data: Procedures dictionary to cache
        cache_dir: Cache directory path
    """
    try:
        cache_path = get_cache_path(subject_id, cache_dir)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cache_path, 'w') as f:
            json.dump(procedures_data, f, indent=2)
        
        print(f"Cached procedures for subject {subject_id}")
        
    except Exception as e:
        print(f"Error saving cache for subject {subject_id}: {e}")


def get_procedures_for_subject(
    subject_id: str, 
    db_host: str = None,
    cache_dir: str = None,
    cache_ttl_hours: int = 168
) -> Optional[Dict]:
    """
    Get procedures for a subject from cache or metadata service.

    Args:
        subject_id: Subject ID to search for
        db_host: Unused (kept for backward compatibility)
        cache_dir: Cache directory path (default: .cache/procedures)
        cache_ttl_hours: Cache time-to-live in hours (default: 168 = 1 week)

    Returns:
        Procedures dictionary if found, None otherwise
    """
    from aind_metadata_service_client import Configuration, ApiClient, DefaultApi
    
    # Set default cache directory
    if cache_dir is None:
        cache_dir = ".cache/procedures"
    
    # Try cache first
    cached_data = get_cached_procedures(subject_id, cache_dir, cache_ttl_hours)
    if cached_data:
        return cached_data
    
    print(f"Querying metadata service for subject {subject_id}...")

    # Configure API client for internal metadata service
    configuration = Configuration(host="http://aind-metadata-service")

    try:
        with ApiClient(configuration) as api_client:
            api_instance = DefaultApi(api_client)

            # Query metadata service for procedures
            response = api_instance.get_procedures(subject_id=subject_id)

            if response:
                print(f"Found procedures for subject {subject_id}")
                # Convert response to dict
                if hasattr(response, "to_dict"):
                    procedures_dict = response.to_dict()
                else:
                    procedures_dict = response
                
                result = {"procedures": procedures_dict}
                save_to_cache(subject_id, result, cache_dir)
                return result

    except Exception as e:
        # Check if it's a validation error with response body
        # (metadata service may return 400 with valid data due to schema validation issues)
        if hasattr(e, "body") and e.body:
            try:
                body_json = json.loads(e.body)
                # If we got procedures data despite validation error, use it
                if "subject_procedures" in body_json:
                    print(f"Found procedures for subject {subject_id} (with validation warnings)")
                    result = {"procedures": body_json}
                    save_to_cache(subject_id, result, cache_dir)
                    return result
            except:
                pass

        print(f"Error querying metadata service: {e}")

    print(f"No procedures found for subject {subject_id}")
    return None


class FiberSchematicGenerator:
    """Generate fiber implant schematics from procedures metadata."""

    @staticmethod
    def safe_float(value, default=0.0):
        """Safely convert value to float, handling None and invalid values."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def extract_fiber_implants(self, procedures_data: Dict) -> List[Dict]:
        """
        Extract fiber implant information from procedures data.
        Handles both V1 and V2 metadata schemas.

        Args:
            procedures_data: Parsed procedures.json data

        Returns:
            List of fiber implant dictionaries with standardized fields
        """
        fibers = []

        # Navigate through the procedures structure
        subject_procedures = procedures_data.get("procedures", {}).get("subject_procedures", [])

        for surgery in subject_procedures:
            # Check both V1 (procedure_type) and V2 (object_type) schemas
            surgery_type = surgery.get("procedure_type") or surgery.get("object_type")

            if surgery_type == "Surgery":
                procedures = surgery.get("procedures", [])

                for procedure in procedures:
                    # Check both V1 and V2 schemas for procedure type
                    proc_type = procedure.get("procedure_type") or procedure.get("object_type")

                    # V1: procedure_type == 'Fiber implant'
                    if proc_type == "Fiber implant":
                        probes = procedure.get("probes", [])

                        for probe in probes:
                            # Safely get ophys_probe - it might be missing or not a dict
                            ophys_probe = probe.get("ophys_probe", {})
                            if not isinstance(ophys_probe, dict):
                                ophys_probe = {}

                            # Extract targeted structure - handle both string and object
                            targeted_structure = probe.get("targeted_structure", "Unknown")
                            if isinstance(targeted_structure, dict):
                                targeted_structure = targeted_structure.get("name", "Unknown")

                            fiber_info = {
                                "name": ophys_probe.get("name", "Unknown"),
                                "ap": self.safe_float(probe.get("stereotactic_coordinate_ap")),
                                "ml": self.safe_float(probe.get("stereotactic_coordinate_ml")),
                                "dv": self.safe_float(probe.get("stereotactic_coordinate_dv")),
                                "angle": self.safe_float(probe.get("angle")),
                                "unit": probe.get("stereotactic_coordinate_unit", "millimeter"),
                                "reference": probe.get("stereotactic_coordinate_reference", "Bregma"),
                                "targeted_structure": targeted_structure,
                            }
                            fibers.append(fiber_info)

                    # V2: object_type == 'Probe implant' with implanted_device.object_type == 'Fiber probe'
                    elif proc_type == "Probe implant":
                        implanted_device = procedure.get("implanted_device", {})
                        device_type = implanted_device.get("object_type", "")

                        if device_type == "Fiber probe":
                            # In V2, coordinates are in device_config.transform
                            device_config = procedure.get("device_config", {})

                            # Default values
                            ml = 0
                            dv = 0
                            ap = 0
                            angle = 0

                            # Extract coordinates from transform array
                            transform = device_config.get("transform", [])

                            for transform_obj in transform:
                                obj_type = transform_obj.get("object_type", "")

                                # Translation contains [AP, ML, DV]
                                if obj_type == "Translation":
                                    translation = transform_obj.get("translation", [])
                                    if isinstance(translation, list) and len(translation) >= 3:
                                        ap = self.safe_float(translation[0])  # Anterior-Posterior
                                        ml = self.safe_float(translation[1])  # Medial-Lateral
                                        dv = self.safe_float(translation[2])  # Dorsal-Ventral

                                # Rotation contains angles
                                elif obj_type == "Rotation":
                                    angles = transform_obj.get("angles", [])
                                    if isinstance(angles, list) and angles:
                                        # Use first non-zero angle if available
                                        for a in angles:
                                            if a is not None and a != 0:
                                                angle = self.safe_float(a)
                                                break

                            # Get targeted structure
                            primary_target = device_config.get("primary_targeted_structure", {})
                            target_name = primary_target.get("name", "Not specified in surgical request form")

                            fiber_info = {
                                "name": device_config.get("device_name", "Unknown"),
                                "ap": ap,
                                "ml": ml,
                                "dv": dv,
                                "angle": angle,
                                "unit": "millimeter",
                                "reference": device_config.get("coordinate_system", {}).get("origin", "Bregma"),
                                "targeted_structure": target_name,
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
            zorder=1,
        )
        ax.add_patch(skull)

        # Bregma marker (origin)
        bregma = Circle(
            (0, 0),
            radius=config.BREGMA_RADIUS,
            facecolor=config.BREGMA_COLOR,
            edgecolor=config.BREGMA_EDGE_COLOR,
            linewidth=1.5,
            zorder=5,
        )
        ax.add_patch(bregma)
        ax.text(
            0,
            -0.8,
            "Bregma",
            ha="center",
            va="top",
            fontsize=config.REFERENCE_FONTSIZE,
            fontweight="bold",
            color=config.BREGMA_EDGE_COLOR,
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
            alpha=0.7,
        )
        ax.add_patch(lambda_marker)
        ax.text(
            0,
            lambda_ap - 0.6,
            "Lambda",
            ha="center",
            va="top",
            fontsize=config.REFERENCE_FONTSIZE,
            color=config.LAMBDA_EDGE_COLOR,
            alpha=0.7,
        )

        # Add coordinate grid
        self._add_coordinate_grid(ax)

    def _add_coordinate_grid(self, ax: plt.Axes):
        """Add a subtle coordinate grid for reference."""
        # Vertical gridlines (ML axis)
        for ml in range(-6, 7, 2):
            ax.axvline(
                ml, color=config.GRID_COLOR, linestyle=config.GRID_LINESTYLE, linewidth=0.5, alpha=config.GRID_ALPHA
            )

        # Horizontal gridlines (AP axis)
        for ap in range(-10, 11, 2):
            ax.axhline(
                ap, color=config.GRID_COLOR, linestyle=config.GRID_LINESTYLE, linewidth=0.5, alpha=config.GRID_ALPHA
            )

    def draw_fiber(self, ax: plt.Axes, fiber: Dict, fiber_index: int):
        """Draw a single fiber implant on the schematic."""
        # Ensure all values are floats (matplotlib requires numeric types)
        ml = self.safe_float(fiber.get("ml", 0))
        ap = self.safe_float(fiber.get("ap", 0))
        angle = self.safe_float(fiber.get("angle", 0))
        name = fiber.get("name", "Unknown")

        # Choose color
        color = config.FIBER_COLORS[fiber_index % len(config.FIBER_COLORS)]

        # Draw fiber insertion point
        fiber_point = Circle(
            (ml, ap), radius=config.FIBER_MARKER_RADIUS, facecolor=color, edgecolor="black", linewidth=2, zorder=10
        )
        ax.add_patch(fiber_point)

        # Label the fiber - position based on left/right side to avoid overlap
        label_offset_y = 0.9
        if ml < 0:  # Left side - align to right corner
            ha = "right"
        else:  # Right side - align to left corner
            ha = "left"

        ax.text(
            ml,
            ap + label_offset_y,
            name,
            ha=ha,
            va="bottom",
            fontsize=config.FIBER_LABEL_FONTSIZE,
            fontweight="bold",
            color="black",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=color, alpha=0.7, edgecolor="black"),
        )

    def create_schematic(self, fibers: List[Dict], subject_id: str) -> str:
        """
        Create the complete fiber implant schematic.
        Returns base64-encoded PNG image.
        """
        # Sort fibers by name (Fiber_0, Fiber_1, Fiber_2...) to ensure consistent order
        def get_fiber_index(fiber):
            name = fiber.get("name", "Unknown")
            # Extract number from "Fiber_0", "Fiber_1", etc.
            try:
                if "_" in name:
                    return int(name.split("_")[-1])
                return 999  # Put unknown names at end
            except (ValueError, IndexError):
                return 999

        sorted_fibers = sorted(fibers, key=get_fiber_index)

        # Create figure
        fig, ax = plt.subplots(figsize=(config.FIGURE_WIDTH, config.FIGURE_HEIGHT))

        # Draw skull outline
        self.create_skull_outline(ax)

        # Draw each fiber
        for idx, fiber in enumerate(sorted_fibers):
            self.draw_fiber(ax, fiber, idx)

        # Set up axes
        ax.set_xlim(-config.SKULL_WIDTH_MM / 2 - 2, config.SKULL_WIDTH_MM / 2 + 2)
        ax.set_ylim(-config.SKULL_LENGTH_MM / 2 - 2, config.SKULL_LENGTH_MM / 2 + 2)
        ax.set_aspect("equal")

        # Labels
        ax.set_xlabel("Medial-Lateral (mm)", fontsize=config.LABEL_FONTSIZE, fontweight="bold")
        ax.set_ylabel("Anterior-Posterior (mm)", fontsize=config.LABEL_FONTSIZE, fontweight="bold")

        # Title
        title = f"Fiber Implant Locations - Top View\nSubject: {subject_id}"
        ax.set_title(title, fontsize=config.TITLE_FONTSIZE, fontweight="bold", pad=20)

        # Add legend with fiber details (color-coded text, no box)
        # Use the same sorted_fibers from above
        legend_items = self._create_legend_text(sorted_fibers)

        # Add colored text lines
        legend_y = 0.98
        line_spacing = 0.035

        for text, color in legend_items:
            ax.text(
                0.02,
                legend_y,
                text,
                transform=ax.transAxes,
                fontsize=config.LEGEND_FONTSIZE,
                verticalalignment="top",
                color=color,
                fontweight="bold" if color != "black" else "normal",
                family="monospace",
            )
            # Count newlines for proper spacing
            num_lines = text.count("\n") + 1
            legend_y -= line_spacing * num_lines

        # Grid
        ax.grid(True, alpha=config.GRID_ALPHA, linestyle="--")

        # Tight layout
        plt.tight_layout()

        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=config.DPI, bbox_inches="tight")
        buf.seek(0)
        plt.close()

        # Encode as base64
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        return img_base64

    def _create_legend_text(self, fibers: List[Dict]) -> List[tuple]:
        """
        Create legend data with fiber details and colors.
        Returns list of (text, color) tuples.
        """
        legend_items = [("Fiber Details:", "black")]
        for idx, fiber in enumerate(fibers):
            color = config.FIBER_COLORS[idx % len(config.FIBER_COLORS)]

            # Ensure all values are floats for formatting
            ap = self.safe_float(fiber.get("ap", 0))
            ml = self.safe_float(fiber.get("ml", 0))
            dv = self.safe_float(fiber.get("dv", 0))
            angle = self.safe_float(fiber.get("angle", 0))
            name = fiber.get("name", "Unknown")

            # Combine coordinates and target in one text block
            text = f"{name}: AP={ap:.2f}, ML={ml:.2f}, DV={dv:.2f} mm"
            if abs(angle) > 1:
                text += f" ∠{angle}°"

            # Add target on a new line
            target = fiber.get("targeted_structure", "Unknown")
            if not target or target == "" or target.lower() == "root":
                target = "Not specified in surgical request form"
            text += f"\nTarget: {target}"

            legend_items.append((text, color))
        return legend_items


# Flask routes


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate_schematic():
    """Generate schematic for a given subject ID."""
    try:
        data = request.get_json()
        subject_id = data.get("subject_id", "").strip()

        if not subject_id:
            return jsonify({"error": "Subject ID is required"}), 400

        # Query metadata service for procedures (with caching)
        cache_dir = app.config.get("CACHE_DIR", ".cache/procedures")
        cache_ttl = app.config.get("CACHE_TTL_HOURS", 168)
        procedures_data = get_procedures_for_subject(subject_id, cache_dir=cache_dir, cache_ttl_hours=cache_ttl)

        if not procedures_data:
            return (
                jsonify(
                    {
                        "error": f"Could not find a procedures record for subject {subject_id}. "
                        f"This subject may not have surgical procedures recorded yet."
                    }
                ),
                404,
            )

        # Generate schematic
        generator = FiberSchematicGenerator()
        try:
            fibers = generator.extract_fiber_implants(procedures_data)
        except Exception as e:
            import traceback
            import sys

            print(f"ERROR in extract_fiber_implants: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            sys.stderr.flush()
            raise

        if not fibers:
            return (
                jsonify(
                    {
                        "error": f"Found procedures record for subject {subject_id}, but no fiber implants were found in the procedures data. "
                        f"This subject may not have had fiber implant surgery yet."
                    }
                ),
                404,
            )

        # Create schematic image
        try:
            img_base64 = generator.create_schematic(fibers, subject_id)
        except Exception as e:
            import traceback
            import sys

            print(f"ERROR in create_schematic: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            sys.stderr.flush()
            raise

        return jsonify({"success": True, "image": img_base64, "fiber_count": len(fibers), "subject_id": subject_id})

    except Exception as e:
        import traceback
        import sys

        error_traceback = traceback.format_exc()
        # Print to stderr to ensure it shows up in logs
        print(f"Error generating schematic: {e}", file=sys.stderr)
        print(f"Full traceback:\n{error_traceback}", file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": f"Error generating schematic: {str(e)}"}), 500


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fiber Schematic Viewer")
    parser.add_argument(
        "--host", type=str, default=config.HOST, help=f"Host address to bind to (default: {config.HOST})"
    )
    parser.add_argument("--port", type=int, default=config.PORT, help=f"Port to bind to (default: {config.PORT})")
    parser.add_argument(
        "--debug", action="store_true", default=config.DEBUG, help=f"Enable debug mode (default: {config.DEBUG})"
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=".cache/procedures",
        help="Cache directory for procedures data (default: .cache/procedures)"
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=168,
        help="Cache TTL in hours (default: 168 = 1 week)"
    )

    args = parser.parse_args()

    # Store configuration in Flask app config
    app.config["CACHE_DIR"] = args.cache_dir
    app.config["CACHE_TTL_HOURS"] = args.cache_ttl

    print(f"Starting Fiber Schematic Viewer on {args.host}:{args.port}")
    print(f"Using AIND Metadata Service for procedure data")
    print(f"Cache directory: {args.cache_dir}")
    print(f"Cache TTL: {args.cache_ttl} hours")
    print(f"Access at: http://localhost:{args.port}")

    app.run(host=args.host, port=args.port, debug=args.debug)
