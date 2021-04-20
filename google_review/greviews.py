#!/usr/bin/env python

from urllib.parse import quote
import requests
import re
import time
import json
import base64

"""
Fetch Google reviews information for a given Google Places Place ID.

See Google Places API on how to retrieve the place id:
https://developers.google.com/maps/documentation/places/web-service/overview

Example usage:

  import greviews
  
  topics = greviews.get_review_topics("ChIJAWkAqNL1t4kRlm4slspOSXo")
  [(t['name'], t['contribution_stats']['num_reviews']) for t in topics]
"""

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36")
REVIEWS_SEARCH_URL = "https://search.google.com/local/reviews?placeid={}"
REVIEWS_API_URL = ("https://www.google.com/async/reviewDialog?cshid={}&gl=us&hl=en-US&yv=3&async=feature_id:{}"
                   ",review_source:All%20reviews,sort_by:qualityScore,is_owner:false,_pms:s,_fmt:json")

# extractors for feature IDs in Google URLs

# used in normal Google search URLs
LRD_EXTRACTOR = re.compile('#lrd=([^,]+)')

# used in Google travels review URL, e.g.
#   https://www.google.com/travel/hotels/entity/CgsIiPGG2O786MCqARAB/reviews?
#   g2lb=2502548,2503781,4258168,4270442,4306835,4317915,4328159,4371335,4401769,4419364,4472151,
#   4482438,4486153,4491350,4509341,4515404,4517258,4536454,4540817,4270859,4284970,4291517&hl=en-US
#   &gl=us&ssta=1&grf=EmQKLAgOEigSJnIkKiIKBwjlDxAEGBUSBwjlDxAEGBYgADAeQMoCSgcI5Q8QBBgTCjQIDBIwEi6yAS
#   sSKQonCiUweDg5YzVhNDVjYWE0NzNmZjM6MHhhYTgxYTNlNmViMDFiODg4&rp=EIjxhtju_OjAqgE4AkAASAHAAQI&ictx=1
GRF_EXTRACTOR = re.compile('\Wgrf=([^&]+)')


def parse_reviews_response(r):
    if r.status_code == 200:
        data = json.loads(r.text[5:])
        if 'reviews' in data['localReviewsDialogProto'] and \
                'topics' in data['localReviewsDialogProto']['reviews']:
            return data['localReviewsDialogProto']['reviews']['topics']
        return []
    else:
        raise RuntimeError("Failed to get reviews response.")


def extract_feature_id(url):
    """
    Extract the "feature ID", which can be used to fetch reviews from Google (using the reviewDialog)
    API, from the redirect URL.

    This method uses two heuristic rules to extract the feature IDs:

     1) Most URLs are regular Google search URLs, where the feature ID can be identified as "#lrd=xxx"
     2) For places that are hotels, we need an alternative logic to extract the feature ID, by extracting
     the "grf" query parameter, conduct base64 decoding, and extract the feature ID from the decoded value.

    :param url: The redirect URL returned by Google when accessing search.google.com/local/reviews
    :return: The extracted feature ID
    """
    lrd_match = LRD_EXTRACTOR.search(url)
    if lrd_match:
        return lrd_match.group(1)
    else:
        # for some place ID, the redirected URL is the Google hotels review
        # URL, so we need an alternative extraction method
        grf_match = GRF_EXTRACTOR.search(url)
        if grf_match:
            grf = base64.b64decode(grf_match.group(1)).split(b'\n')[-1].decode('utf8')
            if grf.startswith('%0x'):
                return grf[1:]
        else:
            raise RuntimeError("Failed to extract feature id from the redirect URL.")


def get_review_topics(place_id):
    r = requests.get(REVIEWS_SEARCH_URL.format(place_id),
                     headers={'user-agent': USER_AGENT})

    if r.status_code == 200:
        redirect_url = r.headers['Location']
        feature_id = extract_feature_id(redirect_url)

        # nano seconds since epoch
        timestamp = int(time.time() * 1e6)
        reviews_url = REVIEWS_API_URL.format(timestamp, quote(feature_id))

        reviews_resp = requests.get(reviews_url, headers={
            'referer': redirect_url,
            'user-agent': USER_AGENT
        })

        return parse_reviews_response(reviews_resp)

    else:
        raise RuntimeError(f"Request failed with HTTP status {r.status_code}")
