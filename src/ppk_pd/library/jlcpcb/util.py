import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from math import ceil, floor, log10
from pathlib import Path
from typing import Any, Callable, Tuple, TypedDict

import wget
from faebryk.core.core import Footprint, Module, Parameter
from faebryk.library.Constant import Constant
from faebryk.library.Range import Range
from faebryk.library.TBD import TBD
from faebryk.library.Resistor import Resistor
from library.e_series import E24, E48, E96, E192
from si_prefix import SI_PREFIX_UNITS, si_format, si_parse

# import asyncio
from tortoise import Tortoise
from tortoise.expressions import Q
from tortoise.fields import CharField, IntField, JSONField
from tortoise.models import Model

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


def get_tolerance_from_str(tolerance_str: str, cmp_value: Parameter) -> str:
    try:
        if "%" in tolerance_str:
            tolerance = float(tolerance_str.strip("%±")) / 100
        elif "~" in tolerance_str:
            tolerances = tolerance_str.split("~")
            tolerances = [float(t) for t in tolerances]
            tolerance = max(tolerances) / 100
        else:
            if isinstance(cmp_value, Constant):
                max_value = cmp_value.value
            elif isinstance(cmp_value, Range):
                max_value = cmp_value.max
            else:
                raise NotImplementedError
            tolerance_value = si_to_float(tolerance_str.strip("±"))
            tolerance = tolerance_value / max_value
        return str(tolerance)
    except Exception as e:
        logger.info(f"Could not convert tolerance from string: {tolerance_str}, {e}")
        return "inf"


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


class Category(Model):
    id = IntField(pk=True)
    category = CharField(max_length=255)
    subcategory = CharField(max_length=255)

    class Meta:
        table = "categories"


class Component(Model):
    lcsc = IntField(pk=True)
    category_id = IntField()
    mfr = CharField(max_length=255)
    package = CharField(max_length=255)
    joints = IntField()
    manufacturer_id = IntField()
    basic = IntField()
    description = CharField(max_length=255)
    datasheet = CharField(max_length=255)
    stock = IntField()
    price = JSONField()
    last_update = IntField()
    extra = JSONField()
    flag = IntField()
    last_on_stock = IntField()

    class Meta:
        table = "components"


class jlcpcb_db:
    async def __init__(
        self, db_path: str = "sqlite://jlcpcb_part_database/cache.sqlite3"
    ) -> None:
        self.results = []
        await Tortoise.init(
            db_url=db_path,
            modules={
                "models": [__name__]
            },  # Use __name__ to refer to the current module
        )

    def get_part(self, lcsc_pn: str) -> jlcpcb_part:
        res = Component.filter(
            lcsc=lcsc_pn.strip("C"),
        )
        if res.count() != 1:
            raise LookupError(f"Could not find exact match for PN {lcsc_pn}")
        res = res.first()
        return {
            "lcsc_pn": res.lcsc,
            "manufacturer_pn": res.mfr,
            "basic": res.basic,
            "price": res.price,
            "extra": res.extra,
            "description": res.description,
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

    async def get_category_id(
        self, category: str = "", subcategory: str = ""
    ) -> list[dict[str, Any]]:
        filter_query = Q()
        if category != "":
            filter_query &= Q(category__icontains=category)
        if subcategory != "":
            filter_query &= Q(subcategory__icontains=subcategory)
        category_ids = await Category.filter(filter_query).values("id")
        if len(category_ids) < 1:
            raise LookupError(
                f"Could not find a match for category {category} and subcategory {subcategory}"
            )
        return [c["id"] for c in category_ids]

    def build_query(self, key: str, p: Parameter) -> Q:
        filter_dict = {}
        if isinstance(p, Constant):
            filter_dict[key] = p.value
            return Q(**filter_dict)
        elif isinstance(p, Range):
            filter_dict[key + "__gte"] = p.min
            filter_dict[key + "__lte"] = p.max
            return Q(**filter_dict)
        elif isinstance(p, TBD):
            logger.warning(f"Skipping filter for key '{key}'', parameter type TBD.")
            return Q()
        else:
            raise NotImplementedError

    async def find_resistor(self, cmp: Resistor):
        category_ids = await self.get_category_id("Resistors", "Chip Resistors - Surface Mount")
        filter_query = Q(category_id__in=category_ids)
        filter_query &= self.build_query("attributes__Resistance", cmp.resistance)
        filter_query &= self.build_query("attributes__Tolerance", cmp.tolerance)
        filter_query &= self.build_query("attributes__Power", cmp.power)

        


    async def query_category(
        self, category: str = "", subcategory: str = "", 
    ) -> list[jlcpcb_part]:
        category_ids = await self.get_category_id(category, subcategory)
        res = await Component.filter(
            category_id__in=category_ids,
            extra__contains=[
                {"attributes__Resistance": value_to_find},
                {"attributes__Tolerance": tolerance_to_find},
            ],
            # extra__contains={"Tolerance": tolerance_to_find}
        ).first()

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

        res = Component.filter(
            category_id=category_id,
        ).order_by("-basic", "price")
        if res.count() != 1:
            raise LookupError(f"Could not find exact match for PN {lcsc_pn}")
        res = res.first()
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

