import logging

logger = logging.getLogger(__name__)

import sqlite3
import re
from faebryk.library.library.parameters import Range, Constant
from si_prefix import SI_PREFIX_UNITS, si_format, si_parse
from math import log10, ceil, floor
from library.e_series import E24, E48, E96, E192


def si_to_float(si_value: str) -> float:
    return si_parse(si_value)


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
    return value_str.rstrip("0").rstrip(".") + prefix_str


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
    value = re.search(r'[\.0-9]+["pnµmkMG]?[ΩFH]', res[0][0])
    return value.group()


def e_values_in_range(value_range: Range):
    e_values = set(E24 + E48 + E96 + E192)
    result = []
    lower_exp = int(floor(log10(value_range.min)))
    upper_exp = int(ceil(log10(value_range.max)))
    for exp in range(lower_exp, upper_exp):
        for e in e_values:
            val = e * 10**exp
            if val >= value_range.min and val <= value_range.max:
                result.append(val)
    return result
