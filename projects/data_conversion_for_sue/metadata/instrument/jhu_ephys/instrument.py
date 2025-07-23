"""Sue's JHU Ephys Rig"""

from datetime import date

# from aind_data_schema_models.coordinates import AnatomicalRelative
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.organizations import Organization

import aind_data_schema.components.devices as d
import aind_data_schema.core.instrument as r
from aind_data_schema.components.connections import Connection
from aind_data_schema.components.identifiers import Software
from aind_data_schema.components.coordinates import CoordinateSystemLibrary
from aind_data_schema_models.coordinates import AnatomicalRelative
from aind_data_schema_models.units import FrequencyUnit

camera_assembly_1 = d.CameraAssembly(
    name="Pupil camera assembly",
    target=d.CameraTarget.EYE,
    relative_position=[AnatomicalRelative.ANTERIOR, AnatomicalRelative.LEFT],
    camera=d.Camera(
        name="Pupil camera",
        manufacturer=Organization.THORLABS,
        data_interface="USB",
        frame_rate=30,
        frame_rate_unit=FrequencyUnit.HZ,
        recording_software=Software(name="ThorCam"),
    ),
    lens=d.Lens(
        name="Silver Telecentric lens",
        manufacturer=Organization.EDMUND_OPTICS,
        model="58-430",
    ),
)

lick_spout_assembly = d.LickSpoutAssembly( 
    name="Lick spout assembly",
    lick_spouts=[
        d.LickSpout(
            name="Left lick spout",
            spout_diameter=0.8,
            solenoid_valve=d.Device(
                name="Solenoid left",
                manufacturer=Organization.DIGIKEY,
                model="1568-11015-ND",
                ),
            lick_sensor=d.Device(
                name="Janelia_Lick_Detector Left",
                manufacturer=Organization.JANELIA,
            ),
            lick_sensor_type=d.LickSensorType("Capacitive"),
        ),
        d.LickSpout(
            name="Right lick spout",
            spout_diameter=0.8,
            solenoid_valve=d.Device(
                name="Solenoid right",
                manufacturer=Organization.DIGIKEY,
                model="1568-11015-ND",
                ),
            lick_sensor=d.Device(
                name="Janelia_Lick_Detector Right",
                manufacturer=Organization.JANELIA,
            ),
            lick_sensor_type=d.LickSensorType("Capacitive"),
        )
    ],
)

speaker = d.Speaker(
    name="Speaker",
    relative_position=[AnatomicalRelative.ANTERIOR],
    manufacturer=Organization.OTHER,
    notes="Unknown manufacturer"
)

tube = d.Tube(name="Mouse Tube", diameter=4.0)

daq = d.DAQDevice(
    name="Arduino",
    manufacturer=Organization.ARDUINO,
    model="Arduino Uno",
    data_interface="USB",
)

# ephys_daq = d.DAQDevice(
#     name="Neuralynx Ephys Acquisition System",
#     manufacturer=Organization.NEURALYNX,
#     model="Cheetah",
#     data_interface="PCIe",
# )

# Create an ephys assembly for the ECEPHYS modality
# ephys_assembly =(
#     name="Neuralynx Ephys Assembly",
#     probes=[
#         d.EphysProbe(
#             name="Tetrode array",
#             probe_model="Custom",
#         )
#     ],
#     manipulator=d.Manipulator(
#         name="Drive system",
#         manufacturer=Organization.OTHER,
#         notes="Custom drive system for tetrode positioning"
#     ),
# )

instrument = r.Instrument(
    location="JHU Room 295F", 
    instrument_id="hopkins_295F_nlyx",
    modification_date=date(2021, 2, 10),
    modalities=[Modality.ECEPHYS, Modality.BEHAVIOR_VIDEOS, Modality.BEHAVIOR],
    coordinate_system=CoordinateSystemLibrary.BREGMA_ARI,
    components=[
        camera_assembly_1,
        lick_spout_assembly,
        speaker,
        tube,
        daq,
        # ephys_assembly
    ],
    connections=[
        Connection(
            source_device="Arduino",
            source_port="10",
            target_device="Solenoid right",
        ),
        Connection(
            source_device="Arduino",
            source_port="11",
            target_device="Solenoid left",
        ),
        Connection(
            source_device="Arduino",
            source_port="5",
            target_device="Speaker",
        ),
        Connection(
            source_device="Arduino",
            source_port="7",
            target_device="Speaker",
        ),
        Connection(
            source_device="Janelia_Lick_Detector Right",
            target_device="Arduino",
            target_port="3",
        ),
        Connection(
            source_device="Janelia_Lick_Detector Left",
            target_device="Arduino",
            target_port="4",
        ),
    ],
    notes="Instrument made retroactively from incomplete records."
)

if __name__ == "__main__":
    instrument.write_standard_file()
