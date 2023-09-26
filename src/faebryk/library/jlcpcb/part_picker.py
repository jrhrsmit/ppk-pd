import logging

log = logging.getLogger("local_library")

# Faebryk library imports
from faebryk.library.has_defined_footprint import has_defined_footprint
from faebryk.library.can_attach_via_pinmap import can_attach_via_pinmap


# Faebryk function imports
from faebryk.core.util import get_all_nodes

# Project library imports
import faebryk.libs.picker.lcsc as lcsc
from library.library.components import *

from library.jlcpcb.capacitor_search import find_capacitor
from library.jlcpcb.inductor_search import find_inductor
from library.jlcpcb.resistor_search import find_resistor
from library.jlcpcb.partnumber_search import find_partnumber
from library.jlcpcb.mosfet_search import find_mosfet

from library.jlcpcb.util import (
    float_to_si,
    si_to_float,
    get_value_from_pn,
    auto_pinmapping,
)
from faebryk.core.core import Module, Parameter, Footprint
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD


def pick_mosfet(cmp: MOSFET):
    lcsc_pn = find_mosfet(cmp)
    auto_pinmapping(component=cmp, partno=lcsc_pn)
    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_resistor(cmp: Resistor):
    lcsc_pn = find_resistor(cmp)

    value = get_value_from_pn(lcsc_pn)
    value_flt = si_to_float(value.strip("Ω"))
    cmp.set_resistance(Constant(value_flt))

    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_capacitor(cmp: Capacitor):
    lcsc_pn = find_capacitor(cmp)

    value = get_value_from_pn(lcsc_pn)
    value_flt = si_to_float(value.strip("F").replace("u", "µ"))
    cmp.set_capacitance(Constant(value_flt))

    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_inductor(cmp: Inductor):
    lcsc_pn = find_inductor(cmp)

    value = get_value_from_pn(lcsc_pn)
    value_flt = si_to_float(value.strip("H").replace("u", "µ"))
    cmp.set_inductance(Constant(value_flt))

    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_part(component: Module):
    for cmp in list(component.NODEs.get_all()):
        # assert type(cmp) is Module
        if hasattr(cmp, "partnumber"):
            assert type(cmp.partnumber) is Constant
            partnumber = cmp.partnumber.value
            lcsc_pn = find_partnumber(partnumber)
            log.info(f"Picked {lcsc_pn: <8} for component {cmp}")
            lcsc.attach_footprint(component=cmp, partno=lcsc_pn)

        elif isinstance(cmp, Resistor):
            pick_resistor(cmp)

        elif isinstance(cmp, Inductor):
            pick_inductor(cmp)

        elif isinstance(cmp, Capacitor):
            pick_capacitor(cmp)

        elif isinstance(cmp, MOSFET):
            pick_mosfet(cmp)

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
