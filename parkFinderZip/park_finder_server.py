#!/usr/bin/env python
# -*- coding: utf-8 -*-

from argparse import ArgumentParser
import orjson

import requests
from parkrank import ProximityParkRanker
from flask import Flask, Response, send_file, send_from_directory, request

app = Flask(__name__)
park_ranker = ProximityParkRanker()


def geocode_zip_us(zipcode):
    params = {'format': 'json',              #API specific
              'addressdetails': 0,
              'country': 'US',
              'postalcode': zipcode}
    headers = {'user-agent': 'parkFinder'}   #  Need to supply a user agent other than the default provided
                                             #  by requests for the API to accept the query.
    try:
        result = requests.get('http://nominatim.openstreetmap.org/search', params=params, headers=headers).json()

        if len(result) > 0:
            return result[0]['lat'], result[0]['lon']
        else:
            return None
    except Exception:
        return None


@app.route('/')
def index():
    return send_file('zipMap.html')


@app.route('/static/<path:path>')
def serve_static_file(path):
    return send_from_directory('static', path)


@app.route('/nearest_zip/<zipcode>')
def get_nearest_zipcode(zipcode):
    zipcode_with_coords = park_ranker.get_zipcode_with_coords(zipcode)
    if zipcode_with_coords:
        return orjson.loads(zipcode_with_coords)[0]
    else:  # not in the existing list, request (lat, lng), and find the closest zip (if not too far)
        coords = geocode_zip_us(zipcode)

        if coords is not None:
            # TODO: may identify more efficient solutions
            nearest = park_ranker.find_closest_zipcode(coords)
            if nearest:
                return orjson.loads(nearest)[0]
            else:
                return {}
        else:
            return {}


@app.route('/recommend/<zipcode>')
def get_recommended_parks(zipcode):
    max_dist = request.args.get('maxdist')
    if max_dist is not None:
        max_dist = float(max_dist)

    return Response(
        park_ranker.get_ranked_parks(zipcode, max_distance=max_dist).to_json(orient='records'),
        mimetype='application/json')


def main():
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
