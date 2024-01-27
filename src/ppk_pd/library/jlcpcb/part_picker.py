import logging

# Project library imports
import faebryk.libs.picker.lcsc as lcsc
from faebryk.core.core import Module

# Faebryk library imports
# Faebryk function imports
from faebryk.core.util import get_all_nodes
from faebryk.library.Capacitor import Capacitor
from faebryk.library.Constant import Constant
from faebryk.library.MOSFET import MOSFET
from faebryk.library.Resistor import Resistor
from library.jlcpcb.auto_pinmapping import (
    auto_pinmapping,
)
from library.jlcpcb.capacitor_search import find_capacitor
from library.jlcpcb.inductor_search import find_inductor
from library.jlcpcb.mosfet_search import find_mosfet
from library.jlcpcb.resistor_search import find_resistor
from library.jlcpcb.util import (
    get_value_from_pn,
    jlcpcb_db,
    si_to_float,
)
from library.library.components import (
    Faebryk_Logo,
    Fuse,
    Inductor,
    Mounting_Hole,
    Pin_Header,
)

log = logging.getLogger("local_library")


def pick_mosfet(db, cmp: MOSFET):
    lcsc_pn = find_mosfet(db, cmp)
    auto_pinmapping(component=cmp, partno=lcsc_pn)
    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_resistor(db, cmp: Resistor):
    lcsc_pn = find_resistor(db, cmp)

    value = get_value_from_pn(lcsc_pn)
    value_flt = si_to_float(value.strip("Ω"))
    cmp.set_resistance(Constant(value_flt))

    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_capacitor(db, cmp: Capacitor):
    lcsc_pn = find_capacitor(db, cmp)

    value = get_value_from_pn(lcsc_pn)
    value_flt = si_to_float(value.strip("F").replace("u", "µ"))
    cmp.set_capacitance(Constant(value_flt))

    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_inductor(db, cmp: Inductor):
    lcsc_pn = find_inductor(db, cmp)

    value = get_value_from_pn(lcsc_pn)
    value_flt = si_to_float(value.strip("H").replace("u", "µ"))
    cmp.set_inductance(Constant(value_flt))

    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_part(component: Module):
    db = jlcpcb_db("jlcpcb_part_database/cache.sqlite3")

    for cmp in list(component.NODEs.get_all()):
        assert isinstance(cmp, Module)
        if hasattr(cmp, "partnumber"):
            assert isinstance(cmp.partnumber, Constant)
            partnumber = cmp.partnumber.value
            lcsc_pn = db.get_part_by_manufacturer_pn(partnumber)
            log.info(f"Picked {lcsc_pn: <8} for component {cmp}")
            lcsc.attach_footprint(component=cmp, partno=lcsc_pn)

        elif isinstance(cmp, Resistor):
            pick_resistor(db, cmp)

        elif isinstance(cmp, Inductor):
            pick_inductor(db, cmp)

        elif isinstance(cmp, Capacitor):
            pick_capacitor(db, cmp)

        elif isinstance(cmp, MOSFET):
            pick_mosfet(db, cmp)

        elif (
            isinstance(cmp, Mounting_Hole)
            or isinstance(cmp, Faebryk_Logo)
            or isinstance(cmp, Pin_Header)
        ):
            # Mechanical components have their footprint in the component defined
            pass

        else:
            if not get_all_nodes(cmp):
                raise RuntimeError(f"Non-virtual component without footprint: {cmp}")
            else:
                pick_part(cmp)
