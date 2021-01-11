"""Write component Sparameters with FDTD Lumerical simulations.
"""

import json
from collections import namedtuple
from pathlib import PosixPath
from typing import Any, Dict, List, Tuple, Union

import gdspy
import numpy as np
import omegaconf
import yaml
from omegaconf import OmegaConf

import pp
from pp.component import Component
from pp.config import __version__
from pp.layers import layer2material, layer2nm, layer2swa
from pp.sp.get_sparameters_path import get_sparameters_path

run_false_warning = """
you need to pass `run=True` flag to run the simulation
To debug, you can create a lumerical FDTD session and pass it to the simulator

```
import lumapi
s = lumapi.FDTD()

import pp
c = pp.c.waveguide() # or whatever you want to simulate
pp.sp.write(component=c, run=False, session=s)
```
"""

materials = {
    "si": "Si (Silicon) - Palik",
    "sio2": "SiO2 (Glass) - Palik",
    "sin": "Si3N4 (Silicon Nitride) - Phillip",
}


default_simulation_settings = dict(
    layer2nm=layer2nm,
    layer2swa=layer2swa,
    layer2material=layer2material,
    remove_layers=[pp.LAYER.WGCLAD],
    background_material="sio2",
    port_width=3e-6,
    port_height=1.5e-6,
    port_extension_um=1,
    mesh_accuracy=2,
    zmargin=1e-6,
    ymargin=2e-6,
    wavelength_start=1.2e-6,
    wavelength_stop=1.6e-6,
    wavelength_points=500,
)


def clean_dict(
    d: Dict[str, Any], layers: List[Tuple[int, int]]
) -> Dict[str, Union[str, float, int]]:
    """Returns same dict after converting tuple keys into list of strings."""
    d["layer2nm"] = [
        f"{k[0]}_{k[1]}_{v}" for k, v in d.get("layer2nm", {}).items() if k in layers
    ]
    d["layer2swa"] = [
        f"{k[0]}_{k[1]}_{v}" for k, v in d.get("layer2swa", {}).items() if k in layers
    ]
    d["layer2material"] = [
        f"{k[0]}_{k[1]}_{v}"
        for k, v in d.get("layer2material", {}).items()
        if k in layers
    ]
    d["remove_layers"] = [f"{k[0]}_{k[1]}" for k in d.get("remove_layers", [])]
    return d


