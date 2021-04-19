#!/usr/bin/env python

from urllib.parse import quote
import requests
import re
import time
import json

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36")
REVIEWS_SEARCH_URL = "https://search.google.com/local/reviews?placeid={}"
REVIEWS_API_URL = ("https://www.google.com/async/reviewDialog?cshid={}&gl=us&hl=en-US&yv=3&async=feature_id:{}"
                   ",review_source:All%20reviews,sort_by:qualityScore,is_owner:false,_pms:s,_fmt:json")

FEATURE_ID_EXTRACTOR = re.compile('#lrd=([^,]+)')


def parse_reviews_response(r):
    if r.status_code == 200:
        data = json.loads(r.text[5:])
        if 'reviews' in data['localReviewsDialogProto'] and \
                'topics' in data['localReviewsDialogProto']['reviews']:
            return data['localReviewsDialogProto']['reviews']['topics']
        return []
    else:
        raise RuntimeError("Failed to get reviews response.")


def get_review_topics(place_id):
    r = requests.get(REVIEWS_SEARCH_URL.format(place_id),
                     headers={'user-agent': USER_AGENT})

    if r.status_code == 200:
        redirect_url = r.headers['Location']
        try:
            feature_id = FEATURE_ID_EXTRACTOR.search(redirect_url).group(1)
        except AttributeError as e:
            raise RuntimeError("Failed to extract feature id from the redirect URL.")

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

# examples
# topics = greviews.get_review_topics("ChIJAWkAqNL1t4kRlm4slspOSXo")
# [(t['name'], t['contribution_stats']['num_reviews']) for t in topics]
