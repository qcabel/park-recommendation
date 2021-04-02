#!/usr/bin/env python

import pandas as pd
from argparse import ArgumentParser
import orjson
import sqlite3

from popular_times import PopularTimes


def extract_features_from_results_blob(individual_result, features):
    namedtuple_result = PopularTimes(*orjson.loads(individual_result))
    extracted = []
    for feature in features:
        extracted.append(getattr(namedtuple_result, feature))

    return pd.Series(extracted)


def compress_popular_times(popular_times_item):
    days = []
    average_popularity = []
    if isinstance(popular_times_item, (list, tuple)):
        #     if popular_times_item is not None:  #might be nan
        for day in popular_times_item:
            days.append(day[0])
            pop_hour = []
            if day[1] is not None:
                for hour in day[1]:
                    pop_hour.append(hour[:2])
            average_popularity.append(pop_hour)

    # return series so when calling .apply, output becomes dataframe, see https://stackoverflow.com/a/23690329
    return pd.Series([days, average_popularity])


def write_compressed_db(df, file_name):
    for name in ['time_spent', 'popular_times_day', 'popular_times']:
        df[name] = df[name].apply(lambda x: orjson.dumps(x))

    conn = sqlite3.connect(file_name)
    df.drop(columns=['results']).to_sql('compressed_curr_popularity', conn)
    conn.close()


def main():
    parser = ArgumentParser("Compress Philly outdoor scraped data")
    parser.add_argument("--input-database", required=True, help="The original database needs to be compressed")
    parser.add_argument("--output-database", help="The database with compressed data")

    args = parser.parse_args()

    if args.output_database is None:
        args.output_database = 'compressed/' + args.input_database + '_compress'

    # get results blob,
    conn = sqlite3.connect(args.input_database + '.db')
    data = pd.read_sql_query("SELECT * FROM curr_popularity", conn)
    conn.close()

    # decompose field,
    data[['rating', 'popular_times', 'time_spent']] = data['results'].apply(extract_features_from_results_blob, args=(
        ['rating', 'popular_times', 'time_spent'], ))

    # compress popular_times
    data[['popular_times_day', 'popular_times']] = data['popular_times'].apply(compress_popular_times)

    # write compressed db
    write_compressed_db(data, args.output_database + '.db')


if __name__ == "__main__":
    main()
