import logging
from typing import Tuple, Callable
import json
import subprocess
from pathlib import Path
import time

import sqlite3
import os
import re
from si_prefix import SI_PREFIX_UNITS, si_format, si_parse
from math import log10, ceil, floor
from library.e_series import E24, E48, E96, E192

from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from faebryk.core.core import Module, Parameter, Footprint
import wget

logger = logging.getLogger(__name__)


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


from typing import TypedDict


class jlcpcb_part(TypedDict):
    lcsc_pn: str
    manufacturer_pn: str
    basic: int
    price: str
    extra: str
    description: str


def connect_to_db(jlcpcb_db_path: str) -> sqlite3.Connection:
    script_path = "./jlcpcb_part_database/fetch.sh"
    # create the dir if it doesn't exist
    os.makedirs(os.path.dirname(jlcpcb_db_path), exist_ok=True)
    # download the db if it doesn't exist
    if not os.path.isfile(jlcpcb_db_path):
        answer = input(
            "JLCPCB database not yet downloaded. Download now? (~5.8GB) [Y/n]"
        )
        if answer == "" or answer.lower() == "y":
            rc = subprocess.call(script_path)
        else:
            exit(1)

    # check if the db is older than a week
    if os.path.getmtime(jlcpcb_db_path) < time.time() - (3600 * 24 * 7):
        answer = input(
            "JLCPCB database is older than a week. Download now? (~5.8GB) [Y/n]"
        )
        if answer == "" or answer.lower() == "y":
            rc = subprocess.call(script_path)
        else:
            logger.warning("Using old JLCPCB database")

    return sqlite3.connect(jlcpcb_db_path)


def jlcpcb_download_db(jlcpcb_db_path: Path):
    prompt_update = False

    if not jlcpcb_db_path.parent.is_dir:
        os.makedirs(jlcpcb_db_path)

    if not jlcpcb_db_path.is_file:
        print(f"No JLCPCB database file in {jlcpcb_db_path}.")
        prompt_update = True
    if os.path.getmtime(jlcpcb_db_path) < time.time() - (3600 * 24):
        print(f"JLCPCB database file in {jlcpcb_db_path} is more than a day old.")
        prompt_update = True

    if prompt_update:
        ans = input(f"Update JLCPCB database? [Y/n]:").lower()
        if ans == "y" or ans == "":
            for i in range(1, 7):
                wget.download(
                    f"https://yaqwsx.github.io/jlcparts/data/cache.z0{i}",
                    out=jlcpcb_db_path.parent,
                )
            subprocess.run(["7z", "x", "cache.zip"])


class jlcpcb_db:
    def __init__(self, db_path: str) -> None:
        self.con = connect_to_db(db_path)
        self.cur = self.con.cursor()
        self.results = []

    def sort_by_basic_price(self, quantity: int = 1) -> jlcpcb_part:
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

        self.results = sorted(results, key=lambda row: (-row["basic"], row["price"]))

        return self.results[0]

    def get_part(self, lcsc_pn: str) -> jlcpcb_part:
        pn = lcsc_pn.strip("C")
        query = f"""
            SELECT lcsc, mfr, basic, price, extra, description
            FROM "main"."components" 
            WHERE lcsc = {pn}
            """
        res = self.cur.execute(query).fetchall()
        if len(res) != 1:
            raise LookupError(f"Could not find exact match for PN {lcsc_pn}")

        return {
            "lcsc_pn": res[0][0],
            "manufacturer_pn": res[0][1],
            "basic": res[0][2],
            "price": res[0][3],
            "extra": res[0][4],
            "description": res[0][5],
        }

    def get_part_by_manufacturer_pn(self, partnumber: str, moq: int = 1):
        query = f"""
            SELECT lcsc 
            FROM "main"."components" 
            WHERE stock > {moq}
            AND mfr LIKE '%{partnumber}%'
            ORDER BY basic DESC, price ASC
            """
        res = self.cur.execute(query).fetchone()
        if res is None:
            raise LookupError(f"Could not find partnumber for query: {query}")
        return "C" + str(res[0])

    def get_category_id(self, category: str, subcategory: str) -> list[int]:
        query = f"""
            SELECT id 
            FROM "main"."categories" 
            WHERE category LIKE '{category}'
            AND subcategory LIKE '{subcategory}'
            """
        res = self.cur.execute(query).fetchall()
        if len(res) < 1:
            raise LookupError(
                f"Could not find exact match for category {category} and subcategory {subcategory}"
            )
        return [r[0] for r in res]

    def query_category(self, category_id: list[int], query: str) -> list[jlcpcb_part]:
        category_query = f"(category_id = {category_id[0]}"
        for id in category_id[1:]:
            category_query += f" OR category_id = {id}"
        category_query += ")"
        query = f"""
            SELECT lcsc, mfr, basic, price, extra, description
            FROM "main"."components" 
            WHERE {category_query}
            AND {query}
            """
        res = self.cur.execute(query).fetchall()
        if len(res) == 0:
            raise LookupError(f"Could not find any parts in category {category_id}")

        parts = []
        for r in res:
            parts.append(
                {
                    "lcsc_pn": r[0],
                    "manufacturer_pn": r[1],
                    "basic": r[2],
                    "price": r[3],
                    "extra": r[4],
                    "description": r[5],
                }
            )
        self.results = parts
        return parts

    def filter_results_by_extra_json_attributes(
        self, key: str, value: Parameter, attr_fn: Callable[[str], str] = lambda x: x
    ) -> None:
        filtered_results = []
        if isinstance(value, Constant):
            for _, part in enumerate(self.results):
                try:
                    extra_json = json.loads(part["extra"])
                    attributes = extra_json["attributes"]
                    field_val = attr_fn(attributes[key])
                    part_val = si_to_float(field_val)
                    if part_val == value.value:
                        filtered_results.append(part)
                except Exception as e:
                    logger.debug(f"Could not parse part {part}, {e}")
        elif isinstance(value, Range):
            for _, part in enumerate(self.results):
                try:
                    extra_json = json.loads(part["extra"])
                    attributes = extra_json["attributes"]
                    field_val = attr_fn(attributes[key])
                    part_val = si_to_float(field_val)
                    if part_val > value.min and part_val < value.max:
                        filtered_results.append(part)
                except Exception as e:
                    logger.debug(f"Could not parse part {part}, {e}")
        else:
            logger.error(
                f"Skipping filter for key '{key}'', parameter type {type(value)} unknown."
            )
            return
            # raise NotImplementedError

        logger.info(
            f"{len(filtered_results)} of {len(self.results)} left after filtering for key {key}"
        )
        self.results = filtered_results


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

    if not (
        hasattr(component, "map_string_to_pin")
        and callable(component.map_string_to_pin)
    ):
        logger.error(
            f"Component {component} has not footprint but also has no map_string_to_pin"
            " method."
        )
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
    easyeda_symbol = EasyedaSymbolImporter(easyeda_cp_cad_data=data).get_symbol()
    pinmap = {}
    for pin in easyeda_symbol.pins:
        name = pin.name.text
        number = pin.settings.spice_pin_number
        pinmap[number] = component.map_string_to_pin(name)
        logger.info(f"Attaching pin {number} ({name}) to {pinmap[number]}")
    component.add_trait(can_attach_to_footprint_via_pinmap(pinmap))
