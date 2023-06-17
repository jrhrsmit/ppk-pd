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


def pick_fuse(fuse: Fuse):
    fuse_type = fuse.fuse_type.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    response_type = fuse.response_type.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    trip_current = fuse.trip_current.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    if fuse_type == Fuse.FuseType.RESETTABLE:
        if response_type == Fuse.ResponseType.SLOW:
            if trip_current == 1:
                lcsc.attach_footprint(component=fuse, partno="C914087")
            elif trip_current == 0.5:
                lcsc.attach_footprint(component=fuse, partno="C914085")

    if not fuse.has_trait(has_footprint):
        raise ValueError(
            f"Could not find fitting fuse for fuse type {fuse_type}, response type {response_type}, trip_current {trip_current}"
        )


def pick_mosfet(mosfet: MOSFET):
    channel_type = mosfet.channel_type.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    if channel_type == MOSFET.ChannelType.N_CHANNEL:
        # AO3400
        lcsc.attach_footprint(component=mosfet, partno="C20917")
        mosfet.add_trait(
            has_defined_footprint_pinmap(
                {
                    "1": mosfet.IFs.gate,
                    "2": mosfet.IFs.source,
                    "3": mosfet.IFs.drain,
                }
            )
        )
    elif channel_type == MOSFET.ChannelType.P_CHANNEL:
        # AO3401
        mosfet.add_trait(
            has_defined_footprint_pinmap(
                {
                    "1": mosfet.IFs.gate,
                    "2": mosfet.IFs.source,
                    "3": mosfet.IFs.drain,
                }
            )
        )
        lcsc.attach_footprint(component=mosfet, partno="C15127")
    else:
        raise ValueError(f"Unknown channel type: {channel_type}")


def pick_capacitor(capacitor: Capacitor):
    """
    Link a partnumber/footprint to a Capacitor

    Uses 0402 when possible
    """

    temperature_coefficient = capacitor.temperature_coefficient.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    value = capacitor.capacitance.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()
    rated_voltage = capacitor.rated_voltage.get_trait(
        is_representable_by_single_value
    ).get_single_representing_value()

    if temperature_coefficient <= Capacitor.TemperatureCoefficient.X7R:
        if rated_voltage <= 16:
            if value == 100e-9:
                lcsc.attach_footprint(component=capacitor, partno="C1525")

    if not capacitor.has_trait(has_footprint):
        raise ValueError(
            f"Could not find fitting capacitor for temperature coefficient {temperature_coefficient}, value {value}"
        )


def pick_resistor(resistor: Resistor):
    """
    Link a partnumber/footprint to a Resistor

    Selects only 1% 0402 resistors
    """

    resistors = {
        "C25076": Constant(100),
        "C11702": Constant(1e3),
        "C25879": Constant(2.2e3),
        "C25900": Constant(4.7e3),
        "C25905": Constant(5.1e3),
        "C25744": Constant(10e3),
        "C25741": Constant(100e3),
    }

    for partno, resistance in resistors.items():
        if (
            isinstance(resistor.resistance, Constant)
            and resistor.resistance.value == resistance.value
        ):
            lcsc.attach_footprint(component=resistor, partno=partno)
            return

    raise ValueError(f"Could not find resistor for value {resistor.resistance}")


