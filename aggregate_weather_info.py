#!/usr/bin/env python

import pandas as pd
import json
from datetime import datetime
from argparse import ArgumentParser
import os
import glob


"""1. go through a folder with all weather json
   2. convert each json to dataframe
   3. concat all partial dataframes to parquet
"""


def json_to_df(data_json, features_to_drop=['stations']):
    # convert json to df
    total_days = len(data_json['days'])
    all_data = [data_json['days'][iday]['hours'][ihour] for iday in range(total_days) for ihour in range(24)]

    for d in all_data:
        for f in features_to_drop:
            if f in d:
                del d[f]

    return pd.DataFrame(all_data)


def json_file_to_df(json_file_name):
    # load a json file and convert it into a dataframe

    # load json
    with open(json_file_name) as f:
        weather_data_partial = json.load(f)

    # construct dataframe
    features_to_drop = ['datetime', 'icon', 'stations', 'source']
    df = json_to_df(weather_data_partial, features_to_drop=features_to_drop)

    # time conversion: this assumes that the datetimeEpoch and local timezone are all America/New_York
    df['datetime'] = df['datetimeEpoch'].apply(datetime.fromtimestamp)

    df['location'] = weather_data_partial['address']
    df['latitude'] = weather_data_partial['latitude']
    df['longitude'] = weather_data_partial['longitude']

    return df


def main():
    parser = ArgumentParser("Aggregate weather json into dataframe parquet")
    parser.add_argument("--output-database", required=True, help="The database to store the results")
    parser.add_argument("--input-folder", default='weather_data',
                        help="The folder will be searched for partial weather data")

    args = parser.parse_args()

    # find filenames to be processed
    file_names = sorted(glob.glob(os.path.join(args.input_folder, "*.json")))

    df_to_concat = []
    for file_name in file_names:
        # print(file_name)
        df = json_file_to_df(file_name)
        df_to_concat.append(df)
    agg_df = pd.concat(df_to_concat, axis=0)
    # save
    agg_df.to_parquet(args.output_database)


if __name__ == "__main__":
    main()

# python aggregate_weather_info.py --output-database weather_data_Date_2021-03-16_2021-04-10.parquet

