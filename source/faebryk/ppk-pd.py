import logging
from typing import List

logger = logging.getLogger(__name__)

# local imports
import library.lcsc as lcsc

# library imports
from faebryk.library.core import Component
from faebryk.library.library.components import LED, Resistor
from faebryk.library.library.interfaces import Electrical, Power
from faebryk.library.library.parameters import Constant, Range
from faebryk.library.trait_impl.component import (
    has_defined_footprint_pinmap,
    has_defined_type_description,
    has_symmetric_footprint_pinmap,
)
from faebryk.library.traits.component import has_footprint, has_footprint_pinmap

# function imports
from faebryk.library.util import get_all_components, times

# Project library imports
from library.library.components import (
    MOSFET,
    DifferentialPair,
    PoweredLED,
    PowerSwitch,
    RJ45_Receptacle,
    USB_C_Receptacle,
)

class USB_C_PD_PSU(Component):
    pass

class STM32G473VET6(Component):
    """
    ST-Microelectronics MCU with 512kB flash, 128kB RAM, Cortex M4 core.
    """
    pass

class MCU(Component):
    pass

class Limiter(Component):
    pass

class Sensing(Component):
    pass

class Power_Frontend(Component):
    pass

class Logic_Analyzer_Frontend(Component):
    pass

class Display(Component):
    pass

class PPK_PD(Component):
    def __init__(self) -> None:
        super().__init__()

        class _CMPs(Component.ComponentsCls()):
            power_supply = USB_C_PD_PSU()
            mcu = MCU()
            power_frontend = Power_Frontend()
            logic_analyzer_frontend = Logic_Analyzer_Frontend()
        
        self.CMPs = _CMPs(self)


