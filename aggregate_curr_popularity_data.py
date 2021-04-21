#!/usr/bin/env python

import numpy as np
import pandas as pd
import sqlite3
import orjson
from tqdm import tqdm

from datetime import datetime, timedelta
from argparse import ArgumentParser
import glob
import os

from popular_times import PopularTimes


# extract curr_popularity/rating_n from everyday's database
# align timestamp and to hour (for join with weather)


def load_curr_popularity(database_name):
    # curr_popularity (only select the rows that contains curr_popularity
    conn = sqlite3.connect(database_name)
    data = pd.read_sql_query("SELECT id, request_id, rating_n, timestamp, curr_popularity FROM curr_popularity WHERE curr_popularity>=0", conn)
    conn.close()
    return data


def extract_avg_popular_times(pop_times):
    avg_pop_times = {}

    # NOTE: can also use dict comprehension:
    # return {(day, hour): avg_pop
    #         for day, hourly_data, _ in pop_times
    #         for hour, avg_pop, *rest in hourly_data if hourly_data}

    if pop_times is None:
        return avg_pop_times

    for day, hourly_data, *other in pop_times:
        if hourly_data is None:
            continue

        for hour, avg_pop, *rest in hourly_data:
            avg_pop_times[(day, hour)] = avg_pop

    return avg_pop_times


def process_popular_times(database_name):
    """
    Process the "popular times" histograms from the scraped blob data.
    Later we can join this processed data back to "current popularity".

    :param database_name:
    :return:
    """

    conn = sqlite3.connect(database_name)
    cursor = conn.execute("SELECT id, request_id, timestamp, results FROM curr_popularity")

    ids = []
    request_ids = []
    datetimes = []

    # extract popularity from "popular_times"
    matched_popular_times = []

    for place_id, req_id, timestamp, blob in cursor:
        ids.append(place_id)
        request_ids.append(req_id)
        dt = timestamp_to_datetime(timestamp)
        datetimes.append(dt)

        if blob is None:
            print(place_id, req_id, timestamp, blob)
            # missing data is imputed as 0
            matched_popular_times.append(0)
        else:
            avg_popularity = extract_avg_popular_times(
                PopularTimes(*orjson.loads(blob)).popular_times)
            # datetime.weekday() has Monday = 0, Sunday = 6, whereas Google has Sunday = 7, Monday = 1
            key = (dt.weekday() + 1, dt.hour)
            matched_popular_times.append(avg_popularity.get(key, 0))

    df = pd.DataFrame({'id': ids, 'request_id': request_ids, 'datetime_hour': datetimes,
                       'avg_popularity': matched_popular_times})
    df_agg = df.groupby(['datetime_hour', 'id']).agg({
        'avg_popularity': np.mean, 'request_id': lambda x: x.iloc[0]
    }).reset_index()

    conn.close()

    return df_agg


def timestamp_to_datetime(ts):
    # get the time at the top of next hour (remove minutes/seconds/microseconds),
    return datetime.fromtimestamp(ts / 1000).replace(
        minute=0, second=0, microsecond=0
    ) + timedelta(hours=1)


def align_timestamp(data):
    # convert timestamp to datetime
    data['datetime_hour'] = data['timestamp'].apply(timestamp_to_datetime)
    # data['datetime'] = data['timestamp'].apply(lambda x: datetime.fromtimestamp(x / 1000))
    # # truncate to the hour, adding one hour to make the observation not ahead of weather obs.
    # data['datetime_hour'] = data['datetime'].apply(
    #     lambda x: x.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    # data resolution to hourly (.mean() for measures at the same datetime_hour)
    data_agg = data.groupby(['datetime_hour', 'id']).agg({'curr_popularity': np.mean, 'rating_n': np.mean,
                                                          'request_id': lambda x: x.iloc[0]}).reset_index()
    return data_agg  # columns: datetime_hour, id, request_id, curr_popularity, rating_n


def enrich_with_popularity(file_name):
    """
    The main processing function to enrich the original database with extracted
    popularity information, while aggregating the data by the hour.

    The returned DataFrame is a merged DataFrame by joining the current (real-time) popularity
    with the historically aggregated average popularity (Google popular times) together.

    :param file_name: The filename of the SQLite database
    :return: the merged DataFrame containing popularity data per hour
    """
    print('processing: {}'.format(file_name))
    data = load_curr_popularity(file_name)
    data_agg = align_timestamp(data)

    # DataFrame with average (hourly aggregated) popularity from Google popular times
    data_avg_pop = process_popular_times(file_name)

    # merge data_agg with data_avg_pop
    data_merged = data_agg.merge(data_avg_pop, how='inner', on=['request_id', 'id', 'datetime_hour'])

    return data_merged


def main():
    parser = ArgumentParser("Aggregate current popularity from multiple days into dataframe parquet")
    parser.add_argument("--output-database", required=True, help="The database to store the results")
    parser.add_argument("--input-folder", default='data',
                        help="The folder will be searched for data")

    args = parser.parse_args()

    # find filenames to be processed
    file_names = glob.glob(os.path.join(args.input_folder, "*.db"))

    df_to_concat = []
    for file_name in tqdm(file_names):
        if r'/nyc' in file_name or r'/philly' in file_name:
            data_merged = enrich_with_popularity(file_name)
            df_to_concat.append(data_merged)

    agg_df = pd.concat(df_to_concat, axis=0)
    # save
    agg_df.to_parquet(args.output_database)


if __name__ == "__main__":
    main()

