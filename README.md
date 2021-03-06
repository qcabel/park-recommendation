An integrated park ranking app to recommend hidden gems around you. 
See a demo at http://ec2-3-233-234-54.compute-1.amazonaws.com:5000/# (currently available for locations near Philadelphia and NYC)

----
### Part I. Data collection 
* Parks selection and their basic information using Google Places API

Selected parks include 4600 state and city parks around Philadelphia and New York City. 
Google place IDs were first searched around the two cities `fetch_park_ids.py` and 
park details were acquired subsequently `fetch_details.py`. 
Utility functions `get_id.py` were adapted from [PopularTimes](https://github.com/m-wrzr/populartimes). 

Other information about these parks were gathered through 
[FourSquare Places API](https://developer.foursquare.com/docs/places-api/) `park_type_per_FourSquare_API.ipynb`, 
[iNaturalist API](https://www.inaturalist.org/pages/api+reference) `inaturalist/explore_inaturalist_API.ipynb` (biodiversity)
, and Wikipedia `get_PA_state_parks.ipynb` (state park information). 

More attributes were extracted by analyzing over 200,000 Google Reviews through topic modeling (see `google_review/`). 


* Live visitor traffic data and hourly weather information

Hourly bulk scrape jobs were set up to retrieve Google Maps Live Popularity data `popular_times_scraper.py`
(about 1,500,000 entries from March to May 2021 in over 2000 parks).

Observed weather information at the city address level paired with the live traffic data was gathered using 
[visualcrossing](https://www.visualcrossing.com/weather-api) Timeline Weather API `get_weather_data.ipynb`

Hourly data were aggregated in preparation for model training 
`aggregate_curr_popularity_data.py` and `aggregate_weather_info.py`.

### Part II. Hourly visitor traffic estimation

Random forest regression was used to estimate hourly visitor traffic for each park. 
The individual park traffic is modeled as a random effect 
with the goal to gauge the general popularity of the park 
while regressing out the effect of visiting time, weather, and park attributes
(such as type, rating and average popular times). See `estimate_park_visitor_traffic.ipynb` for details. 

In general, if a highly rated park has less visitor traffic comparing to a similar park, 
it would be highly recommended.

Although Google Maps Live Popularity provides reasonable signals on park visitor traffic, 
the caveat of using it as a somewhat "ground truth" is also obvious. 
Since it's not the raw data that is provided here, 
when Google adjusts its way of normalizing such measure,
the same values across two months are not necessarily indicating the same traffic.
For example, at the beginning of May, most of the Live Popularity data were clapped between 0 and 100, 
which was not the case previously. 
To account for this change, only data before May 5th were used in model fitting. 

### Part III. Park rank

Heuristic ranking rules were used to rank the parks based on visitor **traffic**, general **rating**, and **diversity** scores
`parkFinderZip/parkrank.py`.


### Part IV. Zip code based park filter and app deployment

A subset of parks will be considered for ranking given the user provided zip code `find_zipcode_nearby_parks.ipynb`. 
The app is available for 1146 unique zip codes near the region of Philadelphia and New York City. 
Candidate parks are within 40 miles of the zip code, and first 25 recommended parks are shown. 

The web app interface can be found at `parkFinderZip/zipMap.html` and 
deployed through Flask `parkFinderZip/park_finder_server.py`.
