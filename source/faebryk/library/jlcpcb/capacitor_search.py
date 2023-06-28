import logging

logger = logging.getLogger(__name__)

from si_prefix import SI_PREFIX_UNITS, si_format
import sqlite3
from library.library.components import Capacitor


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


def build_capacitor_temperature_coefficient_query(
    temperature_coefficient: Capacitor.TemperatureCoefficient,
):
    query = "("
    add_or = False
    for tc in Capacitor.TemperatureCoefficient:
        if tc >= temperature_coefficient:
            if add_or:
                query += " OR "
            else:
                add_or = True
            query += "description LIKE '%" + tc.name + "%'"

    query += ")"
    return query


def build_capacitor_tolerance_query(value: float, max_tolerance_percent: float):
    tolerances = {
        "0.1pF": 0.1e-12,
        "0.25pF": 0.25e-12,
        "0.5pF": 0.5e-12,
        "1%": 0.01 * value,
        "2%": 0.02 * value,
        "2.5%": 0.025 * value,
        "5%": 0.05 * value,
        "10%": 0.10 * value,
        "15%": 0.15 * value,
        "20%": 0.20 * value,
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


def find_capacitor(
    capacitance: float,
    tolerance_percent: float = 20,
    temperature_coefficient: Capacitor.TemperatureCoefficient = Capacitor.TemperatureCoefficient.X7R,
    voltage: float = 16,
    case: str = "0402",
    moq: int = 50,
):
    """
    Find the LCSC part number of a capacitor which is in stock at JLCPCB.

    """
    capacitance_str = resistor_value_to_si(capacitance) + "F"
    tolerance_query = build_capacitor_tolerance_query(capacitance, tolerance_percent)
    temperature_coefficient_query = build_capacitor_temperature_coefficient_query(
        temperature_coefficient
    )

    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc 
        FROM "main"."components" 
        WHERE (category_id LIKE '%27%' OR category_id LIKE '%29%')
        AND package LIKE '%{case}'
        AND stock > {moq}
        AND {temperature_coefficient_query}
        AND (description LIKE '% {capacitance_str}%' OR description LIKE  '{capacitance_str}%')
        AND {tolerance_query}
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchone()
    if res is None:
        raise LookupError(f"Could not find capacitor for query: {query}")
    return "C" + str(res[0])
