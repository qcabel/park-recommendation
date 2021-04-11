#!/usr/bin/env python

import numpy as np
import pandas as pd
import sqlite3

from datetime import datetime, timedelta
from argparse import ArgumentParser
import glob
import os


# extract curr_popularity/rating_n from everyday's database
# align timestamp and to hour (for join with weather)


def load_curr_popularity(database_name):
    # curr_popularity (only select the rows that contains curr_popularity
    conn = sqlite3.connect(database_name)
    data = pd.read_sql_query("SELECT id, request_id, rating_n, timestamp, curr_popularity FROM curr_popularity WHERE curr_popularity>=0", conn)
    conn.close()
    return data


def align_timestamp(data):
    # convert timestamp to datetime
    data['datetime'] = data['timestamp'].apply(lambda x: datetime.fromtimestamp(x / 1000))
    # truncate to the hour, adding one hour to make the observation not ahead of weather obs.
    data['datetime_hour'] = data['datetime'].apply(
        lambda x: x.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    # data resolution to hourly (.mean() for measures at the same datetime_hour)
    data_agg = data.groupby(['datetime_hour', 'id']).agg({'curr_popularity': np.mean, 'rating_n': np.mean,
                                                          'request_id': lambda x: x.iloc[0]}).reset_index()
    return data_agg  # columns: datetime_hour, id, request_id, curr_popularity, rating_n


def main():
    parser = ArgumentParser("Aggregate current popularity from multiple days into dataframe parquet")
    parser.add_argument("--output-database", required=True, help="The database to store the results")
    parser.add_argument("--input-folder", default='data',
                        help="The folder will be searched for data")

    args = parser.parse_args()

    # find filenames to be processed
    file_names = glob.glob(os.path.join(args.input_folder, "*.db"))

    df_to_concat = []
    for file_name in file_names:
        if r'/nyc' in file_name or r'/philly' in file_name:
            print('processing: {}'.format(file_name))
            data = load_curr_popularity(file_name)
            data_agg = align_timestamp(data)

            df_to_concat.append(data_agg)

    agg_df = pd.concat(df_to_concat, axis=0)
    # save
    agg_df.to_parquet(args.output_database)


if __name__ == "__main__":
    main()

