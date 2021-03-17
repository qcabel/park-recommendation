#!/usr/bin/env

from argparse import ArgumentParser
import pandas as pd
import sqlite3
import json

import get_id
import pickle


def parse_args():
    parser = ArgumentParser(description="Getting Google place ids for Places API")
    parser.add_argument("--api-key", required=True, help="Google Places API Key")
    parser.add_argument("--forest", default=False, action="store_true")
    parser.add_argument("--park-file", help="Coordinates in lat,lng format, e.g. 55.33,-135.66",
                        default=[])
    parser.add_argument("--output", required=True, help="The output file for this run.")
    parser.add_argument("--limit", type=int, default=-1)

    args = parser.parse_args()
    return args


def main():
    args = parse_args()

    out_conn = sqlite3.connect(args.output)
    out_cur = out_conn.cursor()

    if args.forest:
        out_cur.execute('''CREATE TABLE state_forest (id text, name text, address text, data blob)''')
    else:
        out_cur.execute('''CREATE TABLE state_park (id text, name text, address text, data blob)''')

    results = []
    text_list = pd.read_csv(args.park_file)
    for ind, text in enumerate(text_list.iloc[:, 0].tolist()):
        if 0 < args.limit < ind:
            break
        if args.forest:
            text += ' state forest, pa'
        else:
            text += ', pa'
        resp = get_id.get_state_park_id(args.api_key, text)

        to_insert_values = [(resp['candidates'][0]['place_id'], resp['candidates'][0]['name'],
                             resp['candidates'][0]['formatted_address'], json.dumps(resp))]
        if args.forest:
            out_cur.executemany('''INSERT INTO state_forest VALUES (?, ?, ?, ?)''', to_insert_values)
        else:
            out_cur.executemany('''INSERT INTO state_park VALUES (?, ?, ?, ?)''', to_insert_values)

        out_conn.commit()

    out_conn.close()


if __name__ == "__main__":
    main()