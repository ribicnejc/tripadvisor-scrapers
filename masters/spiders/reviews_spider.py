import scrapy

from scrapy_splash import SplashRequest

from masters.data_structures.Review import Review
from masters.spiders_sel import reviews_sel
from masters.utils import unicode_utils, coordinate_utils


class ReviewsSpider(scrapy.Spider):
    name = "reviews"
    root_url = 'https://www.tripadvisor.com'
    current_review_coordinates = ""
    urls = [
        '/Attraction_Review-g644300-d7289577-Reviews-Tourist_Information_Centre_Kranj_House-Kranj_Upper_Carniola_Region.html',
    ]

    def request(self, url, callback):
        request_with_cookies = scrapy.Request(
            url=(self.root_url + url),
            callback=callback)
        request_with_cookies.cookies['TALanguage'] = 'ALL'
        request_with_cookies.cookies['TAReturnTo'] = '%1%%2FAttraction_Review%3FreqNum%3D1%26isLastPoll%3Dfalse%26filterLang%3DALL%26filterSegment%3D%26changeSet%3DREVIEW_LIST%26g%3D644300%26q%3D%26t%3D%26puid%3DXExNFQokH20AAYnnbnQAAACo%26preferFriendReviews%3DFALSE%26trating%3D%26d%3D7289577%26filterSeasons%3D%26waitTime%3D19%26paramSeqId%3D10'
        request_with_cookies.headers[
            'User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 12_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/71.0.3578.89 Mobile/15E148 Safari/605.1'

        return request_with_cookies

    def splash_request(self, url, callback):
        # splash
        return SplashRequest(self.root_url+url, callback, args={
            # optional; parameters passed to Splash HTTP API
            'wait': 10,
            # 'url' is prefilled from request url
            # 'http_method' is set to 'POST' for POST requests
            # 'body' is set to request body for POST requests
        },)

    def start_requests(self):
        for url in self.urls:
            self.current_review_coordinates = reviews_sel.get_coordinates(self.root_url + url)
            # yield self.splash_request(url, self.parse)
            yield self.request(url, self.parse)

    def parse(self, response):
        next_href = response.css('div.ui_pagination a.next::attr(href)').extract_first()
        if next_href is not None:
            next_review_page_url = unicode_utils.unicode_to_string(next_href)
        else:
            next_review_page_url = ""
        review_location_name = unicode_utils.unicode_to_string(
            response.css('div h1.ui_header::text').extract_first())
        review_location_tags = unicode_utils.unicode_list_to_string(
            response.css('div.ppr_priv_trip_planner_breadcrumbs').xpath(
                '//ul[@class="breadcrumbs"]/li/a/span/text()').extract())
        review_location_description_tags = unicode_utils.unicode_list_to_string(
            response.css('div.headerInfoWrapper div.detail a::text').extract())
        review_current_page = unicode_utils.unicode_to_string(
            response.css('div.pageNumbers a.current::attr(data-page-number)').extract_first())

        review_last_page = unicode_utils.unicode_to_string(
            response.css('div.pageNumbers a.last::attr(data-page-number)').extract_first())

        location_lat, location_lng = coordinate_utils.parse_google_maps_link(self.current_review_coordinates)
        place_rate = unicode_utils.unicode_to_string(response.css('span.overallRating::text').extract_first())

        reviews = []

        for review in response.css('div.review-container'):
            review_id = unicode_utils.unicode_to_string(review.css('::attr(data-reviewid)').extract_first())
            user_id = unicode_utils.unicode_user_uid_to_string(
                review.css('div.member_info div.memberOverlayLink::attr(id)').extract_first())
            review_date = unicode_utils.unicode_date_to_string_number(
                review.css('span.ratingDate::attr(title)').extract_first())
            review_rate = unicode_utils.unicode_rating_to_string(
                review.css('span.ui_bubble_rating::attr(class)').extract_first())
            username = unicode_utils.unicode_to_string(review.css('div.info_text div::text').extract_first())
            review_data = Review(review_location_name,
                                 review_location_description_tags,
                                 location_lat,
                                 location_lng,
                                 review_id,
                                 review_date,
                                 user_id,
                                 place_rate,
                                 review_rate,
                                 username)
            reviews.append(review_data)

        filename = 'scraped_data/data_reviews/reviews-%s-%s.csv' % (review_location_name, review_current_page)
        with open(filename, 'wb') as f:
            f.write(Review.get_csv_header())
            for review in reviews:
                f.write(review.get_csv_line())
        self.log('Saved file %s' % filename)
        if next_review_page_url is not "":
            yield self.request(next_review_page_url, self.parse)
