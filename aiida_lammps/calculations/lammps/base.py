"""
A basic plugin for performing calculations in ``LAMMPS`` using aiida.

The plugin will take the input parameters validate them against a schema
and then use them to generate the ``LAMMPS`` input file. The input file
is generated depending on the parameters provided, the type of potential,
the input structure and whether or not a restart file is provided.
"""
from aiida import orm
from aiida.common import datastructures
from aiida.engine import CalcJob

from aiida_lammps.common.generate_structure import generate_lammps_structure
from aiida_lammps.common.input_generator import generate_input_file
from aiida_lammps.data.lammps_potential import LammpsPotentialData
from aiida_lammps.data.trajectory import LammpsTrajectory


class BaseLammpsCalculation(CalcJob):
    """
    A basic plugin for performing calculations in ``LAMMPS`` using aiida.

    The plugin will take the input parameters validate them against a schema
    and then use them to generate the ``LAMMPS`` input file. The input file
    is generated depending on the parameters provided, the type of potential,
    the input structure and whether or not a restart file is provided.
    """

    _INPUT_FILENAME = "input.in"
    _STRUCTURE_FILENAME = "structure.dat"

    _DEFAULT_LOGFILE_FILENAME = "log.lammps"
    _DEFAULT_OUTPUT_FILENAME = "lammps_output"
    _DEFAULT_TRAJECTORY_FILENAME = "aiida_lammps.trajectory.dump"
    _DEFAULT_VARIABLES_FILENAME = "aiida_lammps.yaml"
    _DEFAULT_RESTART_FILENAME = "lammps.restart"
    _DEFAULT_POTENTIAL_FILENAME = "potential.dat"
    _DEFAULT_READ_RESTART_FILENAME = "aiida_lammps.restart"

    _DEFAULT_PARSER = "lammps.base"

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input(
            "script",
            valid_type=orm.SinglefileData,
            required=False,
            help="Complete input script to use. If specified, `structure`, `potential` and `parameters` are ignored.",
        )
        spec.input(
            "structure",
            valid_type=orm.StructureData,
            required=False,
            help="Structure used in the ``LAMMPS`` calculation",
        )
        spec.input(
            "potential",
            valid_type=LammpsPotentialData,
            required=False,
            help="Potential used in the ``LAMMPS`` calculation",
        )
        spec.input(
            "parameters",
            valid_type=orm.Dict,
            required=False,
            help="Parameters that control the ``LAMMPS`` calculation",
        )
        spec.input(
            "input_restartfile",
            valid_type=orm.SinglefileData,
            required=False,
            help="Input restartfile to continue from a previous ``LAMMPS`` calculation",
        )
        spec.input(
            "parent_folder",
            valid_type=orm.RemoteData,
            required=False,
            help="An optional working directory of a previously completed calculation to restart from.",
        )
        spec.input(
            "metadata.options.input_filename",
            valid_type=str,
            default=cls._INPUT_FILENAME,
        )
        spec.input(
            "metadata.options.structure_filename",
            valid_type=str,
            default=cls._STRUCTURE_FILENAME,
        )
        spec.input(
            "metadata.options.output_filename",
            valid_type=str,
            default=cls._DEFAULT_OUTPUT_FILENAME,
        )
        spec.input(
            "metadata.options.logfile_filename",
            valid_type=str,
            default=cls._DEFAULT_LOGFILE_FILENAME,
        )
        spec.input(
            "metadata.options.variables_filename",
            valid_type=str,
            default=cls._DEFAULT_VARIABLES_FILENAME,
        )
        spec.input(
            "metadata.options.trajectory_filename",
            valid_type=str,
            default=cls._DEFAULT_TRAJECTORY_FILENAME,
        )
        spec.input(
            "metadata.options.restart_filename",
            valid_type=str,
            default=cls._DEFAULT_RESTART_FILENAME,
        )
        spec.inputs["metadata"]["options"]["parser_name"].default = cls._DEFAULT_PARSER
        spec.inputs.validator = cls.validate_inputs

        spec.output(
            "results",
            valid_type=orm.Dict,
            required=True,
            help="The data extracted from the lammps log file",
        )
        spec.output(
            "trajectories",
            valid_type=LammpsTrajectory,
            required=True,
            help="The data extracted from the lammps trajectory file",
        )
        spec.output(
            "time_dependent_computes",
            valid_type=orm.ArrayData,
            required=True,
            help="The data with the time dependent computes parsed from the lammps.log",
        )
        spec.output(
            "restartfile",
            valid_type=orm.SinglefileData,
            required=False,
            help="The restartfile of a ``LAMMPS`` calculation",
        )
        spec.output(
            "structure",
            valid_type=orm.StructureData,
            required=False,
            help="The output structure.",
        )
        spec.exit_code(
            350,
            "ERROR_NO_RETRIEVED_FOLDER",
            message="the retrieved folder data node could not be accessed.",
            invalidates_cache=True,
        )
        spec.exit_code(
            351,
            "ERROR_LOG_FILE_MISSING",
            message="the file with the lammps log was not found",
            invalidates_cache=True,
        )
        spec.exit_code(
            352,
            "ERROR_FINAL_VARIABLE_FILE_MISSING",
            message="the file with the final variables was not found",
            invalidates_cache=True,
        )
        spec.exit_code(
            353,
            "ERROR_TRAJECTORY_FILE_MISSING",
            message="the file with the trajectories was not found",
            invalidates_cache=True,
        )
        spec.exit_code(
            354,
            "ERROR_STDOUT_FILE_MISSING",
            message="the stdout output file was not found",
        )
        spec.exit_code(
            355,
            "ERROR_STDERR_FILE_MISSING",
            message="the stderr output file was not found",
        )
        spec.exit_code(
            356,
            "ERROR_RESTART_FILE_MISSING",
            message="the file with the restart information was not found",
        )
        spec.exit_code(
            357,
            "ERROR_CALCULATION_DID_NOT_FINISH",
            message="The calculation did not finish properly but an intermediate restartfile was found",
        )
        spec.exit_code(
            1001,
            "ERROR_PARSING_LOGFILE",
            message="error parsing the log file has failed.",
        )
        spec.exit_code(
            1002,
            "ERROR_PARSING_FINAL_VARIABLES",
            message="error parsing the final variable file has failed.",
        )

    @classmethod
    def validate_inputs(cls, value, ctx):
        """Validate the top-level inputs namespace."""
        if "script" not in value and any(
            key not in value for key in ("structure", "potential", "parameters")
        ):
            return (
                "Unless `script` is specified the inputs `structure`, `potential` and "
                "`parameters` have to be specified."
            )

    def prepare_for_submission(self, folder):
        """
        Create the input files from the input nodes passed to this instance of the `CalcJob`.
        """
        # pylint: disable=too-many-locals

        # Get the name of the trajectory file
        _trajectory_filename = self.inputs.metadata.options.trajectory_filename

        # Get the name of the variables file
        _variables_filename = self.inputs.metadata.options.variables_filename

        # Get the name of the restart file
        _restart_filename = self.inputs.metadata.options.restart_filename

        # Get the name of the output file
        _output_filename = self.inputs.metadata.options.output_filename

        # Get the name of the logfile file
        _logfile_filename = self.inputs.metadata.options.logfile_filename

        # If there is a restartfile set its name to the input variables and
        # write it in the remote folder
        if "input_restartfile" in self.inputs:
            _read_restart_filename = self._DEFAULT_READ_RESTART_FILENAME
            with folder.open(_read_restart_filename, "wb") as handle:
                handle.write(self.inputs.input_restartfile.get_content())
        else:
            _read_restart_filename = None

        if "script" in self.inputs:
            input_filecontent = self.inputs.script.get_content()
            _parameters = {}
        else:
            # Get the parameters dictionary so that they can be used for creating
            # the input file
            _parameters = self.inputs.parameters.get_dict()

            # Generate the content of the structure file based on the input
            # structure
            structure_filecontent, _ = generate_lammps_structure(
                self.inputs.structure,
                self.inputs.potential.atom_style,
            )

            # Get the name of the structure file and write it to the remote folder
            _structure_filename = self.inputs.metadata.options.structure_filename

            with folder.open(_structure_filename, "w") as handle:
                handle.write(structure_filecontent)

            # Write the potential to the remote folder
            with folder.open(self._DEFAULT_POTENTIAL_FILENAME, "w") as handle:
                handle.write(self.inputs.potential.get_content())

            # Write the input file content. This function will also check the
            # sanity of the passed paremters when comparing it to a schema
            input_filecontent = generate_input_file(
                potential=self.inputs.potential,
                structure=self.inputs.structure,
                parameters=_parameters,
                restart_filename=_restart_filename,
                trajectory_filename=_trajectory_filename,
                variables_filename=_variables_filename,
                read_restart_filename=_read_restart_filename,
            )

        # Get the name of the input file, and write it to the remote folder
        _input_filename = self.inputs.metadata.options.input_filename

        with folder.open(_input_filename, "w") as handle:
            handle.write(input_filecontent)

        codeinfo = datastructures.CodeInfo()
        # Command line variables to ensure that the input file from LAMMPS can
        # be read
        codeinfo.cmdline_params = ["-in", _input_filename, "-log", _logfile_filename]
        # Set the code uuid
        codeinfo.code_uuid = self.inputs.code.uuid
        # Set the name of the stdout
        codeinfo.stdout_name = _output_filename

        # Generate the datastructure for the calculation information
        calcinfo = datastructures.CalcInfo()
        calcinfo.uuid = str(self.uuid)

        # Define the list of temporary files that will be retrieved
        calcinfo.retrieve_temporary_list = []
        # Set the files that must be retrieved
        calcinfo.retrieve_list = []
        calcinfo.retrieve_list.append(_output_filename)
        calcinfo.retrieve_list.append(_logfile_filename)
        calcinfo.retrieve_list.append(_variables_filename)
        calcinfo.retrieve_list.append(_trajectory_filename)
        # Add the restart file to the list of files to be retrieved if we want to store it in the database
        if "restart" in _parameters:
            if _parameters.get("restart", {}).get("print_final", False):
                calcinfo.retrieve_list.append(_restart_filename)
            if _parameters.get("restart", {}).get("print_intermediate", False):
                calcinfo.retrieve_temporary_list.append(
                    (f"{_restart_filename}*", ".", None)
                )

        # Set the information of the code into the calculation datastructure
        calcinfo.codes_info = [codeinfo]

        return calcinfo
