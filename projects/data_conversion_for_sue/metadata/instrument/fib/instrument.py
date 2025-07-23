"""Sue's Fiber Photometry Rig"""

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

camera_assembly_2 = d.CameraAssembly(
    name="Tongue camera assembly",
    target=d.CameraTarget.TONGUE,
    relative_position=[AnatomicalRelative.LEFT],
    camera=d.Camera(
        name="Tongue camera",
        manufacturer=Organization.BASLER,
        data_interface="USB",
        model="acA640-750um",
        serial_number="24621482",
        frame_rate=550,
        frame_rate_unit=FrequencyUnit.HZ,
    ),
    lens=d.Lens(
        name="Gold Telecentric lens",
        manufacturer=Organization.EDMUND_OPTICS,
        model="55-349",
    ),
)

patch_cord = d.FiberPatchCord(
    name="Fiber optic patch cord",
    manufacturer=d.Organization.DORIC, # confirm
    core_diameter=200, # confirm
    numerical_aperture=0.37, # confirm
)

light_sources = [
    d.LightEmittingDiode(
        name="470nm LED",
        manufacturer=Organization.THORLABS,
        model="M470F3",
        wavelength=470,
    ),
    d.LightEmittingDiode(
        name="415nm LED",
        manufacturer=Organization.THORLABS,
        model="M415F3",
        wavelength=415,
    ),
    d.LightEmittingDiode(
        name="565nm LED",
        manufacturer=Organization.THORLABS,
        model="M565F3",
        wavelength=565,
    ),
    d.LightEmittingDiode(
        name="810nm LED",
        manufacturer=Organization.THORLABS,
        model="M810L5",
        wavelength=810,
    )
]

detector_1 = d.Detector(
    name="Green CMOS",
    serial_number="21396991",
    manufacturer=Organization.FLIR,
    model="BFS-U3-20S40M",
    detector_type="Camera",
    data_interface="USB",
    cooling="Air",
    immersion="air",
    bin_width=4,
    bin_height=4,
    bin_mode="Additive",
    crop_offset_x=0,
    crop_offset_y=0,
    crop_width=200,
    crop_height=200,
    gain=2,
    chroma="Monochrome",
    bit_depth=16,
)

detector_2 = d.Detector(
    name="Red CMOS",
    serial_number="21396991",
    manufacturer=Organization.FLIR,
    model="BFS-U3-20S40M",
    detector_type="Camera",
    data_interface="USB",
    cooling="Air",
    immersion="air",
    bin_width=4,
    bin_height=4,
    bin_mode="Additive",
    crop_offset_x=0,
    crop_offset_y=0,
    crop_width=200,
    crop_height=200,
    gain=2,
    chroma="Monochrome",
    bit_depth=16,
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

instrument = r.Instrument(
    location="321", 
    instrument_id="FIP_Sue",
    modification_date=date(2021, 2, 10),
    modalities=[Modality.FIB, Modality.BEHAVIOR_VIDEOS, Modality.BEHAVIOR],
    coordinate_system=CoordinateSystemLibrary.BREGMA_ARI,
    components=[
        camera_assembly_1,
        camera_assembly_2,
        patch_cord,
        *light_sources,
        detector_1,
        detector_2,
        lick_spout_assembly,
        speaker,
        tube,
        daq
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
    serialized = instrument.model_dump_json()
    deserialized = r.Instrument.model_validate_json(serialized)
    deserialized.write_standard_file()


###
# daq arduino Uno



#     pinMode(CSplus, OUTPUT); digitalWrite(CSplus, LOW);
#     pinMode(CSminus, OUTPUT); digitalWrite(CSminus, LOW);
#     pinMode(odorBlank, OUTPUT); digitalWrite(odorBlank, LOW);
#     pinMode(waterR, OUTPUT); digitalWrite(waterR, LOW);
#     pinMode(waterL, OUTPUT); digitalWrite(waterL, LOW);    
#     pinMode(solRight, OUTPUT); digitalWrite(solRight, LOW);
#     pinMode(solLeft, OUTPUT); digitalWrite(solLeft, LOW);
#     pinMode(led, OUTPUT); digitalWrite(led, LOW);
#     pinMode(cueSync, OUTPUT); digitalWrite(cueSync, LOW);
#     pinMode(lickSync, OUTPUT); digitalWrite(lickSync, LOW);
#     // input pints
#     pinMode(lickR, INPUT);
#     pinMode(lickL, INPUT);

# CSplus and minus connects to speaker; 
# waterR/L connected to water solenoid; 
# lickR/L for lick Janelia lick sensors; 
# solRight/Left for lick retraction control;

 
 
# }

# #ephys: 
# no tongue camera
# no fiber photometry
# ephys neuralynx (daq) - Sue send ID
# no leds
