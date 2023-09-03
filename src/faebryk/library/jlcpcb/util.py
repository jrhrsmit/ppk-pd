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
    return si_parse(si_value.rstrip("ΩFHAVz"))


def float_to_si(value: float) -> str:
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
