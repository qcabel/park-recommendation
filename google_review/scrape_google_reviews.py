#!/usr/bin/env python

from itertools import zip_longest
from argparse import ArgumentParser
import time

import plyvel
import tqdm
import greviews
import logging
import orjson


def load_place_ids(fname):
    with open(fname) as f:
        return [place_id.strip() for place_id in f if place_id.strip()]


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)

def gen_key_name(place_id):
    return f"reviews:all:{place_id}".encode('utf8')

def main():
    parser = ArgumentParser(description="")
    parser.add_argument("--batch-size", default=100, type=int, help="The batch size to write to LevelDB.")
    parser.add_argument("--sleep", default=500, type=int, help="The milliseconds to sleep after each request.")
    parser.add_argument("-n", "--total", type=int, help="Specify the maximum number of places to scrape (for testing).")
    parser.add_argument("place_ids", help="A text file containing the place IDs (one per row)")
    parser.add_argument("output_db", help="Output database (LevelDB) directory for the scraped data.")

    args = parser.parse_args()

    db = plyvel.DB(args.output_db, create_if_missing=True)

    place_ids = load_place_ids(args.place_ids)

    if args.total is not None:
        place_ids = place_ids[:args.total]

    with tqdm.tqdm(total=len(place_ids)) as pbar:
        for batch in grouper(place_ids, args.batch_size):
            wb = db.write_batch()

            for place_id in batch:
                if place_id is not None:
                    try:
                        reviews = greviews.get_reviews(place_id)
                        time.sleep(args.sleep / 1000.0)

                        wb.put(gen_key_name(place_id), orjson.dumps(reviews))
                    except Exception as e:
                        logging.error(f"Request for place ID {place_id} has failed", exc_info=True)

                    pbar.update(1)

            wb.write()

    db.close()


if __name__ == "__main__":
    main()
