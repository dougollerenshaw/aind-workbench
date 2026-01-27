"""Module for creating Fiber Photometry session metadata.

This module implements an ETL (Extract, Transform, Load) pattern for generating
standardized session metadata from fiber photometry experiments. It handles:

- Extraction of session times from data files
- Transformation of raw data into standardized session objects
- Loading/saving of session metadata in a standard format

The ETL class provides hooks for future extension to fetch additional data from
external services or handle new data formats.
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd
from aind_data_schema.base import AindCoreModel
from aind_data_schema.core.session import (
    DetectorConfig,
    FiberConnectionConfig,
    LightEmittingDiodeConfig,
    Session,
    Stream,
)
from aind_data_schema_models.modalities import Modality

from aind_metadata_mapper.core import GenericEtl
from aind_metadata_mapper.core_models import JobResponse
from aind_metadata_mapper.fip.models import JobSettings
from aind_metadata_mapper.fip.utils import (
    extract_session_end_time_from_files,
    extract_session_start_time_from_files,
)
from aind_metadata_mapper.utils.timing_utils import (
    validate_session_temporal_consistency,
)


@dataclass
class FiberData:
    """Intermediate data model for fiber photometry data.

    This model holds the extracted and processed data before final
    transformation into a Session object. It serves as a structured
    intermediate representation of the fiber photometry session data.

    Parameters
    ----------
    start_time : datetime
        Session start time from fiber photometry files
    end_time : Optional[datetime]
        Session end time from fiber photometry files
    data_files : List[Path]
        List of paths to fiber photometry data files
    timestamps : List[float]
        List of timestamps from fiber photometry recordings
    light_source_configs : List[dict]
        List of light source configuration dictionaries
    detector_configs : List[dict]
        List of detector configuration dictionaries
    fiber_configs : List[dict]
        List of fiber configuration dictionaries
    subject_id : str
        Subject identifier
    experimenter_full_name : List[str]
        List of experimenter names
    rig_id : str
        Identifier for the experimental rig
    iacuc_protocol : str
        IACUC protocol number
    notes : str
        Additional notes about the session
    mouse_platform_name : str
        Name of the mouse platform used
    active_mouse_platform : bool
        Whether the mouse platform was active
    session_type : str
        Type of session (e.g. "FIB")
    anaesthesia : Optional[str]
        Anaesthesia used, if any
    animal_weight_post : Optional[float]
        Animal weight after session
    animal_weight_prior : Optional[float]
        Animal weight before session
    """

    start_time: datetime
    end_time: Optional[datetime]
    data_files: List[Path]
    timestamps: List[float]
    light_source_configs: List[dict]
    detector_configs: List[dict]
    fiber_configs: List[dict]
    subject_id: str
    experimenter_full_name: List[str]
    rig_id: str
    iacuc_protocol: str
    notes: str
    mouse_platform_name: str
    active_mouse_platform: bool
    session_type: str
    anaesthesia: Optional[str]
    animal_weight_post: Optional[float]
    animal_weight_prior: Optional[float]


class FIBEtl(GenericEtl[JobSettings]):
    """Creates fiber photometry session metadata using an ETL pattern.

    This class handles the full lifecycle of session metadata creation:
    - Extracting timing information from data files
    - Transforming raw data into standardized session objects
    - Loading/saving session metadata in a standard format

    The ETL process ensures that all required metadata fields are populated
    and validates the output against the AIND data schema.

    This class inherits from GenericEtl which provides the _load method
    for writing session metadata to a JSON file using a standard filename
    format (session_fip.json).
    """

    def __init__(self, job_settings: Union[str, JobSettings]):
        """Initialize ETL with job settings.

        Parameters
        ----------
        job_settings : Union[str, JobSettings]
            Either a JobSettings object or a JSON string that can
            be parsed into one. The settings define all required parameters
            for the session metadata, including experimenter info, subject
            ID, data paths, etc.

        Raises
        ------
        ValidationError
            If the provided settings fail schema validation
        JSONDecodeError
            If job_settings is a string but not valid JSON
        """
        if isinstance(job_settings, str):
            job_settings = JobSettings(**json.loads(job_settings))
        super().__init__(job_settings)

    def _extract(self) -> FiberData:
        """Extract metadata and raw data from fiber photometry files.

        This method parses the raw data files to create an
        intermediate data model containing all necessary
        information for creating a Session object.

        Returns
        -------
        FiberData
            Intermediate data model containing parsed file data and metadata
        """
        settings = self.job_settings
        data_dir = Path(settings.data_directory)

        data_files = list(data_dir.glob("FIP_Data*.csv"))
        local_timezone = settings.local_timezone
        start_time = extract_session_start_time_from_files(
            data_dir, local_timezone
        )
        end_time = (
            extract_session_end_time_from_files(
                data_dir, start_time, local_timezone
            )
            if start_time
            else None
        )

        timestamps = []
        for file in data_files:
            df = pd.read_csv(file, header=None)
            timestamps.extend(df[0].tolist())

        stream_data = settings.data_streams[0]

        return FiberData(
            start_time=start_time,
            end_time=end_time,
            data_files=data_files,
            timestamps=timestamps,
            light_source_configs=stream_data["light_sources"],
            detector_configs=stream_data["detectors"],
            fiber_configs=stream_data["fiber_connections"],
            subject_id=settings.subject_id,
            experimenter_full_name=settings.experimenter_full_name,
            rig_id=settings.rig_id,
            iacuc_protocol=settings.iacuc_protocol,
            notes=settings.notes,
            mouse_platform_name=settings.mouse_platform_name,
            active_mouse_platform=settings.active_mouse_platform,
            session_type=settings.session_type,
            anaesthesia=settings.anaesthesia,
            animal_weight_post=settings.animal_weight_post,
            animal_weight_prior=settings.animal_weight_prior,
        )

    def _transform(self, fiber_data: FiberData) -> Session:
        """Transform extracted data into a valid Session object.

        Parameters
        ----------
        fiber_data : FiberData
            Intermediate data model containing parsed file data and metadata

        Returns
        -------
        Session
            A fully configured Session object that
            conforms to the AIND data schema
        """
        stream = Stream(
            stream_start_time=fiber_data.start_time,
            stream_end_time=fiber_data.end_time,
            light_sources=[
                LightEmittingDiodeConfig(**ls)
                for ls in fiber_data.light_source_configs
            ],
            stream_modalities=[Modality.FIB],
            detectors=[
                DetectorConfig(**d) for d in fiber_data.detector_configs
            ],
            fiber_connections=[
                FiberConnectionConfig(**fc) for fc in fiber_data.fiber_configs
            ],
        )

        session = Session(
            experimenter_full_name=fiber_data.experimenter_full_name,
            session_start_time=fiber_data.start_time,
            session_end_time=fiber_data.end_time,
            session_type=fiber_data.session_type,
            rig_id=fiber_data.rig_id,
            subject_id=fiber_data.subject_id,
            iacuc_protocol=fiber_data.iacuc_protocol,
            notes=fiber_data.notes,
            data_streams=[stream],
            mouse_platform_name=fiber_data.mouse_platform_name,
            active_mouse_platform=fiber_data.active_mouse_platform,
            anaesthesia=fiber_data.anaesthesia,
            animal_weight_post=fiber_data.animal_weight_post,
            animal_weight_prior=fiber_data.animal_weight_prior,
        )

        # Validate temporal consistency (end time > start time)
        validate_session_temporal_consistency(session)

        return session

    def _load(
        self, output_model: AindCoreModel, output_directory: Optional[Path]
    ) -> JobResponse:
        """Override parent _load to handle custom
        filenames and default directories.

        This implementation differs from the parent GenericEtl._load
        in that it:
        1. Uses the filename specified in job_settings rather
        than model's default
        2. Falls back to data_directory if no output_directory specified
        3. Maintains validation and error handling from parent class

        Parameters
        ----------
        output_model : AindCoreModel
            The final model that has been constructed and validated
        output_directory : Optional[Path]
            Directory where the file should be written. If None,
            defaults to job_settings.data_directory

        Returns
        -------
        JobResponse
            Object containing status code, message, and optional data.
            Status codes:
            - 200: Success
            - 500: File writing errors
        """
        # If no output directory specified, use the data directory
        if output_directory is None:
            output_directory = Path(self.job_settings.data_directory)

        output_path = output_directory / self.job_settings.output_filename
        with open(output_path, "w") as f:
            f.write(output_model.model_dump_json(indent=3))
        return JobResponse(
            status_code=200, message=f"Write model to {output_path}"
        )

    def run_job(self) -> JobResponse:
        """Run the complete ETL job and return a JobResponse.

        This method orchestrates the full ETL process:
        1. Extracts metadata from files and settings
        2. Transforms the data into a valid Session object
        3. Saves the session metadata to the specified output location
        4. Verifies the output file was written correctly

        Returns
        -------
        JobResponse
            Object containing status code, message, and optional data.
            Status codes:
            - 200: Success
            - 406: Validation errors
            - 500: File writing errors

        Notes
        -----
        Uses the parent class's _load method which
        handles validation and writing.
        """
        fiber_data = self._extract()
        transformed_session = self._transform(fiber_data)
        job_response = self._load(
            transformed_session, self.job_settings.output_directory
        )
        return job_response


if __name__ == "__main__":
    sys_args = sys.argv[1:]
    main_job_settings = JobSettings.from_args(sys_args)
    etl = FIBEtl(job_settings=main_job_settings)
    etl.run_job()
