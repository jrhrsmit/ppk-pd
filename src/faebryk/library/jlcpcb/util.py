import logging
from typing import Tuple
import json
import subprocess

logger = logging.getLogger(__name__)

import sqlite3
import os
import re
from si_prefix import SI_PREFIX_UNITS, si_format, si_parse
from math import log10, ceil, floor
from library.e_series import E24, E48, E96, E192


def si_to_float(si_value: str) -> float:
    si_value = si_value.replace("u", "µ")
    return si_parse(si_value.rstrip("ΩFHAVWz"))


def float_to_si(value: float) -> str:
    if value == float("inf"):
        value_str = "∞"
        prefix_str = ""
    elif value == float("-inf"):
        value_str = "-∞"
        prefix_str = ""
    else:
        value_str = si_format(
            value,
            precision=2,
            format_str="{value}",
        )
        prefix_str = si_format(
            value,
            precision=2,
            format_str="{prefix}",
        )
    si_value = value_str.rstrip("0").rstrip(".") + prefix_str
    # JLCPCB only uses 'u'
    si_value = si_value.replace("µ", "u")
    return si_value


def get_value_from_pn(lcsc_pn: str) -> str:
    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    pn = lcsc_pn.strip("C")
    query = f"""
        SELECT description 
        FROM "main"."components" 
        WHERE lcsc = {pn}
        """
    res = cur.execute(query).fetchall()
    if len(res) != 1:
        raise LookupError(f"Could not find exact match for PN {lcsc_pn}")
    value = re.search(r'[\.0-9]+["pnuµmkMG]?[ΩFH]', res[0][0])
    return value.group()

class jlcpcb_query:
    def __init__(self, query: str) -> None:
        con = connect_to_db()
        cur = con.cursor()

        query_result = cur.execute(query).fetchall()
        if not query_result:
            raise LookupError(f"Could not find resistor for query: {query}")

        self.results = []
        for r in query_result:
            self.results.append(
                {
                    "lcsc": r[0],
                    "manufacturer_pn": r[1],
                    "basic": r[2],
                    "price": r[3],
                    "extra": r[4],
                    "description": r[5],
                }
            )
        logger.info(f"Found {len(self.results)} results")

    def sort_by_basic_price(self, quantity: int = 1):
        """
        Sort query by basic and price

        Takes a query result in the form of (PN, basic, price JSON).
        Converts the price JSON to the price at that quantity as a float, and sorts it by basic, and then price
        """

        results = []
        for i, result in enumerate(self.results):
            price_json = json.loads(result["price"])
            for price_range in price_json:
                if quantity <= price_range["qTo"] or price_range["qTo"] == "null":
                    results.append(self.results[i])
                    results[-1]["basic"] = int(results[-1]["basic"])
                    results[-1]["price"] = float(price_range["price"])
                    break

        self.results = sorted(
            self.results, key=lambda row: (-row["basic"], row["price"])
        )


def sort_by_basic_price(
    query_results: list[Tuple[int, int, str]], quantity: int = 1
) -> list[Tuple[int, int, float]]:
    """
    Sort query by basic and priceS

    Takes a query result in the form of (PN, basic, price JSON).
    Converts the price JSON to the price at that quantity as a float, and sorts it by basic, and then price
    """

    for i, result in enumerate(query_results):
        price_json = json.loads(result[2])
        for price_range in price_json:
            if quantity <= price_range["qTo"] or price_range["qTo"] == "null":
                result_copy = list(query_results[i])
                result_copy[0] = int(result_copy[0])
                result_copy[1] = int(result_copy[1])
                result_copy[2] = float(price_range["price"])
                query_results[i] = result_copy
                break

    return sorted(query_results, key=lambda row: (-row[1], row[2]))


def connect_to_db() -> sqlite3.Connection:
    path = "jlcpcb_part_database/cache.sqlite3"
    script_path = "./jlcpcb_part_database/fetch.sh"
    # create the dir if it doesn't exist
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.isfile(path):
        answer = input(
            "JLCPCB database not yet downloaded. Download now? (~5.8GB) [Y/n]"
        )
        if answer == "" or answer.lower() == "y":
            rc = subprocess.call(script_path)
        else:
            exit(1)

    return sqlite3.connect(path)


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

