#!/usr/bin/env python

from argparse import ArgumentParser
import json
import sqlite3
from time import sleep

import popular_times


def parse_args():
    parser = ArgumentParser(description="Getting Places details and popular times")
    parser.add_argument("--api-key", required=True, help="Google Places API Key")
    parser.add_argument("--input-db", required=True,
                        help="The input SQLite DB which is used to fetch place details")
    parser.add_argument("--output", required=True,
                        help="The output SQLite DB where we store additional details & popular times flag")
    parser.add_argument("--limit", type=int, default=-1,
                        help="maximum number of query")

    args = parser.parse_args()

    return args


def main():
    args = parse_args()
    in_conn = sqlite3.connect(args.input_db)
    cur = in_conn.cursor()

    out_conn = sqlite3.connect(args.output)
    out_cur = out_conn.cursor()

    out_cur.execute('''CREATE TABLE popularity (id text, name text, address text, 
    has_popular_times integer, curr_popularity integer, details blob, raw blob)''')

    for ind, row in enumerate(cur.execute("SELECT id FROM places")):
        sleep(0.5)
        if args.limit > 0 and ind > args.limit:
            break

        place_id = row[0]
        place_details = popular_times.get_place_details_by_id(place_id, args.api_key)
        poptimes = popular_times.get_populartimes_by_place_details(place_details)

        # figure out how to store the data??
        has_popular_times = poptimes.popular_times is not None
        curr_popularity = poptimes.current_popularity or -1

        # insert place_details, curr_popularity, has_popular_times
        to_insert_values = [(place_id, place_details['name'], place_details['formatted_address'],
                            has_popular_times, curr_popularity, json.dumps(place_details),
                             json.dumps(poptimes))]
        out_cur.executemany('''INSERT INTO popularity VALUES (?, ?, ?, ?, ?, ?, ?)''', to_insert_values)

        out_conn.commit()

    in_conn.close()
    out_conn.close()


if __name__ == "__main__":
    main()