def pick_tvs(tvs: Component):
    # assert fuse.has_trait(...)
    if isinstance(tvs, TVS_Array_Common_Anode):
        reverse_working_voltage = tvs.reverse_working_voltage.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        num_channels = tvs.num_channels.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()

        if num_channels == 5:
            if reverse_working_voltage == 5:
                lcsc.attach_footprint(component=tvs, partno="C15879")
                tvs.add_trait(
                    has_defined_footprint_pinmap(
                        {
                            "1": tvs.IFs.cathodes[0],
                            "2": tvs.IFs.anode,
                            "3": tvs.IFs.cathodes[1],
                            "4": tvs.IFs.cathodes[2],
                            "5": tvs.IFs.cathodes[3],
                            "6": tvs.IFs.cathodes[4],
                        }
                    )
                )
            else:
                raise ValueError(
                    f"No TVS diode for param channels = {num_channels} and Vrwm = {reverse_working_voltage}"
                )
        else:
            raise ValueError(f"No TVS diode for param channels = {num_channels}")
    elif isinstance(tvs, TVS_Array_Common_Anode_Power):
        reverse_working_voltage = tvs.reverse_working_voltage.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        num_channels = tvs.num_channels.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()

        if num_channels == 4:
            if reverse_working_voltage == 5:
                lcsc.attach_footprint(component=tvs, partno="C132258")
                tvs.add_trait(
                    has_defined_footprint_pinmap(
                        {
                            "1": tvs.IFs.channels[0],
                            "2": tvs.IFs.power.IFs.lv,
                            "3": tvs.IFs.channels[1],
                            "4": tvs.IFs.channels[2],
                            "5": tvs.IFs.power.IFs.hv,
                            "6": tvs.IFs.channels[3],
                        }
                    )
                )
            else:
                raise ValueError(
                    f"No TVS diode for param channels = {num_channels} and Vrwm = {reverse_working_voltage}"
                )
        elif num_channels == 2:
            if reverse_working_voltage == 5:
                lcsc.attach_footprint(component=tvs, partno="C395633")
                tvs.add_trait(
                    has_defined_footprint_pinmap(
                        {
                            "1": tvs.IFs.power.IFs.lv,
                            "2": tvs.IFs.channels[0],
                            "3": tvs.IFs.channels[1],
                            "4": tvs.IFs.power.IFs.hv,
                        }
                    )
                )
            else:
                raise ValueError(
                    f"No TVS diode for param channels = {num_channels} and Vrwm = {reverse_working_voltage}"
                )
        else:
            raise ValueError(f"No TVS diode for param channels = {num_channels}")
    elif isinstance(tvs, TVS):
        reverse_working_voltage = tvs.reverse_working_voltage.get_trait(
            is_representable_by_single_value
        ).get_single_representing_value()
        if reverse_working_voltage == 5:
            lcsc.attach_footprint(component=tvs, partno="C85402")
            tvs.add_trait(
                has_defined_footprint_pinmap(
                    {
                        "1": tvs.IFs.cathode,
                        "2": tvs.IFs.anode,
                    }
                )
            )
        else:
            raise ValueError(f"No TVS diode for param Vrwm = {reverse_working_voltage}")
    else:
        raise ValueError(f"Unknown TVS type: {type(tvs)}")

    if not tvs.has_trait(has_footprint):
        raise ValueError(
            f"Could not find fitting TVS diode with type {type(tvs)}, Vrwm = {reverse_working_voltage}"
        )


def pick_part(component: Component):
    for cmp in component.CMPs.get_all():
        if hasattr(cmp, 'partnumber'):
            partnumber = cmp.partnumber.get_trait(
                is_representable_by_single_value
            ).get_single_representing_value()

        if isinstance(cmp, USB_C_Receptacle_Power_Only):
            lcsc.attach_footprint(component=cmp, partno="C283540")
            cmp.add_trait(
                has_defined_footprint_pinmap(
                    {
                        "6": cmp.IFs.gnd[0],
                        "5": cmp.IFs.vbus[0],
                        "4": cmp.IFs.cc2,
                        "3": cmp.IFs.cc1,
                        "2": cmp.IFs.vbus[1],
                        "1": cmp.IFs.gnd[1],
                        "0": cmp.IFs.shield,
                    }
                )
            )
        elif isinstance(cmp, Resistor):
            pick_resistor(cmp)
        elif isinstance(cmp, Fuse):
            pick_fuse(cmp)
        elif (
            isinstance(cmp, TVS)
            or isinstance(cmp, TVS_Array_Common_Anode)
            or isinstance(cmp, TVS_Array_Common_Anode_Power)
        ):
            pick_tvs(cmp)
        elif isinstance(cmp, MOSFET):
            pick_mosfet(cmp)
        elif isinstance(cmp, Capacitor):
            pick_capacitor(cmp)
        elif (
            isinstance(cmp, Mounting_Hole)
            or isinstance(cmp, Faebryk_Logo)
        ):
            # Mechanical components have their footprint in the component defined
            pass
        else:
            if not get_all_components(cmp):
                raise RuntimeError(f"Non-virtual component without footprint: {cmp}")
            else:
                pick_part(cmp)