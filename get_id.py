#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
part of the code adapted from https://github.com/m-wrzr/populartimes

with provided bounding box, search for all qualified places (filtered by types).
return placeID and (maybe) whether this place contain time information

"""

import calendar
import sqlite3
import datetime
import json
import logging
import math
import re
import ssl
import threading
import urllib.parse
import urllib.request
from queue import Queue
from time import sleep, time

import requests
from geopy import Point
from geopy.distance import geodesic, GeodesicDistance

logging.basicConfig(level=logging.INFO)

# urls for google api web service
BASE_URL = "https://maps.googleapis.com/maps/api/place/"
NEARBY_URL = BASE_URL + "nearbysearch/json?location={},{}&radius={}&types={}&key={}"


class PopulartimesException(Exception):
    """Exception raised for errors in the input.
    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


def get(api_key, types, p1, p2, n_threads=20, radius=180, all_places=False, mock=False):
    """
    :param api_key: str; api key from google places web service
    :param types: [str]; placetypes
    :param p1: (float, float); lat/lng of the south-west delimiting point
    :param p2: (float, float); lat/lng of the north-east delimiting point
    :param n_threads: int; number of threads to use
    :param radius: int; meters;
    :param all_places: bool; include/exclude places without populartimes
    :return: see readme
    """
    params = {
        "API_key": api_key,
        "radius": radius,
        "type": types,
        "n_threads": n_threads,
        "all_places": all_places,
        "bounds": {
            "lower": {
                "lat": min(p1[0], p2[0]),
                "lng": min(p1[1], p2[1])
            },
            "upper": {
                "lat": max(p1[0], p2[0]),
                "lng": max(p1[1], p2[1])
            }
        }
    }

    return run_all(params, mock=mock)


def scan_into_db(db_path, api_key, types, p1, p2, n_threads=20, radius=180, mock=False):
    """
    :param api_key: str; api key from google places web service
    :param types: [str]; placetypes
    :param p1: (float, float); lat/lng of the south-west delimiting point
    :param p2: (float, float); lat/lng of the north-east delimiting point
    :param n_threads: int; number of threads to use
    :param radius: int; meters;
    :param all_places: bool; include/exclude places without populartimes
    :return: see readme
    """
    params = {
        "API_key": api_key,
        "radius": radius,
        "type": types,
        "n_threads": n_threads,
        "bounds": {
            "lower": {
                "lat": min(p1[0], p2[0]),
                "lng": min(p1[1], p2[1])
            },
            "upper": {
                "lat": max(p1[0], p2[0]),
                "lng": max(p1[1], p2[1])
            }
        }
    }

    return run_sqlite(db_path, params, mock=mock)


def run_sqlite(db_path, params, mock=False):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    bounds = params["bounds"]

    logging.info("Creating database 'places'...")
    cur.execute('''CREATE TABLE places (id text, name text, data blob)''')

    start = datetime.datetime.now()
    i = 0
    for lat, lng in get_circle_centers([bounds["lower"]["lat"], bounds["lower"]["lng"]],  # southwest
                                       [bounds["upper"]["lat"], bounds["upper"]["lng"]],  # northeast
                                       params["radius"]):
        if not mock:
            sleep(0.5)
            # all places found in the current circle (using the nearly API)
            circle_places = get_radar(params, {
                "pos": (lat, lng),
                "res": 0
            })
            logging.info(f"{len(circle_places)} places found for {lat}, {lng}")

            # insert this batch into SQLite
            to_insert_values = [(x['place_id'], x['name'], json.dumps(x))
                                for x in circle_places.values()]
            cur.executemany('''INSERT INTO places VALUES (?, ?, ?)''', to_insert_values)

            conn.commit()

        i += 1

    if mock:
        logging.info(f"Mock run finished with {i} circles")
    else:
        logging.info("Finished in: {}".format(str(datetime.datetime.now() - start)))

    conn.close()


def run_all(params, mock=False):
    """
    Run radar scanning and return all places in one output.
    :param params:
    :param mock:
    :return:
    """
    start = datetime.datetime.now()
    g_places = {}

    bounds = params["bounds"]
    i = 0
    for lat, lng in get_circle_centers([bounds["lower"]["lat"], bounds["lower"]["lng"]],  # southwest
                                       [bounds["upper"]["lat"], bounds["upper"]["lng"]],  # northeast
                                       params["radius"]):
        if not mock:
            logging.info(f"Fetching places for {lat}, {lng}")
            sleep(0.5)
            # all places found in the current circle (using the nearly API)
            circle_places = get_radar(params, {
                "pos": (lat, lng),
                "res": 0
            })
            logging.info(f"{len(circle_places)} places found for {lat}, {lng}")

            # add the places found in this circle to all places for the given bounding box
            g_places.update(circle_places)

        i += 1

    if mock:
        logging.info(f"Mock run finished with {i} circles")

    logging.info("Finished in: {}".format(str(datetime.datetime.now() - start)))

    return g_places


def rect_circle_collision(rect_left, rect_right, rect_bottom, rect_top, circle_x, circle_y, radius):
    # returns true iff circle intersects rectangle

    def clamp(val, min, max):
        # limits value to the range min..max
        if val < min:
            return min
        if val > max:
            return max
        return val

    # Find the closest point to the circle within the rectangle
    closest_x = clamp(circle_x, rect_left, rect_right)
    closest_y = clamp(circle_y, rect_bottom, rect_top)

    # Calculate the distance between the circle's center and this closest point
    dist_x = circle_x - closest_x
    dist_y = circle_y - closest_y

    # If the distance is less than the circle's radius, an intersection occurs
    dist_sq = (dist_x * dist_x) + (dist_y * dist_y)

    return dist_sq < (radius * radius)


