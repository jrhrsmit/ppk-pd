# library imports
from faebryk.core.core import Parameter
from faebryk.core.core import Module
from faebryk.library.Electrical import Electrical
from faebryk.library.ElectricPower import ElectricPower
from faebryk.library.ElectricLogic import ElectricLogic
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from faebryk.library.has_footprint import has_footprint
from faebryk.library.can_attach_via_pinmap import can_attach_via_pinmap
from faebryk.library.can_attach_to_footprint_symmetrically import (
    can_attach_to_footprint_symmetrically,
)
from faebryk.library.can_attach_to_footprint_via_pinmap import (
    can_attach_to_footprint_via_pinmap,
)

# function imports
from faebryk.libs.util import times
from faebryk.core.util import get_all_nodes

import logging

log = logging.getLogger(__name__)

# Project library imports
from library.library.components import (
    TPS54331DR,
    Capacitor,
    Resistor,
    Diode,
    Inductor,
    Mounting_Hole,
    Faebryk_Logo,
    Pin_Header,
    MOSFET,
    TPS543x,
)

from library.jlcpcb.part_picker import pick_part

from library.e_series import e_series_ratio, e_series_in_range, E12, E24, E48
from library.jlcpcb.util import float_to_si

#from math import sqrt, pi, log10, tan, atan, degrees, radians, exp
import math


class Buck_Converter_TPS5430(Module):
    """
    Buck converter based on TPS5430

    Datasheet: https://www.ti.com/lit/ds/slvs632j/slvs632j.pdf
    Inverting application note: https://www.ti.com/lit/an/slva257a/slva257a.pdf
    Eval board: https://www.ti.com/lit/ug/slvu243/slvu243.pdf
    """
    
    def __init__(
        self,
        input_voltage: Range = Range(10.8, 19.8),
        output_voltage: Constant = Constant(5.0),
        input_ripple_voltage: Constant = Constant(0.3),
        output_ripple_voltage: Constant = Constant(0.03),
        output_current: Constant = Constant(3),
        #output_voltage_accuracy: Constant = Constant(0.02),
    ) -> None:
        super().__init__()

        self.operating_frequency = 500e3
        self.input_voltage = input_voltage
        self.output_voltage = output_voltage
        self.input_ripple_voltage = input_ripple_voltage
        self.output_ripple_voltage = output_ripple_voltage
        self.output_current = output_current


        class _NODEs(Module.NODES()):
            U1 = TPS543x()
            # input cap always 10uF
            C1_input = Capacitor(
                capacitance=Constant(10e-6),
                rated_voltage=Constant(input_voltage.max),
                temperature_coefficient=Constant(Capacitor.TemperatureCoefficient.X7R),
                tolerance=Constant(20),
            )
            C2_boot = Capacitor()
            C3_output = Capacitor()
            D1_catch = Diode()
            L1 = Inductor(
                inductance=TBD,
                rated_current=TBD,
                tolerance=Constant(20),
                inductor_type=Inductor.InductorType.Power,
                self_resonant_frequency=self.operating_frequency * 1.5,
            )
            R1_sense_high = Resistor()
            R2_sense_low = Resistor()

        self.NODEs = _NODEs()

    def calc_L1(self):
        Kind = 0.2
        Vin_max = (self.input_voltage.max + self.input_ripple_voltage.value / 2)
        Lmin = (self.output_voltage.value + self.output_ripple_voltage.value /2) * (self.input_voltage.max - self.output_voltage.value) / (
            self.input_voltage.max * Kind * self.output_current.value * self.operating_frequency
        )
        L = Range(Lmin, 2 * Lmin)

        assert L.min >= 10e-6, "L1 is lower than minimum recommended value"
        assert L.max <= 100e-6, "L1 is higher than maximum recommended value"

        I_L_rms = math.sqrt(
            self.output_current.value ** 2 + 1/12 * (
                self.output_voltage.value * (
                    Vin_max - self.output_voltage.value
                ) / (
                    Vin_max * L.min * self.operating_frequency * 0.8
                )
            )  ** 2
        )

        I_L_peak = self.output_current.max + self.output_voltage * (Vin_max - self.output_voltage) / (
            1.6 * Vin_max * L.min * self.operating_frequency
        )

        self.NODEs.L1.inductance = L
        self.NODEs.L1.rated_current = Range(min(I_L_rms, I_L_peak), float("inf"))
    
    



