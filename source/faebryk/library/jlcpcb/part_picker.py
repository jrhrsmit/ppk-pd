import logging

logger = logging.getLogger("local_library")

# Faebryk library imports
from faebryk.library.trait_impl.component import (
    has_defined_footprint_pinmap,
    has_footprint,
)
from faebryk.library.library.components import Resistor
from faebryk.library.traits.parameter import (
    is_representable_by_single_value,
)


# Faebryk function imports
from faebryk.library.util import get_all_components

# Project library imports
import library.lcsc as lcsc
from library.library.components import *

from library.jlcpcb.capacitor_search import find_capacitor
from library.jlcpcb.resistor_search import find_resistor
from library.jlcpcb.partnumber_search import find_partnumber


def pick_resistor(cmp: Resistor):
    tolerance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    resistance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    lcsc_pn = find_resistor(resistance, tolerance)
    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_capacitor(cmp: Capacitor):
    tolerance = cmp.tolerance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    capacitance = cmp.capacitance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    temperature_coefficient = cmp.temperature_coefficient.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    rated_voltage = cmp.rated_voltage.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    lcsc_pn = find_capacitor(
        capacitance=capacitance,
        tolerance_percent=tolerance,
        temperature_coefficient=temperature_coefficient,
        voltage=rated_voltage,
    )
    lcsc.attach_footprint(component=cmp, partno=lcsc_pn)


def pick_part(component: Component):
    for cmp in component.CMPs.get_all():
        if hasattr(cmp, "partnumber"):
            partnumber = cmp.partnumber.get_trait(
                is_representable_by_single_value
            ).get_single_representing_value()
            lcsc_pn = find_partnumber(partnumber)
            lcsc.attach_footprint(component=cmp, partno=lcsc_pn)

        elif isinstance(cmp, Resistor):
            pick_resistor(cmp)

        elif isinstance(cmp, Capacitor):
            pick_capacitor(cmp)

        elif isinstance(cmp, Mounting_Hole) or isinstance(cmp, Faebryk_Logo):
            # Mechanical components have their footprint in the component defined
            pass
        else:
            if not get_all_components(cmp):
                raise RuntimeError(f"Non-virtual component without footprint: {cmp}")
            else:
                pick_part(cmp)
