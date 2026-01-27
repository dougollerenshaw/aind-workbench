"""FIP (Fiber Photometry) mapper module.

Maps ProtoAcquisitionDataSchema JSON (from acquisition repo) to AIND Data Schema 2.0 Acquisition format.

The mapper:
- Validates input JSON against schema from aind-metadata-extractor
- Extracts timing, rig config, and session metadata from nested JSON structure
- Creates 3 channels per fiber: Green (470nm), Isosbestic (415nm), Red (565nm)
- Fetches intended measurements and implanted fiber info from metadata service (optional)

Note: We don't have access to the ethics_review_id in the extracted metadata. This should be provided by the extractor.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aind_metadata_extractor
import jsonschema
from aind_data_schema.components.configs import (
    Channel,
    DetectorConfig,
    LightEmittingDiodeConfig,
    PatchCordConfig,
    TriggerType,
)
from aind_data_schema.components.connections import Connection
from aind_data_schema.components.identifiers import Code
from aind_data_schema.core.acquisition import Acquisition, DataStream
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.units import PowerUnit, SizeUnit, TimeUnit

from aind_metadata_mapper.base import MapperJob, MapperJobSettings
from aind_metadata_mapper.fip.constants import (
    ACQUISITION_TYPE_AIND_VR_FORAGING,
    CAMERA_EXPOSURE_TIME_MICROSECONDS_PER_MILLISECOND,
    DEFAULT_LED_POWER,
    DEFAULT_OUTPUT_FILENAME,
    DEVICE_NAME_MAP,
    EMISSION_GREEN,
    EMISSION_RED,
    ETHICS_REVIEW_ID,
    EXCITATION_BLUE,
    EXCITATION_UV,
    EXCITATION_YELLOW,
    FIP_CAMERA_COMPRESSION,
    ROI_KEYWORD_BACKGROUND,
    ROI_KEYWORD_GREEN,
    ROI_KEYWORD_ISO,
    ROI_KEYWORD_RED,
    ROI_KEYWORD_ROI,
    VR_FORAGING_FIP_REPO_URL,
)
from aind_metadata_mapper.utils import (
    ensure_timezone,
    get_intended_measurements,
    get_procedures,
    get_protocols_for_modality,
    normalize_utc_timezone,
)

logger = logging.getLogger(__name__)


class FIPMapper(MapperJob):
    """FIP Mapper - transforms intermediate FIP data into Acquisition metadata.

    This mapper follows the standard pattern for AIND metadata mappers:
    - Takes intermediate metadata from extractor
    - Transforms to schema-compliant Acquisition
    - Outputs to standard filename: acquisition.json (configurable)

    Parameters
    ----------
    output_filename : str, optional
        Output filename for the acquisition metadata.
        Defaults to "acquisition.json".
    """

    def __init__(self, output_filename: str = DEFAULT_OUTPUT_FILENAME):
        """Initialize the FIP mapper.

        Parameters
        ----------
        output_filename : str, optional
            Output filename, by default "acquisition.json"
        """
        self.output_filename = output_filename

    def _validate_fip_metadata(self, metadata: dict) -> None:  # pragma: no cover
        """Validate FIP metadata against the JSON schema.

        Parameters
        ----------
        metadata : dict
            The metadata to validate.

        Raises
        ------
        FileNotFoundError
            If the fip.json schema file cannot be found.
        ValueError
            If validation fails with details about what went wrong.
        """
        # Load schema from extractor package
        schema_path = Path(aind_metadata_extractor.__file__).parent / "models" / "fip.json"  # pragma: no cover

        if not schema_path.exists():  # pragma: no cover
            raise FileNotFoundError(  # pragma: no cover
                f"FIP JSON schema not found at {schema_path}. "  # pragma: no cover
                "Ensure you have the correct version of aind-metadata-extractor installed."  # pragma: no cover
            )  # pragma: no cover

        with open(schema_path, "r") as f:  # pragma: no cover
            schema = json.load(f)  # pragma: no cover

        # Validate metadata against schema
        try:  # pragma: no cover
            jsonschema.validate(instance=metadata, schema=schema)  # pragma: no cover
        except jsonschema.ValidationError as e:  # pragma: no cover
            raise ValueError(f"FIP metadata validation failed: {e.message}\nPath: {e.path}") from e  # pragma: no cover

    def _parse_intended_measurements(
        self, subject_id: str, data: Optional[dict] = None
    ) -> Optional[Dict[str, Dict[str, Optional[str]]]]:
        """Parse intended measurements for FIP from the metadata service.

        Parameters
        ----------
        subject_id : str
            The subject ID to query.
        data : Optional[dict], optional
            Pre-fetched intended measurements data. If None, will be fetched from service.

        Returns
        -------
        Optional[Dict[str, Dict[str, Optional[str]]]]
            Dictionary mapping fiber names to channel measurements, e.g.:
            {
                "Fiber_0": {
                    "R": "dopamine",      # Red channel
                    "G": "calcium",       # Green channel
                    "B": None,            # Blue channel (typically unused)
                    "Iso": "control"      # Isosbestic channel
                },
                "Fiber_1": {...}
            }
            Returns None if the request fails or subject has no measurements.
        """
        if data is None:
            data = get_intended_measurements(subject_id)
        if not data:
            logger.warning(
                f"No intended_measurements information found for subject_id={subject_id}. "
                "These fields will be None in the resulting metadata file."
            )
            return None

        # Normalize to list: handle both single object and array responses
        measurements_list = data.get("data", [])
        if isinstance(measurements_list, dict):
            measurements_list = [measurements_list]

        # Convert to fiber-indexed dictionary
        result = {
            item["fiber_name"]: {
                "R": item.get("intended_measurement_R"),
                "G": item.get("intended_measurement_G"),
                "B": item.get("intended_measurement_B"),
                "Iso": item.get("intended_measurement_Iso"),
            }
            for item in measurements_list
            if item.get("fiber_name")
        }

        if not result:
            logger.warning(f"No valid fiber measurements found for subject_id={subject_id}.")
            return None
        return result

    def _extract_fiber_index(self, fiber_name: str) -> int:
        """Extract fiber index from fiber name.

        Parameters
        ----------
        fiber_name : str
            Fiber name (e.g., "Fiber_0").

        Returns
        -------
        int
            Fiber index.

        Raises
        ------
        ValueError
            If fiber name format is invalid and cannot be parsed.
        """
        if not fiber_name.startswith("Fiber_"):
            raise ValueError(
                f"Invalid fiber name format: '{fiber_name}'. " f"Expected format: 'Fiber_<index>' (e.g., 'Fiber_0')"
            )
        try:
            return int(fiber_name.split("_")[1])
        except (IndexError, ValueError) as e:
            raise ValueError(
                f"Could not parse fiber index from '{fiber_name}'. "
                f"Expected format: 'Fiber_<integer>' (e.g., 'Fiber_0')"
            ) from e

    def _parse_implanted_fibers(self, subject_id: str, data: Optional[dict] = None) -> tuple[Optional[List[int]], bool]:
        """Parse implanted fiber indices from procedures data.

        Determines which fibers were actually implanted during surgery.
        This prevents creating patch cord connections to non-existent implanted fibers.

        Parameters
        ----------
        subject_id : str
            Subject ID to query.
        data : Optional[dict], optional
            Pre-fetched procedures data. If None, will be fetched from service.

        Returns
        -------
        tuple[Optional[List[int]], bool]
            Tuple of (implanted_fiber_indices, procedures_fetched) where:
            - implanted_fiber_indices: List of implanted fiber indices
              (e.g., [0, 1, 2] for Fiber_0, Fiber_1, Fiber_2), or None if no implanted fibers found.
            - procedures_fetched: False if procedures data could not be retrieved, True otherwise.
        """
        if data is None:
            data = get_procedures(subject_id)
        if not data:
            return None, False

        implanted_indices = set()

        for subject_proc in data.get("subject_procedures", []):
            if subject_proc.get("object_type") == "Surgery":
                for proc in subject_proc.get("procedures", []):
                    if proc.get("object_type") == "Probe implant":
                        implanted_device = proc.get("implanted_device", {})
                        if implanted_device.get("object_type") == "Fiber probe":
                            fiber_name = implanted_device.get("name", "")
                            fiber_idx = self._extract_fiber_index(fiber_name)
                            implanted_indices.add(fiber_idx)

        if not implanted_indices:
            return None, True

        return sorted(implanted_indices), True

    def transform(
        self,
        metadata: dict,
        skip_validation: bool = False,
        intended_measurements: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
        implanted_fibers: Optional[List[int]] = None,
    ) -> Acquisition:
        """Transforms intermediate metadata into a complete Acquisition model.

        Parameters
        ----------
        metadata : dict
            Metadata extracted from FIP files via the extractor.
            Must conform to the ProtoAcquisitionDataSchema JSON schema.
        skip_validation : bool, optional
            If True, skip JSON schema validation (useful for testing). Defaults to False.
        intended_measurements : Optional[Dict[str, Dict[str, Optional[str]]]], optional
            Intended measurements data. If None, will be fetched from metadata service.
        implanted_fibers : Optional[List[int]], optional
            Implanted fiber indices. If None, will be fetched from metadata service.
            Must be non-empty after fetching.

        Returns
        -------
        Acquisition
            Fully composed acquisition model.

        Raises
        ------
        ValueError
            If metadata validation fails.
        """
        # Validate metadata against JSON schema unless skipped
        if not skip_validation:
            self._validate_fip_metadata(metadata)

        # Extract fields from nested structure
        session = metadata["session"]
        rig = metadata["rig"]
        data_streams = metadata["data_stream_metadata"]

        # Validate that ethics_review_id is not in session (it's a constant)
        if isinstance(session, dict) and "ethics_review_id" in session:
            raise ValueError(
                "ethics_review_id is a constant and should not be provided in the session metadata. "
                "It is automatically set from the FIP mapper constants."
            )

        subject_id = session["subject"]
        instrument_id = rig["rig_name"]

        # Get timing from all data streams (handle multiple epochs)
        # Find earliest start_time and latest end_time across all epochs
        start_times = [ensure_timezone(normalize_utc_timezone(ds["start_time"])) for ds in data_streams]
        end_times = [ensure_timezone(normalize_utc_timezone(ds["end_time"])) for ds in data_streams]

        earliest_start = min(start_times)
        latest_end = max(end_times)

        session_start_time, session_end_time = self._process_session_times(
            earliest_start,
            latest_end,
        )

        # Fetch intended measurements and implanted fibers from metadata service if not provided
        if intended_measurements is None:
            intended_measurements = self._parse_intended_measurements(subject_id)
        if implanted_fibers is None:
            # Fetch implanted fibers from metadata service
            implanted_fibers, procedures_fetched = self._parse_implanted_fibers(subject_id)

            # Check if procedures service call failed (distinct from finding no fibers)
            if not procedures_fetched:
                raise ValueError(
                    f"Failed to retrieve procedures data from metadata service for subject_id={subject_id}. "
                    "Cannot create FIP acquisition metadata without procedures information."
                )

            # Procedures were successfully retrieved, but no implanted fibers found in the data
            if not implanted_fibers:
                raise ValueError(
                    f"No implanted fibers found in procedures data for subject_id={subject_id}. "
                    "Implanted fiber information is required to create FIP acquisition metadata."
                )
        else:
            # implanted_fibers were provided by caller - validate they're not empty
            if not implanted_fibers:
                raise ValueError(
                    f"No implanted fibers found for subject_id={subject_id}. "
                    "Implanted fiber information is required to create FIP acquisition metadata."
                )

        # Get protocol URLs for FIP modality
        protocol_id = get_protocols_for_modality("fip") or None

        # Create code list from session commit hash
        code = None
        if session.get("commit_hash"):
            code = [Code(url=VR_FORAGING_FIP_REPO_URL, version=session["commit_hash"])]

        data_stream = DataStream(
            stream_start_time=session_start_time,
            stream_end_time=session_end_time,
            modalities=[Modality.FIB],
            code=code,
            active_devices=self._get_active_devices(rig, implanted_fibers),
            configurations=self._build_configurations(rig, implanted_fibers, intended_measurements),
            connections=self._build_connections(implanted_fibers),
        )

        acquisition = Acquisition(
            subject_id=subject_id,
            acquisition_start_time=session_start_time,
            acquisition_end_time=session_end_time,
            experimenters=session.get("experimenter", []),
            ethics_review_id=ETHICS_REVIEW_ID,
            instrument_id=instrument_id,
            acquisition_type=ACQUISITION_TYPE_AIND_VR_FORAGING,
            notes=session.get("notes"),
            data_streams=[data_stream],
            stimulus_epochs=[],
            subject_details=None,  # FIP data contract does not include subject details
            protocol_id=protocol_id,
        )

        return acquisition

    def _extract_camera_exposure_time(self, rig_config: Dict) -> float:
        """Extract camera exposure time from rig configuration.

        The FIP system stores camera exposure time in the light_source task data
        as 'delta_1' (in microseconds). This represents the camera integration time
        during each LED pulse cycle. All light sources should have the same delta_1
        value since the cameras are synchronized to the LED timing.

        Parameters
        ----------
        rig_config : Dict
            Rig configuration dictionary containing light source definitions.

        Returns
        -------
        float
            Camera exposure time in microseconds.

        Raises
        ------
        ValueError
            If delta_1 cannot be found in any light source configuration.

        Notes
        -----
        The delta values in the light source task represent LED timing:
        - delta_1: Camera exposure time (microseconds) - what we extract here
        - delta_2: Delay between LED pulse and camera trigger (microseconds)
        - delta_3: LED pulse width (microseconds)
        - delta_4: Additional timing parameter (microseconds)
        """
        # Find any light source with task data
        for key, value in rig_config.items():
            if key.startswith("light_source_") and isinstance(value, dict):
                task = value.get("task", {})
                if isinstance(task, dict) and "delta_1" in task:
                    delta_1 = task["delta_1"]
                    if isinstance(delta_1, (int, float)) and delta_1 > 0:
                        logger.info(f"Extracted camera exposure time: {delta_1} μs from {key}")
                        return float(delta_1)

        # If delta_1 not found, log warning and return default
        logger.warning(
            "Could not find delta_1 (camera exposure time) in any light_source configuration. "
            "Using default value of 10000 μs."
        )
        return 10000.0  # Default exposure time in microseconds

    def _get_camera_names_from_roi(self, roi_settings: Dict) -> Dict[str, str]:
        """Get camera device identifiers from ROI settings.

        Extracts camera config keys from ROI settings and transforms them to
        historical standard device names using DEVICE_NAME_MAP.

        Parameters
        ----------
        roi_settings : Dict
            ROI settings from rig configuration.

        Returns
        -------
        Dict[str, str]
            Dictionary mapping camera type to transformed device name.
            E.g., {"green": "Green CMOS", "red": "Red CMOS"}
        """
        camera_names = {}

        for roi_key in roi_settings.keys():
            if ROI_KEYWORD_ROI in roi_key and ROI_KEYWORD_BACKGROUND not in roi_key:
                # Extract camera key from roi_key (e.g., "camera_green_iso_roi" -> "camera_green_iso")
                camera_key = roi_key.replace(ROI_KEYWORD_ROI, "")

                # Determine camera type
                if ROI_KEYWORD_GREEN in camera_key or ROI_KEYWORD_ISO in camera_key:
                    camera_type = "green"
                elif ROI_KEYWORD_RED in camera_key:
                    camera_type = "red"
                else:
                    continue

                # Transform rig key to historical standard name
                device_name = DEVICE_NAME_MAP.get(camera_key, camera_key)
                camera_names[camera_type] = device_name

        return camera_names

    def _build_led_configs(self, rig_config: Dict) -> tuple:
        """Build LED configurations from rig config.

        Parameters
        ----------
        rig_config : Dict
            Rig configuration dictionary.

        Returns
        -------
        tuple
            (led_configs, led_configs_by_wavelength) where led_configs is a list
            and led_configs_by_wavelength is a dict mapping wavelength to config.
        """
        led_configs = []
        led_configs_by_wavelength = {}
        light_source_names = [name for name in rig_config.keys() if name.startswith("light_source_")]

        for light_source_name in light_source_names:
            light_source = rig_config[light_source_name]
            wavelength = self._get_led_wavelength(light_source_name.replace("light_source_", ""))

            # Transform rig key to historical standard name
            device_name = DEVICE_NAME_MAP.get(light_source_name, light_source_name)

            led_config = LightEmittingDiodeConfig(
                device_name=device_name,
                power=light_source.get("power", DEFAULT_LED_POWER),
                power_unit=PowerUnit.PERCENT,
            )
            led_configs.append(led_config)

            if wavelength:
                led_configs_by_wavelength[wavelength] = led_config

        return led_configs, led_configs_by_wavelength

    def _create_channel(
        self,
        fiber_idx: int,
        channel_type: str,
        led_config: Optional[LightEmittingDiodeConfig],
        intended_measurement: Optional[str],
        camera_name: str,
        emission_wavelength: int,
        exposure_time_ms: float,
    ) -> Channel:
        """Create a single channel configuration.

        Parameters
        ----------
        fiber_idx : int
            Fiber index.
        channel_type : str
            Channel type (Green, Isosbestic, Red).
        led_config : Optional[LightEmittingDiodeConfig]
            LED configuration for this channel.
        intended_measurement : Optional[str]
            Intended measurement for this channel.
        camera_name : str
            Camera device name.
        emission_wavelength : int
            Emission wavelength in nm.
        exposure_time_ms : float
            Camera exposure time in milliseconds.

        Returns
        -------
        Channel
            Channel configuration.
        """
        return Channel(
            channel_name=f"Fiber_{fiber_idx}_{channel_type}",
            intended_measurement=intended_measurement,
            detector=DetectorConfig(
                device_name=camera_name,
                exposure_time=exposure_time_ms,
                exposure_time_unit=TimeUnit.MS,
                trigger_type=TriggerType.INTERNAL,
                compression=FIP_CAMERA_COMPRESSION,
            ),
            light_sources=[led_config] if led_config else [],
            excitation_filters=[],
            emission_filters=[],
            emission_wavelength=emission_wavelength,
            emission_wavelength_unit=SizeUnit.NM,
        )

    def _build_configurations(
        self,
        rig_config: Dict[str, Any],
        implanted_fibers: List[int],
        intended_measurements: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
    ) -> List[Any]:
        """Build device configurations from rig config.

        Parameters
        ----------
        rig_config : Dict[str, Any]
            Rig configuration dictionary from metadata.
        intended_measurements : Optional[Dict[str, Dict[str, Optional[str]]]], optional
            Intended measurements from metadata service, mapping fiber names to
            channel measurements (R, G, B, Iso), by default None.
        implanted_fibers : List[int]
            List of implanted fiber indices from procedures endpoint. Creates
            patch cord configurations for these implanted fibers.

        Returns
        -------
        List[Any]
            List of device configurations (LEDs, detectors, and patch cords).
        """
        configurations = []

        # Extract camera exposure time from light source delta_1 field
        exposure_time_us = self._extract_camera_exposure_time(rig_config)
        # Convert microseconds to milliseconds for DetectorConfig
        exposure_time_ms = exposure_time_us / CAMERA_EXPOSURE_TIME_MICROSECONDS_PER_MILLISECOND

        # Build LED configs
        led_configs, led_configs_by_wavelength = self._build_led_configs(rig_config)
        configurations.extend(led_configs)

        # Build patch cord configurations
        # Each fiber index corresponds to: Patch Cord N → Fiber N (implant)
        # Patch Cord 0 → Fiber 0, Patch Cord 1 → Fiber 1, etc.
        #
        # Each fiber has 3 channels due to temporal multiplexing:
        #   1. Green: 470nm excitation, ~520nm emission, green camera
        #   2. Isosbestic: 415nm excitation, ~520nm emission, green camera (same detector!)
        #   3. Red: 565nm excitation, ~590nm emission, red camera
        roi_settings = rig_config.get("roi_settings", {})
        if roi_settings:
            # Get camera identifiers from ROI settings
            camera_names = self._get_camera_names_from_roi(roi_settings)
            green_camera_name = camera_names.get("green")
            red_camera_name = camera_names.get("red")

            # Use implanted fibers directly
            fiber_indices = implanted_fibers

            # Create patch cord for each implanted fiber
            for fiber_idx in fiber_indices:
                channels = []
                fiber_name = f"Fiber_{fiber_idx}"
                fiber_measurements = intended_measurements.get(fiber_name) if intended_measurements else None

                # Channel definitions: (channel_type, measurement_key, led_wavelength, camera_name, emission_wavelength)
                channel_defs = [
                    ("Green", "G", EXCITATION_BLUE, green_camera_name, EMISSION_GREEN),
                    ("Isosbestic", "Iso", EXCITATION_UV, green_camera_name, EMISSION_GREEN),
                    ("Red", "R", EXCITATION_YELLOW, red_camera_name, EMISSION_RED),
                ]

                for channel_type, measurement_key, led_wavelength, camera_name, emission_wavelength in channel_defs:
                    if camera_name:
                        measurement = fiber_measurements.get(measurement_key) if fiber_measurements else None
                        channels.append(
                            self._create_channel(
                                fiber_idx,
                                channel_type,
                                led_configs_by_wavelength.get(led_wavelength),
                                measurement,
                                camera_name,
                                emission_wavelength,
                                exposure_time_ms,
                            )
                        )

                # Create patch cord if we have channels
                if channels:
                    patch_cord = PatchCordConfig(
                        device_name=f"Patch Cord {fiber_idx}",
                        channels=channels,
                    )
                    configurations.append(patch_cord)

        return configurations

    def _get_led_wavelength(self, led_name: str) -> Optional[int]:
        """Get LED excitation wavelength based on LED name.

        FIP system uses 3 LEDs for excitation, each producing different emission:
        - UV LED (415nm excitation) → green emission (isosbestic control)
        - Blue LED (470nm excitation) → green emission (GFP signal)
        - Yellow/Lime LED (565nm excitation) → red emission (RFP signal)

        Parameters
        ----------
        led_name : str
            LED name from rig config key (e.g., "uv", "blue", "lime").

        Returns
        -------
        Optional[int]
            LED excitation wavelength in nm, or None if unknown.
        """
        led_lower = led_name.lower()
        if "uv" in led_lower:
            return EXCITATION_UV
        if "blue" in led_lower:
            return EXCITATION_BLUE
        if "lime" in led_lower or "yellow" in led_lower:
            return EXCITATION_YELLOW
        return None

    def _get_active_devices(
        self,
        rig_config: Dict[str, Any],
        implanted_fibers: List[int],
    ) -> List[str]:
        """Get list of active device names.

        Includes implanted fibers and patch cords based on procedures data.
        Each fiber index corresponds to: Patch Cord N → Fiber N (implant).

        Parameters
        ----------
        rig_config : Dict[str, Any]
            Rig configuration dictionary from metadata.
        implanted_fibers : List[int]
            List of implanted fiber indices from procedures endpoint.

        Returns
        -------
        List[str]
            List of active device names.
        """
        devices = []

        # Add LEDs - use rig keys and transform to historical standard names
        light_source_names = [name for name in rig_config.keys() if name.startswith("light_source_")]
        for light_source_name in light_source_names:
            device_name = DEVICE_NAME_MAP.get(light_source_name, light_source_name)
            devices.append(device_name)

        # Add cameras - use rig keys and transform to historical standard names
        camera_names = [name for name in rig_config.keys() if name.startswith("camera_")]
        for camera_name in camera_names:
            device_name = DEVICE_NAME_MAP.get(camera_name, camera_name)
            devices.append(device_name)

        # Add patch cords and implanted fibers
        fiber_indices = implanted_fibers

        for fiber_idx in fiber_indices:
            devices.append(f"Patch Cord {fiber_idx}")
            devices.append(f"Fiber {fiber_idx}")

        # Add controller
        if "cuttlefish_fip" in rig_config:
            cuttlefish_name = rig_config["cuttlefish_fip"].get("name")
            if cuttlefish_name:
                devices.append(cuttlefish_name)

        return devices

    def _build_connections(self, implanted_fibers: List[int]) -> List[Connection]:
        """Build connections between patch cords and implanted fibers.

        Creates Connection objects representing the physical connections
        between patch cords and fibers during the acquisition session.

        Parameters
        ----------
        implanted_fibers : List[int]
            List of implanted fiber indices from procedures endpoint.

        Returns
        -------
        List[Connection]
            List of Connection objects for each patch cord → fiber pair.
        """
        connections = []
        for fiber_idx in implanted_fibers:
            patch_cord_name = f"Patch Cord {fiber_idx}"
            fiber_name = f"Fiber {fiber_idx}"
            connections.append(
                Connection(
                    source_device=patch_cord_name,
                    target_device=fiber_name,
                    send_and_receive=False,
                )
            )
        return connections

    def _process_session_times(self, session_start_time, session_end_time):
        """Process and validate session times.

        Ensures both times have timezone info (using system local timezone if needed)
        and swaps them if they're in the wrong order.

        Parameters
        ----------
        session_start_time : datetime or str
            Session start time.
        session_end_time : datetime or str
            Session end time.

        Returns
        -------
        tuple[datetime, datetime]
            Processed start and end times with timezone info.
        """
        session_start_time = ensure_timezone(session_start_time)
        session_end_time = ensure_timezone(session_end_time)

        if session_start_time > session_end_time:
            session_start_time, session_end_time = (
                session_end_time,
                session_start_time,
            )

        return session_start_time, session_end_time

    def run_job(self, job_settings: MapperJobSettings) -> None:
        """Run the FIP mapping job.

        Reads fip.json from input_filepath, transforms it to acquisition format,
        and writes acquisition_fip.json to output_filepath.

        This method follows the standard MapperJob pattern required for automatic
        discovery and execution by GatherMetadataJob.

        Parameters
        ----------
        job_settings : MapperJobSettings
            Settings containing input_filepath and output_filepath.
        """
        # Read input file
        with open(job_settings.input_filepath, "r") as f:
            metadata = json.load(f)

        # Transform to acquisition
        acquisition = self.transform(metadata)

        filename_suffix = job_settings.output_filename_suffix

        acquisition.write_standard_file(output_directory=job_settings.output_directory, filename_suffix=filename_suffix)