def cover_rect_with_circles(w, h, r):
    """
    fully cover a rectangle of given width and height with
    circles of radius r. This algorithm uses a hexagonal
    honeycomb pattern to cover the area.
    :param w: width of rectangle
    :param h: height of reclangle
    :param r: radius of circles
    :return: list of circle centers (x,y)
    """

    # initialize result list
    res = []

    # horizontal distance between circle centers
    x_dist = math.sqrt(3) * r
    # vertical distance between circle centers
    y_dist = 1.5 * r
    # number of circles per row (different for even/odd rows)
    cnt_x_even = math.ceil(w / x_dist)
    cnt_x_odd = math.ceil((w - x_dist / 2) / x_dist) + 1
    # number of rows
    cnt_y = math.ceil((h - r) / y_dist) + 1

    y_offs = 0.5 * r
    for y in range(cnt_y):
        if y % 2 == 0:
            # shift even rows to the right
            x_offs = x_dist / 2
            cnt_x = cnt_x_even
        else:
            x_offs = 0
            cnt_x = cnt_x_odd

        for x in range(cnt_x):
            res.append((x_offs + x * x_dist, y_offs + y * y_dist))

    # top-right circle is not always required
    if res and not rect_circle_collision(0, w, 0, h, res[-1][0], res[-1][1], r):
        res = res[0:-1]

    return res


def get_circle_centers(b1, b2, radius):
    """
    the function covers the area within the bounds with circles
    :param b1: south-west bounds [lat, lng]
    :param b2: north-east bounds [lat, lng]
    :param radius: specified radius, adapt for high density areas
    :return: list of circle centers that cover the area between lower/upper
    """

    sw = Point(b1)
    ne = Point(b2)

    # north/east distances
    dist_lat = geodesic(Point(sw[0], sw[1]), Point(ne[0], sw[1])).meters
    dist_lng = geodesic(Point(sw[0], sw[1]), Point(sw[0], ne[1])).meters

    circles = cover_rect_with_circles(dist_lat, dist_lng, radius)
    cords = [
        GeodesicDistance(meters=c[0])
            .destination(
            GeodesicDistance(meters=c[1])
                .destination(point=sw, bearing=90),
            bearing=0
        )[:2]
        for c in circles
    ]

    return cords


def get_radar(params, item):
    _lat, _lng = item["pos"]

    places = {}

    # places - nearby search
    # https://developers.google.com/places/web-service/search?hl=en#PlaceSearchRequests
    radar_str = NEARBY_URL.format(
        _lat, _lng, params["radius"], "|".join(params["type"]), params["API_key"]
    )

    # is this a next page request?
    if item["res"] > 0:
        # possibly wait remaining time until next_page_token becomes valid
        min_wait = 2  # wait at least 2 seconds before the next page request
        sec_passed = time() - item["last_req"]
        if sec_passed < min_wait:
            sleep(min_wait - sec_passed)
        radar_str += "&pagetoken=" + item["next_page_token"]

    resp = json.loads(requests.get(radar_str, auth=('user', 'pass')).text)
    check_response_code(resp)

    radar = resp["results"]

    item["res"] += len(radar)
    if item["res"] >= 60:
        logging.warning(
            f"Result limit in search radius [{_lat}, {_lng}, {params['radius']}] reached, some data may get lost")

    bounds = params["bounds"]

    # retrieve google ids for detail search
    for place in radar:
        geo = place["geometry"]["location"]
        if bounds["lower"]["lat"] <= geo["lat"] <= bounds["upper"]["lat"] \
                and bounds["lower"]["lng"] <= geo["lng"] <= bounds["upper"]["lng"]:
            # this isn't thread safe, but we don't really care,
            # since in worst case a set entry is simply overwritten
            places[place["place_id"]] = place

    # if there are more results, schedule next page requests
    if "next_page_token" in resp:
        item["next_page_token"] = resp["next_page_token"]
        item["last_req"] = time()
        # recursively this method itself, to get the next page's results
        inner_results = get_radar(params, item)
        places.update(inner_results)

    return places


def check_response_code(resp):
    """
    check if query quota has been surpassed or other errors occured
    :param resp: json response
    :return:
    """
    if resp["status"] == "OK" or resp["status"] == "ZERO_RESULTS":
        return

    if resp["status"] == "REQUEST_DENIED":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "Request was denied, the API key is invalid.")

    if resp["status"] == "OVER_QUERY_LIMIT":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "You exceeded your Query Limit for Google Places API Web Service, "
                                    "check https://developers.google.com/places/web-service/usage "
                                    "to upgrade your quota.")

    if resp["status"] == "INVALID_REQUEST":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "The query string is malformed, "
                                    "check if your formatting for lat/lng and radius is correct.")

    if resp["status"] == "INVALID_REQUEST":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "The query string is malformed, "
                                    "check if your formatting for lat/lng and radius is correct.")

    if resp["status"] == "NOT_FOUND":
        raise PopulartimesException("Google Places " + resp["status"],
                                    "The place ID was not found and either does not exist or was retired.")

    raise PopulartimesException("Google Places " + resp["status"],
                                "Unidentified error with the Places API, please check the response code")