from faebryk.library.can_attach_to_footprint_via_pinmap import (
    can_attach_to_footprint_via_pinmap,
)
import json
from faebryk.core.core import Module
from faebryk.library.can_attach_to_footprint import can_attach_to_footprint
from pathlib import Path
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.easyeda.easyeda_importer import (
    EasyedaSymbolImporter,
)
import logging

logger = logging.getLogger(__name__)

# TODO dont hardcode relative paths
BUILD_FOLDER = Path("./build")
LIB_FOLDER = Path("./src/kicad/libs")

def auto_pinmapping(component: Module, partno: str):
    # check pinmap
    if component.has_trait(can_attach_to_footprint):
        logger.warning(f"Component {component} already has a pinmap, skipping")
        return

    api = EasyedaApi()

    cache_base = BUILD_FOLDER / Path("cache/easyeda")
    cache_base.mkdir(parents=True, exist_ok=True)

    comp_path = cache_base.joinpath(partno)
    if not comp_path.exists():
        logger.debug(f"Did not find component {partno} in cache, downloading...")
        cad_data = api.get_cad_data_of_component(lcsc_id=partno)
        serialized = json.dumps(cad_data)
        comp_path.write_text(serialized)

    data = json.loads(comp_path.read_text())

    logger.warning(f"No pinmap found for component {component}, attaching pins by name")
    easyeda_symbol =  EasyedaSymbolImporter(
        easyeda_cp_cad_data=data
    ).get_symbol()
    pinmap = {}
    for pin in easyeda_symbol.pins:
        name = pin.name.text
        number  = pin.settings.spice_pin_number
        pinmap[number] = component.map_string_to_pin(name)
        logger.info(f"Attaching pin {number} ({name}) to {pinmap[number]}")
    component.add_trait(can_attach_to_footprint_via_pinmap(pinmap))

