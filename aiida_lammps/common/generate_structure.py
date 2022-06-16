"""
Creation of the structure file content.

As allowing the users to create their lattices using LAMMPS' would be too
complex, one must ensure that the aiida StructureData is written to file in
a format that is compatible to LAMMPS.

In the case of non-orthogonal structures, this will take care of generating
a triclinic cell compatible with what LAMMPS expects.
"""
import typing

import numpy as np


def transform_cell(cell) -> typing.Union[np.array, np.array]:
    """Transform the cell to an orientation, compatible with LAMMPS

    LAMMPS requires the simulation cell to be in the format of a
    lower triangular matrix (right-handed basis).
    Therefore the cell and positions may require rotation and inversion.
    See https://lammps.sandia.gov/doc/Howto_triclinic.html

    :param cell: crystal cell of the original structure
    :returns: LAMMPS compatible cell, transformation between original and final cell
    :rtype: typing.Union[np.array, np.array]
    """
    cell = np.array(cell)
    transform, upper_tri = np.linalg.qr(cell.T, mode="complete")
    new_cell = np.transpose(upper_tri)

    # LAMMPS also requires positive values on the diagonal of the,
    # so invert cell if necessary
    inversion = np.eye(3)
    for entry in range(3):
        if new_cell[entry, entry] < 0.0:
            inversion[entry, entry] = -1.0
    new_cell = np.dot(inversion, new_cell.T).T
    transform = np.dot(transform, inversion.T).T

    return new_cell, transform


def generate_lammps_structure(
    structure,
    atom_style: str = "atomic",
    charge_dict: dict = None,
    round_dp: float = None,
    docstring: str = "generated by aiida_lammps",
) -> typing.Union[str, np.array]:
    """Create lammps input structure file content.

    :param structure: the structure to use in the simulation
    :type structure: orm.StructureData
    :param atom_style: treatment of the particles according to lammps, defaults to 'atomic'
    :type atom_style: str, optional
    :param charge_dict: dictionary with the charge for the particles, defaults to None
    :type charge_dict: dict, optional
    :param round_dp: precision to which to round the positions, defaults to None
    :type round_dp: float, optional
    :param docstring: header for the structure file, defaults to 'generated by aiida_lammps'
    :type docstring: str, optional
    :raises ValueError: if the atom_style does not belong to either 'atomic' or 'charge'
    :return: the structure file content, the transformation matrix applied to
        the structure cell and coordinates
    :rtype: typing.Union[str, np.array]
    """
    # pylint: disable=too-many-locals

    if atom_style not in ["atomic", "charge"]:
        raise ValueError(
            f"atom_style must be in ['atomic', 'charge'], not '{atom_style}'"
        )
    if charge_dict is None:
        charge_dict = {}

    # mapping of atom kind_name to id number
    kind_name_id_map = {}
    for site in structure.sites:
        if site.kind_name not in kind_name_id_map:
            kind_name_id_map[site.kind_name] = len(kind_name_id_map) + 1
    # mapping of atom kind_name to mass
    kind_mass_dict = {kind.name: kind.mass for kind in structure.kinds}

    filestring = ""
    filestring += f"# {docstring}\n\n"
    filestring += f"{len(structure.sites)} atoms\n"
    filestring += f"{len(kind_name_id_map)} atom types\n\n"

    atoms = structure.get_ase()
    cell, coord_transform = transform_cell(atoms.cell)
    positions = np.transpose(np.dot(coord_transform, np.transpose(atoms.positions)))

    if round_dp:
        cell = np.round(cell, round_dp) + 0.0
        positions = np.round(positions, round_dp) + 0.0

    filestring += f"0.0 {cell[0, 0]:20.10f} xlo xhi\n"
    filestring += f"0.0 {cell[1, 1]:20.10f} ylo yhi\n"
    filestring += f"0.0 {cell[2, 2]:20.10f} zlo zhi\n"
    filestring += (
        f"{cell[1, 0]:20.10f} {cell[2, 0]:20.10f} {cell[2, 1]:20.10f} xy xz yz\n\n"
    )

    filestring += "Masses\n\n"
    for kind_name in sorted(list(kind_name_id_map.keys())):
        filestring += (
            f"{kind_name_id_map[kind_name]} {kind_mass_dict[kind_name]:20.10f} \n"
        )
    filestring += "\n"

    filestring += "Atoms\n\n"

    for site_index, (pos, site) in enumerate(zip(positions, structure.sites)):

        kind_id = kind_name_id_map[site.kind_name]

        if atom_style == "atomic":
            filestring += f"{site_index + 1} {kind_id}"
            filestring += f" {pos[0]:20.10f} {pos[1]:20.10f} {pos[2]:20.10f}\n"
        if atom_style == "charge":
            charge = charge_dict.get(site.kind_name, 0.0)
            filestring += f"{site_index + 1} {kind_id} {charge}"
            filestring += f" {pos[0]:20.10f} {pos[1]:20.10f} {pos[2]:20.10f}\n"

    return filestring, coord_transform
