#!/usr/bin/env python3
"""Test simplified ephys configuration"""

try:
    from aind_data_schema.core.acquisition import EphysAssemblyConfig, ManipulatorConfig
    from aind_data_schema.components.coordinates import Translation, CoordinateSystem, Axis
    print("✓ Import successful")
    
    # Test with configuration matching procedures.json
    config = EphysAssemblyConfig(
        device_name="Tetrode",
        manipulator=ManipulatorConfig(
            device_name="unknown",
            coordinate_system=CoordinateSystem(
                name="BREGMA_ARI",
                origin="Bregma",
                axes=[
                    Axis(name="AP", direction="Posterior_to_anterior"),
                    Axis(name="ML", direction="Left_to_right"),
                    Axis(name="SI", direction="Superior_to_inferior")
                ],
                axis_unit="millimeter"
            ),
            local_axis_positions=Translation(translation=[0, 0, 0])
        ),
        probes=[]  # Required field but can be empty list
    )
    print("✓ Procedures.json-compatible config works!")
    print(f"Manipulator: {config.manipulator}")
    print(f"Probes: {config.probes}")
    print(f"Modules: {config.modules}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