def write(
    component: Component,
    session: bool = None,
    run: bool = True,
    overwrite: bool = False,
    dirpath: PosixPath = pp.CONFIG["sp"],
    **settings,
):
    """Write Sparameters from a gdsfactory component using Lumerical FDTD.

    Args:
        component: gdsfactory Component
        session: you can pass a session=lumapi.FDTD() for debugging
        run: True-> runs Lumerical , False -> only draws simulation
        overwrite: run even if simulation results already exists
        dirpath: where to store the simulations
        layer2nm: dict of GDSlayer to thickness (nm) {(1, 0): 220}
        layer2swa: dict of {(1, 0): 90.0} - sidewall angles for GDS layers
        layer2material: dict of {(1, 0): "si"}
        remove_layers: list of tuples (layers to remove)
        background_material: for the background
        port_width: port width (m)
        port_height: port height (m)
        port_extension_um: port extension (um)
        mesh_accuracy: 2 (1: coarse, 2: fine, 3: superfine)
        zmargin: for the FDTD region 1e-6 (m)
        ymargin: for the FDTD region 2e-6 (m)
        wavelength_start: 1.2e-6 (m)
        wavelength_stop: 1.6e-6 (m)
        wavelength_points: 500

    Return:
        results: dict(wavelength_nm, S11, S12 ...) after simulation, or if simulation exists and returns the Sparameters directly
    """
    sim_settings = default_simulation_settings

    if hasattr(component, "simulation_settings"):
        sim_settings.update(component.simulation_settings)
    for setting in sim_settings.keys():
        assert (
            setting in sim_settings
        ), f"`{setting}` is not a valid setting ({list(sim_settings.keys())})"

    sim_settings.update(**settings)

    # easier to access dict in a namedtuple `ss.port_width`
    ss = namedtuple("sim_settings", sim_settings.keys())(*sim_settings.values())

    assert ss.port_width < 5e-6
    assert ss.port_height < 5e-6
    assert ss.zmargin < 5e-6
    assert ss.ymargin < 5e-6

    ports = component.ports

    component.remove_layers(ss.remove_layers)
    component._bb_valid = False

    c = pp.extend_ports(component=component, length=ss.port_extension_um)
    gdspath = pp.write_gds(c)

    filepath = get_sparameters_path(
        component=component,
        dirpath=dirpath,
        layer2material=ss.layer2material,
        layer2nm=ss.layer2nm,
    )
    filepath_json = filepath.with_suffix(".json")
    filepath_sim_settings = filepath.with_suffix(".yml")
    filepath_fsp = filepath.with_suffix(".fsp")

    if run and filepath_json.exists() and not overwrite:
        return json.loads(open(filepath_json).read())

    if not run and session is None:
        print(run_false_warning)

    pe = ss.port_extension_um * 1e-6 / 2
    port_locations = np.stack([p.midpoint for p in ports.values()], 0)
    x_min = port_locations[:, 0].min() * 1e-6 - pe
    x_max = port_locations[:, 0].max() * 1e-6 + pe
    y_min = port_locations[:, 1].min() * 1e-6 - pe
    y_max = port_locations[:, 1].max() * 1e-6 + pe

    z = 0
    z_span = 2 * ss.zmargin + max(ss.layer2nm.values()) * 1e-9

    layers = component.get_layers()
    sim_settings = OmegaConf.create(
        dict(
            simulation_settings=clean_dict(sim_settings, layers=layers),
            component=component.get_settings(),
            version=__version__,
        )
    )

    # Uncomment to debug
    # filepath_sim_settings.write_text(OmegaConf.to_yaml(sim_settings))
    # print(filepath_sim_settings)
    # return

    try:
        import lumapi
    except ModuleNotFoundError as e:
        print(
            "Cannot import lumapi (Python Lumerical API). "
            "You can add set the PYTHONPATH variable or add it with `sys.path.append()`"
        )
        raise e
    except OSError as e:
        raise e

    s = session or lumapi.FDTD(hide=False)
    s.newproject()
    s.selectall()
    s.deleteall()
    s.addrect(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z=z,
        z_span=z_span,
        index=1.5,
        name="clad",
    )

    material = ss.background_material
    if material not in materials:
        raise ValueError(f"{material} not in {list(materials.keys())}")
    material = materials[material]
    s.setnamed("clad", "material", material)

    s.addfdtd(
        dimension="3D",
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z=z,
        z_span=z_span,
        simulation_time=5e-12,
        mesh_accuracy=ss.mesh_accuracy,
        use_early_shutoff=True,
        auto_shutoff_min=1e-4,
    )

    for layer, nm in ss.layer2nm.items():
        if layer not in layers:
            continue
        assert layer in ss.layer2material, f"{layer} not in {ss.layer2material.keys()}"

        material = ss.layer2material[layer]
        if material not in materials:
            raise ValueError(f"{material} not in {list(materials.keys())}")
        material = materials[material]

        # merge polygons (necessary before extrusion with swa != 90 degrees)
        lib = gdspy.GdsLibrary(infile=gdspath)
        for cell in lib.top_level():
            _cell = gdspy.Cell(cell.name, exclude_from_current=True)
            _cell.add(
                gdspy.boolean(
                    cell,
                    None,
                    "or",
                    layer=layer[0],
                    datatype=layer[1],
                    max_points=1000000,
                )
            )
            lib.add(_cell, overwrite_duplicate=True)
        lib.write_gds(gdspath)

        s.gdsimport(str(gdspath), c.name, f"{layer[0]}:{layer[1]}")
        silicon = f"GDS_LAYER_{layer[0]}:{layer[1]}"
        s.setnamed(silicon, "z span", nm * 1e-9)
        s.setnamed(silicon, "material", material)
        s.setnamed(
            silicon, "script", "selectall;\nset('material',%material%);"
        )  # disable part of script for GDS poly group

        _extrude_gds_polygons(s, silicon, ss.layer2swa.get(layer, 90.0))

    for i, port in enumerate(ports.values()):
        s.addport()
        p = f"FDTD::ports::port {i+1}"
        s.setnamed(p, "x", port.x * 1e-6)
        s.setnamed(p, "y", port.y * 1e-6)
        s.setnamed(p, "z span", ss.port_height)

        deg = int(port.orientation) % 360
        # assert port.orientation in [0, 90, 180, 270], f"{port.orientation} needs to be [0, 90, 180, 270]"
        if (0 <= deg < 45) or (270 + 45 <= deg < 360):
            direction = "Backward"
            injection_axis = "x-axis"
            dxp = 0
            dyp = ss.port_width
        elif 45 <= deg < 90 + 45:
            direction = "Backward"
            injection_axis = "y-axis"
            dxp = ss.port_width
            dyp = 0
        elif 90 + 45 <= deg < 180 + 45:
            direction = "Forward"
            injection_axis = "x-axis"
            dxp = 0
            dyp = ss.port_width
        elif 180 + 45 <= deg < 270 + 45:
            direction = "Forward"
            injection_axis = "y-axis"
            dxp = ss.port_width
            dyp = 0
        else:
            raise ValueError(
                f"port {port.name} with orientation {port.orientation} is not a valid"
                " number "
            )

        s.setnamed(p, "direction", direction)
        s.setnamed(p, "injection axis", injection_axis)
        s.setnamed(p, "y span", dyp)
        s.setnamed(p, "x span", dxp)
        # s.setnamed(p, "theta", deg)
        s.setnamed(p, "name", port.name)

    s.setglobalsource("wavelength start", ss.wavelength_start)
    s.setglobalsource("wavelength stop", ss.wavelength_stop)
    s.setnamed("FDTD::ports", "monitor frequency points", ss.wavelength_points)

    if run:
        s.save(str(filepath_fsp))
        s.deletesweep("s-parameter sweep")

        s.addsweep(3)
        s.setsweep("s-parameter sweep", "Excite all ports", 0)
        s.setsweep("s-parameter sweep", "auto symmetry", 1)
        s.runsweep("s-parameter sweep")

        # collect results
        # S_matrix = s.getsweepresult("s-parameter sweep", "S matrix")
        sp = s.getsweepresult("s-parameter sweep", "S parameters")

        # export S-parameter data to file named s_params.dat to be loaded in
        # INTERCONNECT
        s.exportsweep("s-parameter sweep", str(filepath))
        print(f"wrote sparameters to {filepath}")

        keys = [key for key in sp.keys() if key.startswith("S")]
        ra = {f"{key}a": list(np.unwrap(np.angle(sp[key].flatten()))) for key in keys}
        rm = {f"{key}m": list(np.abs(sp[key].flatten())) for key in keys}

        results = {"wavelength_nm": list(sp["lambda"].flatten() * 1e9)}
        results.update(ra)
        results.update(rm)

        filepath_json.write_text(json.dumps(results))
        filepath_sim_settings.write_text(yaml.dump(_omegaconf2dict(sim_settings)))
        return results


