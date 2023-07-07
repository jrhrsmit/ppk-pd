import logging
from pathlib import Path
from typing import List
import typer


# local imports
from ppk_pd import PPK_PD
from library.library.components import Mounting_Hole, Faebryk_Logo
import library.lcsc


# function imports
from faebryk.exporters.netlist.kicad.netlist_kicad import from_faebryk_t2_netlist
from faebryk.exporters.netlist.netlist import make_t2_netlist_from_t1
from faebryk.exporters.netlist.graph import (
    make_graph_from_components,
    make_t1_netlist_from_graph,
)

from faebryk.library.core import Component
from faebryk.exporters.netlist.netlist import Component as NL_Component

from library.library.components import (
    Capacitor,
    Resistor,
    Inductor,
)
from faebryk.library.traits.component import (
    has_type_description,
)
from faebryk.library.trait_impl.component import has_overriden_name_defined
from faebryk.library.traits.component import has_overriden_name


# logging settings
#logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.INFO)
#logging.getLogger(library.lcsc.__name__).setLevel(logging.DEBUG)

from rich.logging import RichHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("rich")

def write_netlist(components: List[Component], path: Path) -> bool:
    graph = make_graph_from_components(components)
    t1 = make_t1_netlist_from_graph(graph)
    t2 = make_t2_netlist_from_t1(t1)

    extra_comps = [
        NL_Component(
            name=comp["name"],
            value=comp["value"],
            properties=comp["properties"],
        )
        for comp in t1
        if comp["real"]
    ]

    netlist = from_faebryk_t2_netlist(t2, extra_comps)

    if path.exists():
        old_netlist = path.read_text()
        # TODO this does not work!
        if old_netlist == netlist:
            return False
        backup_path = path.with_suffix(path.suffix + ".bak")
        logger.info(f"Backup old netlist at {backup_path}")
        backup_path.write_text(old_netlist)

    logger.info("Writing Experiment netlist to {}".format(path.resolve()))
    path.write_text(netlist, encoding="utf-8")

    return True


def set_designators(components: List[Component]) -> List[Component]:
    designator_number = {}
    for cmp in components:
        if isinstance(cmp, Capacitor):
            designator_prefix = "C"

        elif isinstance(cmp, Resistor):
            designator_prefix = "R"
        else:
            if cmp.has_trait(has_type_description):
                designator_prefix = cmp.get_trait(
                    has_type_description
                ).get_type_description()
            else:
                designator_prefix = "U"

        if designator_prefix not in designator_number:
            designator_number[designator_prefix] = 0
        else:
            designator_number[designator_prefix] += 1

        cmp.add_trait(
            has_overriden_name_defined(
                f"{designator_prefix}{designator_number[designator_prefix]:03d}"
            )
        )


def main(nonetlist: bool = False):
    # paths
    build_dir = Path("./build")
    faebryk_build_dir = build_dir.joinpath("faebryk")
    faebryk_build_dir.mkdir(parents=True, exist_ok=True)
    kicad_prj_path = Path(__file__).parent.parent.joinpath("kicad")
    netlist_path = kicad_prj_path.joinpath("main.net")

    # graph
    G = PPK_PD()
    # designators
    set_designators([G])
    # netlist
    write_netlist([G], netlist_path)


if __name__ == "__main__":
    typer.run(main)
