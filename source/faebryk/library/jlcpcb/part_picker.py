import logging

logger = logging.getLogger("local_library")

# Faebryk library imports
from faebryk.library.trait_impl.component import (
    has_defined_footprint_pinmap,
    has_footprint,
)
from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)


# Faebryk function imports
from faebryk.library.util import get_all_components

# Project library imports
import library.lcsc as lcsc
from library.library.components import *

from library.jlcpcb.capacitor_search import find_capacitor
from library.jlcpcb.inductor_search import find_inductor
from library.jlcpcb.resistor_search import find_resistor
from library.jlcpcb.partnumber_search import find_partnumber

from library.jlcpcb.util import (
    float_to_si,
    si_to_float,
    get_value_from_pn,
)
from faebryk.library.library.parameters import Range, Constant


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


def pick_part(component: Component):
    for cmp in component.CMPs.get_all():
        if hasattr(cmp, "partnumber"):
            partnumber = cmp.partnumber.get_trait(
                is_representable_by_single_value
            ).get_single_representing_value()
            lcsc_pn = find_partnumber(partnumber)
            logger.info(f"Picked {lcsc_pn: <8} for component {cmp}")
            lcsc.attach_footprint(component=cmp, partno=lcsc_pn)

        elif isinstance(cmp, Resistor):
            pick_resistor(cmp)

        elif isinstance(cmp, Inductor):
            pick_inductor(cmp)

        elif isinstance(cmp, Capacitor):
            pick_capacitor(cmp)

        elif (
            isinstance(cmp, Mounting_Hole)
            or isinstance(cmp, Faebryk_Logo)
            or isinstance(cmp, Pin_Header)
        ):
            # Mechanical components have their footprint in the component defined
            pass

        else:
            if not get_all_components(cmp):
                raise RuntimeError(f"Non-virtual component without footprint: {cmp}")
            else:
                pick_part(cmp)