def _omegaconf2dict(conf):
    if isinstance(conf, (omegaconf.DictConfig, dict)):
        return {k: _omegaconf2dict(v) for k, v in conf.items()}
    elif isinstance(conf, (omegaconf.ListConfig, list, tuple)):
        return [_omegaconf2dict(v) for v in conf]
    else:
        return conf


def _extrude_gds_polygons(session, name, sidewall_angle=80.0, dz=10e-9):
    if (90.0 - sidewall_angle) < 1e-3:
        return
    num_polys = int(session.getnamednumber(f"{name}::poly"))
    for i in range(1, num_polys + 1):
        session.setnamed(f"{name}::poly", "name", f"poly{i}", 1)
    for i in range(1, num_polys + 1):
        session.select(f"{name}::poly{i}")
        # we could do the following with the lumerical python api,
        # but it's somehow quite a bit faster like this:
        # original code from https://support.lumerical.com/hc/en-us/articles/360034382334-Tips-for-adding-sidewall-angles-to-simulation-objects
        session.eval(
            f"""
        dz = {dz};
        sidewall_angle = {sidewall_angle};
        V = get("vertices");
        z1 = get("z min");
        z2 = get("z max");
        num_vertices= length(V)/2;
        num_steps = round((z2-z1)/dz);
        if(num_steps < 2) {{ num_steps = 2; }}
        tempVx = pinch(V,2,1);
        tempVy = pinch(V,2,2);
        x0 = sum(tempVx)/num_vertices;
        y0 = sum(tempVy)/num_vertices;
        r0 = sum( sqrt(((tempVx-x0)^2 + (tempVy-y0)^2)) )/num_vertices;
        for(j=1:num_steps) {{
            scale_factor = ( r0 + (j-1/2)*(z2-z1)/num_steps/tan(sidewall_angle*pi/180) )/r0;
            tempVx = (pinch(V,2,1)-x0)*scale_factor + x0;
            tempVy = (pinch(V,2,2)-y0)*scale_factor + y0;
            tempV = V;
            tempV(1:num_vertices,1) = tempVx;
            tempV(1:num_vertices,2) = tempVy;
            if(j > 1) {{ copy(0,0,0); }}
            set("z min",z2-j*(z2-z1)/num_steps);
            set("z max",z2-(j-1)*(z2-z1)/num_steps);
            set("vertices",tempV);
        }}
        """
        )


def sample_write_coupler_ring():
    """Sample on how to write a sweep of Sparameters."""
    [
        write(
            pp.c.coupler_ring(
                wg_width=wg_width, length_x=length_x, bend_radius=bend_radius, gap=gap
            )
            for wg_width in [0.5]
            for length_x in [0.1, 1, 2, 3, 4]
            for gap in [0.15, 0.2]
            for bend_radius in [5, 10]
        )
    ]


if __name__ == "__main__":
    # c = pp.c.coupler_ring(length_x=3)
    c = pp.c.mmi1x2()
    r = write(component=c, layer2nm={(1, 0): 200})
    print(r)
    # print(r.keys())
    # print(c.ports.keys())
