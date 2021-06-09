#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd


class ProximityParkRanker:
    PROXIMITY_THRESHOLD_MILES = 20.0

    def __init__(self):
        self.info_df_wt_fsq_type = pd.read_parquet('park_feature_with_predpop_clean.parquet')
        self.zipcode_geo = pd.read_parquet('zipcode_geo.parquet')
        self.info_with_inaturalist = pd.read_parquet('park_info_with_inaturalist.parquet')

        self.all_zipcodes = set(self.zipcode_geo['zipcode'])

        self.latitudes = self.zipcode_geo['lat'].values.astype(np.float)
        self.longitudes = self.zipcode_geo['lng'].values.astype(np.float)

    @staticmethod
    def max_min_norm(data, min_val=None, max_val=None):
        if min_val is None:
            min_val = data.min()
        if max_val is None:
            max_val = data.max()

        return (data - min_val) / (max_val - min_val)

    @staticmethod
    def compute_dists(lats, lngs, point):
        lat1, lng1 = point
        lat1 = float(lat1)
        lng1 = float(lng1)

        R = 6371e3
        phi1 = lat1 * np.pi / 180
        phi2 = lats * np.pi / 180
        delta_phi = (lats - lat1) * np.pi / 180
        delta_lambda = (lngs - lng1) * np.pi / 180

        a = np.sin(delta_phi / 2) ** 2 + \
            np.cos(phi1) * np.cos(phi2) * \
            np.sin(delta_lambda / 2) ** 2

        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

        d = R * c / 1609.34

        return d

    def get_coordinate(self, zipcode):
        return [float(c)
                for c in self.zipcode_geo[self.zipcode_geo['zipcode'] == zipcode][['lat', 'lng']].iloc[0].values.tolist()]

    def get_zipcode_with_coords(self, zipcode):
        if zipcode in self.all_zipcodes:
            return self.zipcode_geo[self.zipcode_geo['zipcode'] == zipcode][['zipcode', 'lat', 'lng']].to_json(
                orient='records')
        else:
            return None

    def find_closest_zipcode(self, point):
        dists = self.compute_dists(self.latitudes, self.longitudes, point)
        index = np.argmin(dists)

        if dists[index] < self.PROXIMITY_THRESHOLD_MILES:
            return self.zipcode_geo[['zipcode', 'lat', 'lng']].iloc[index:(index+1)].to_json(orient='records')
        else:
            return None

    def get_ranked_parks(self, zipcode, max_distance=None):
        park_ids = self.zipcode_geo[self.zipcode_geo['zipcode'] == zipcode]['nearby_parks'].iloc[0]
        df_tmp = self.info_df_wt_fsq_type[self.info_df_wt_fsq_type['id'].isin(park_ids)]
        df_tmp = df_tmp.merge(self.info_with_inaturalist, how='left', on=['id', 'name', 'lat', 'lng', 'address'])
        df_tmp.dropna(subset=['species_count'], inplace=True)
        df_tmp.reset_index(drop=True, inplace=True)

        # clean up data
        df_tmp.loc[np.where(df_tmp['species_count'] > 1500)[0], 'species_count'] = 1500
        # normalize
        df_tmp['species_count_norm'] = self.max_min_norm(np.sqrt(df_tmp['species_count'] + 1.0))
        df_tmp['rating_norm'] = self.max_min_norm(df_tmp['rating'])
        df_tmp['traffic_norm'] = self.max_min_norm(-df_tmp['pred_pop_residual'])
        df_tmp['traffic_rank'] = np.argsort(np.argsort(-df_tmp['pred_pop_residual'])) / df_tmp.shape[0]

        df_tmp['distance'] = self.compute_dists(
            df_tmp['lat'].values.astype(np.float),
            df_tmp['lng'].values.astype(np.float),
            self.get_coordinate(zipcode))

        if max_distance:
            df_tmp = df_tmp[df_tmp['distance'] < max_distance]

        df_tmp['total_score'] = 0.6 * df_tmp['species_count_norm'] + df_tmp['traffic_norm'] + \
                                1.5 * df_tmp['rating_norm']

        df_tmp = df_tmp.sort_values(by=['total_score'], ascending=False)

        return df_tmp

