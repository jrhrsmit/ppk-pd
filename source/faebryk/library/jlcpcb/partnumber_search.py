import logging

logger = logging.getLogger(__name__)

import sqlite3


def find_partnumber(partnumber: str, moq: int = 1):
    con = sqlite3.connect("jlcpcb_part_database/cache.sqlite3")
    cur = con.cursor()
    query = f"""
        SELECT lcsc 
        FROM "main"."components" 
        WHERE stock > {moq}
        AND mfr LIKE '%{partnumber}%'
        ORDER BY basic DESC, price ASC
        """
    res = cur.execute(query).fetchone()
    if res is None:
        raise LookupError(f"Could not find partnumber for query: {query}")
    return "C" + str(res[0])
