import logging

logger = logging.getLogger(__name__)

from si_prefix import SI_PREFIX_UNITS, si_format
import sqlite3


def resistor_value_to_si(value: float) -> str:
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


def build_resistor_tolerance_query(value: float, max_tolerance_percent: float):
    tolerances = {
        "0.01%": 0.0001 * value,
        "0.02%": 0.0002 * value,
        "0.05%": 0.0005 * value,
        "0.1%": 0.001 * value,
        "0.2%": 0.002 * value,
        "0.25%": 0.0025 * value,
        "0.5%": 0.005 * value,
        "1%": 0.01 * value,
        "2%": 0.02 * value,
        "3%": 0.03 * value,
        "5%": 0.05 * value,
        "7.5%": 0.075 * value,
        "10%": 0.10 * value,
        "15%": 0.15 * value,
        "20%": 0.20 * value,
        "30%": 0.30 * value,
    }
    plusminus = "±"
    query = "("
    add_or = False
    for tolerance_str, tolerance_abs in tolerances.items():
        if tolerance_abs <= max_tolerance_percent / 100 * value:
            if add_or:
                query += " OR "
            else:
                add_or = True
            tolerance_str_escape = tolerance_str.replace("%", "\%")
            query += "description LIKE '%" + plusminus + tolerance_str_escape + "%'"
            query += " ESCAPE '\\'"

    query += ")"
    return query


def find_resistor(
    resistance: float,
    tolerance_percent: float = 1,
    case: str = "0402",
    moq: int = 50,
):
    """
    Find the LCSC part number of a resistor which is in stock at JLCPCB.

    TODO: Does not find 'better' tolerance components, only exactly the tolerance specified.
    """
    resistor_str = resistor_value_to_si(resistance) + "Ω"
    tolerance_query = build_resistor_tolerance_query(resistance, tolerance_percent)

    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc 
        FROM "main"."components" 
        WHERE (category_id LIKE '%46%' or category_id LIKE '%52%')
        AND package LIKE '%{case}'
        AND stock > {moq}
        AND (description LIKE '% {resistor_str}%' OR description LIKE '{resistor_str}%')
        AND {tolerance_query}
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchone()
    if res is None:
        raise LookupError(f"Could not find resistor for query: {query}")
    return "C" + str(res[0])
