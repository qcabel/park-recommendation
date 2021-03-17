#!/usr/bin/env python

import calendar
import json
import re
import urllib.parse
import logging
import requests
from collections import namedtuple

from get_id import check_response_code

# urls for google api web service
BASE_URL = "https://maps.googleapis.com/maps/api/place/"
RADAR_URL = BASE_URL + "radarsearch/json?location={},{}&radius={}&types={}&key={}"
NEARBY_URL = BASE_URL + "nearbysearch/json?location={},{}&radius={}&types={}&key={}"
DETAIL_URL = BASE_URL + "details/json?placeid={}&key={}"

# user agent for populartimes request
USER_AGENT = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_1) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/54.0.2840.98 Safari/537.36"}


PopularTimes = namedtuple('PopularTimes',
                          ('place_id', 'rating', 'rating_n', 'popular_times',
                           'current_popularity', 'time_spent'))


def index_get(array, *argv):
    """
    checks if a index is available in the array and returns it
    :param array: the data array
    :param argv: index integers
    :return: None if not available or the return value
    """

    try:

        for index in argv:
            array = array[index]

        return array

    # there is either no info available or no popular times
    # TypeError: rating/rating_n/populartimes wrong of not available
    except (IndexError, TypeError):
        return None


def get_popularity_for_day(popularity):
    """
    Returns popularity for day
    :param popularity:
    :return:
    """

    # Initialize empty matrix with 0s
    pop_json = [[0 for _ in range(24)] for _ in range(7)]
    wait_json = [[0 for _ in range(24)] for _ in range(7)]

    for day in popularity:

        day_no, pop_times = day[:2]

        if pop_times:
            for hour_info in pop_times:

                hour = hour_info[0]
                pop_json[day_no - 1][hour] = hour_info[1]

                # check if the waiting string is available and convert no minutes
                if len(hour_info) > 5:
                    wait_digits = re.findall(r'\d+', hour_info[3])

                    if len(wait_digits) == 0:
                        wait_json[day_no - 1][hour] = 0
                    elif "min" in hour_info[3]:
                        wait_json[day_no - 1][hour] = int(wait_digits[0])
                    elif "hour" in hour_info[3]:
                        wait_json[day_no - 1][hour] = int(wait_digits[0]) * 60
                    else:
                        wait_json[day_no - 1][hour] = int(wait_digits[0]) * 60 + int(wait_digits[1])

                # day wrap
                if hour_info[0] == 23:
                    day_no = day_no % 7 + 1

    ret_popularity = [
        {
            "name": list(calendar.day_name)[d],
            "data": pop_json[d]
        } for d in range(7)
    ]

    # waiting time only if applicable
    ret_wait = [
        {
            "name": list(calendar.day_name)[d],
            "data": wait_json[d]
        } for d in range(7)
    ] if any(any(day) for day in wait_json) else []

    # {"name" : "monday", "data": [...]} for each weekday as list
    return ret_popularity, ret_wait


def get_populartimes_by_id(place_id, api_key):
    details = get_place_details_by_id(place_id, api_key)
    return get_populartimes_by_place_details(details)


def get_place_details_by_id(place_id, api_key):
    detail_str = DETAIL_URL.format(place_id, api_key)
    resp = json.loads(requests.get(detail_str, auth=('user', 'pass')).text)
    check_response_code(resp)

    return resp["result"]


def get_populartimes_by_place_details(detail) -> PopularTimes:
    address = detail["formatted_address"] if "formatted_address" in detail else detail.get("vicinity", "")

    return get_populartimes_by_name_addr(detail['name'], address)


def build_populartimes_url(name, address):
    place_identifier = "{} {}".format(name, address)

    params_url = {
        "tbm": "map",
        "tch": 1,
        "hl": "en",
        "q": urllib.parse.quote_plus(place_identifier),
        "pb": "!4m12!1m3!1d4005.9771522653964!2d-122.42072974863942!3d37.8077459796541!2m3!1f0!2f0!3f0!3m2!1i1125!2i976"
              "!4f13.1!7i20!10b1!12m6!2m3!5m1!6e2!20e3!10b1!16b1!19m3!2m2!1i392!2i106!20m61!2m2!1i203!2i100!3m2!2i4!5b1"
              "!6m6!1m2!1i86!2i86!1m2!1i408!2i200!7m46!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e3!2b0!3e3!"
              "1m3!1e4!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e3!2b1!3e2!1m3!1e9!2b1!3e2!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e"
              "10!2b0!3e4!2b1!4b1!9b0!22m6!1sa9fVWea_MsX8adX8j8AE%3A1!2zMWk6Mix0OjExODg3LGU6MSxwOmE5ZlZXZWFfTXNYOGFkWDh"
              "qOEFFOjE!7e81!12e3!17sa9fVWea_MsX8adX8j8AE%3A564!18e15!24m15!2b1!5m4!2b1!3b1!5b1!6b1!10m1!8e3!17b1!24b1!"
              "25b1!26b1!30m1!2b1!36b1!26m3!2m2!1i80!2i92!30m28!1m6!1m2!1i0!2i0!2m2!1i458!2i976!1m6!1m2!1i1075!2i0!2m2!"
              "1i1125!2i976!1m6!1m2!1i0!2i0!2m2!1i1125!2i20!1m6!1m2!1i0!2i956!2m2!1i1125!2i976!37m1!1e81!42b1!47m0!49m1"
              "!3b1"
    }

    search_url = "https://www.google.de/search?" + "&".join(k + "=" + str(v) for k, v in params_url.items())

    return search_url


def parse_populartimes(resp, address):
    data = resp.split('/*""*/')[0]

    # find eof json
    jend = data.rfind("}")
    if jend >= 0:
        data = data[:jend + 1]

    jdata = json.loads(data)["d"]
    jdata = json.loads(jdata[4:])

    # check if proper and numeric address, i.e. multiple components and street number
    is_proper_address = any(char.isspace() for char in address.strip()) and any(char.isdigit() for char in address)

    # heuristic based on proper_address, which may fail
    address_index = 0 if is_proper_address else 1
    info = index_get(jdata, 0, 1, address_index, 14)
    # try the other possibility if the heuristic failed
    if info is None:
        info = index_get(jdata, 0, 1, 1 - address_index, 14)

    rating = index_get(info, 4, 7)
    rating_n = index_get(info, 4, 8)

    place_id = index_get(info, 78)
    popular_times = index_get(info, 84, 0)

    # current_popularity is also not available if popular_times isn't
    current_popularity = index_get(info, 84, 7, 1)

    time_spent = index_get(info, 117, 0)

    # extract wait times and convert to minutes
    if time_spent:
        nums = [float(f) for f in re.findall(r'\d*\.\d+|\d+', time_spent.replace(",", "."))]
        contains_min, contains_hour = "min" in time_spent, "hour" in time_spent or "hr" in time_spent

        time_spent = None

        if contains_min and contains_hour:
            time_spent = [nums[0], nums[1] * 60]
        elif contains_hour:
            time_spent = [nums[0] * 60, (nums[0] if len(nums) == 1 else nums[1]) * 60]
        elif contains_min:
            time_spent = [nums[0], nums[0] if len(nums) == 1 else nums[1]]

        time_spent = [int(t) for t in time_spent]

    return PopularTimes(place_id, rating, rating_n, popular_times, current_popularity, time_spent)


def get_populartimes_by_name_addr(name, address) -> PopularTimes:
    """
    request information for a place and parse current popularity
    :param name: name string
    :param address: address string for checking if numbered address
    :return:
    """
    # logging.info("searchterm: " + search_url)
    search_url = build_populartimes_url(name, address)

    # noinspection PyUnresolvedReferences
    resp = requests.get(search_url, headers=USER_AGENT, verify=False).text

    return parse_populartimes(resp, address)