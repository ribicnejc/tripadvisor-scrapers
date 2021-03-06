import re
import time
import json

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.action_chains import ActionChains

from masters import settings
from masters.data_structures.Review import Review
from masters.utils import unicode_utils, coordinate_utils, file_utils
from masters.utils.logger_utils import Logger
from masters.utils.timer_utils import Timer


def exception_handler(f):
    def wrapper(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            return result
        except NoSuchElementException as e:
            Logger.log_it('Element not found' + str(e))
        except Exception as e:
            Logger.log_it(str(e))

    return wrapper


def stale_decorator(f):
    def wrapper(*args, **kwargs):
        counter = 3
        while counter != 0:
            try:
                result = f(*args, **kwargs)
                return result
            except StaleElementReferenceException:
                Logger.log_it("Stale element... retrying")
                counter -= 1
            except WebDriverException:
                Logger.log_it("Web driver exception... retrying")
                counter -= 1
            time.sleep(1)
        return None

    return wrapper


class GeckoReviewSpider(object):
    def __init__(self, url):
        Logger.log_it("##########################################")
        self.timer = Timer()
        self.timer.start_timer()
        options = Options()
        options.headless = settings.HEADLESS_MODE

        options.add_argument("start-maximized")
        # options.add_argument("disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-application-cache')
        options.add_argument('--disable-gpu')
        options.add_argument("--disable-dev-shm-usage")

        firefox_profile = webdriver.FirefoxProfile()
        firefox_profile.set_preference('permissions.default.image', 2)
        firefox_profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', 'false')

        # self.driver = gecko_utils.get_gecko_driver()
        self.driver = webdriver.Firefox(options=options, firefox_profile=firefox_profile)

        # driver.add_cookie({'name': 'TALanguage', 'value': 'ALL'})
        try:
            self.driver.get(url)
        except:
            self.driver.close()
            return
        # self.driver.implicitly_wait(0.5)
        # self.wait = WebDriverWait(self.driver, 5)

    @exception_handler
    def select_all_languages(self):
        time.sleep(1)
        Logger.log_it("Selecting all languages")
        review_title = self.driver.find_element_by_css_selector("h2._1VLgXtcm")
        y = review_title.location['y']
        self.driver.execute_script("window.scrollTo(0, " + str(y) + ");")
        time.sleep(0.2)
        all_languages = self.driver.find_element_by_css_selector('label.bUKZfPPw')
        ActionChains(self.driver).move_to_element(all_languages).click().perform()
        time.sleep(1)

    @stale_decorator
    def is_all_languages_selected(self):
        all_languages = self.driver.find_element_by_xpath('//input[@id="filters_detail_language_filterLang_ALL"]')
        return all_languages.is_selected()

    def is_other_page(self):
        Logger.log_it("Checking if its the other page")
        try:
            tmp = self.driver.find_element_by_css_selector('h1._3QHreJVJ').text
            Logger.log_it("It is. Skipping.")
            return True
        except:
            Logger.log_it("It is not. Scraping.")
            return False

    def is_not_ram_capable(self, parent_url):
        Logger.log_it("Checking if machine is RAM capable")
        try:
            review_last_page = self.driver.find_elements_by_css_selector('div.pageNumbers a.pageNum')[-1].text
        except Exception as e:
            review_last_page = "None"

        RAM = 4500
        max_pages = (RAM / 300) * 100
        Logger.log_it("Performance: Pages limit %s | Pages to scrap %s" % (max_pages, review_last_page))
        if review_last_page is None or review_last_page == "None":
            return False
        if int(review_last_page) > max_pages:
            Logger.log_it("Skipping page")
            Logger.log_performance_location(parent_url)
            return True
        return False

    def has_next_review_page(self):
        Logger.log_it("Checking if next page exists")
        return not (self.get_next_page_url() is None)

    def get_next_page_url(self):
        try:
            next_url = self.driver.find_element_by_css_selector('div.ui_pagination a.next').get_attribute("href")
        except:
            next_url = None
        f = lambda x: "None" if next_url is None else next_url
        var = f(next_url)
        if var == "None":
            Logger.log_it("Next page doesn't exists")
            return next_url
        Logger.log_it("Next url exists: " + f(next_url))
        return next_url

    def next_page(self):
        # time.sleep(0.2)
        current_page = self.driver.find_element_by_css_selector('span.pageNum.current.disabled')
        next_page = self.driver.find_elements_by_css_selector('div.pageNumbers a.pageNum')
        current_page = current_page.text
        pages = self.driver.find_elements_by_css_selector('div.pageNumbers a.pageNum')
        for page in pages:
            page_num = page.text
            if int(page_num) > int(current_page):
                next_page = page
                break
        y = next_page.location['y']
        self.driver.execute_script("window.scrollTo(0, " + str(y - 200) + ");")
        time.sleep(0.2)
        ActionChains(self.driver).move_to_element(next_page).click().perform()
        time.sleep(0.4)

    @stale_decorator
    def scrap_page(self, parent_url, scraped_pages, start_time, root_url):
        time.sleep(0.2)
        review_location_name = unicode_utils.unicode_to_string(
            self.driver.find_element_by_css_selector('div h1.ui_header').text)
        try:
            review_current_page = unicode_utils.unicode_to_string(
                self.driver.find_element_by_css_selector('div.pageNumbers span.current').text)
        except NoSuchElementException as e:
            review_current_page = "None"

        try:
            review_last_page = self.driver.find_elements_by_css_selector('div.pageNumbers a.pageNum')[-1].text
        except Exception as e:
            review_last_page = "None"

        review_location_type = unicode_utils.unicode_list_to_string(
            map(lambda x: x.text, self.driver.find_elements_by_css_selector('div._3RTCF0T0 a._1cn4vjE4')))
        review_location_breadcrumbs = unicode_utils.unicode_list_to_string(
            map(lambda x: x.text, self.driver.find_elements_by_css_selector('div ul.breadcrumbs li.breadcrumb a span')))
        try:
            review_location_rate = unicode_utils.unicode_rating_to_string(
                self.driver.find_element_by_css_selector('div._1NKYRldB span.ui_bubble_rating').get_attribute('class'))
        except:
            review_location_rate = "0"

        current_url = self.driver.current_url
        current_url = current_url.replace(root_url, "")

        pattern = re.compile(r"(?<=recentHistoryList', )(.*)(?=\);)")
        html_content = self.driver.find_element_by_xpath("//*").get_attribute('outerHTML')
        tripadvisor = re.search(pattern, html_content)
        tripadvisor_data = "None"
        for group in tripadvisor.groups():
            if "coords" in group:
                tripadvisor_data = group
                break
        tripadvisor_data = json.loads(tripadvisor_data)
        location_lat, location_lng = coordinate_utils.parse_json_to_coords(tripadvisor_data)

        extra = []

        grades = self.driver.find_elements_by_css_selector('div.ui_column ul._2lcHrbTn li.ui_checkbox._3gEj_Jb5')
        for grade in grades:
            key = grade.find_element_by_css_selector('label').text
            try:
                value = grade.find_element_by_css_selector('span._3fVK8yi6').text
            except:
                value = None
            if value is None:
                break
            extra.append(key + " : " + value)

        extra = unicode_utils.unicode_list_to_string(extra)
        if not extra:
            extra = "None"

        reviews = []
        for review in self.driver.find_elements_by_css_selector('div.main_content div.Dq9MAugU'):
            review_id = unicode_utils.unicode_to_string(
                review.find_element_by_css_selector('div.oETBfkHU').get_attribute('data-reviewid'))
            review_date = unicode_utils.unicode_date_v2_to_string_number(
                review.find_element_by_css_selector('div._2fxQ4TOx span').text)
            try:
                review_experience_date = unicode_utils.unicode_date_v3_to_string_number(
                    review.find_element_by_css_selector('div._27JpaCjl span').text.split(':')[1])
            except Exception:
                review_experience_date = review_date

            review_rate = unicode_utils.unicode_rating_to_string(
                review.find_element_by_css_selector('span.ui_bubble_rating').get_attribute('class'))

            user_name = unicode_utils.unicode_to_string(review.find_element_by_css_selector('a.ui_header_link').text)
            user_link = unicode_utils.unicode_to_string(
                review.find_element_by_css_selector('a.ui_header_link').get_attribute('href'))
            user_id = unicode_utils.unicode_string_to_md5(user_link)

            review_data = Review(review_location_name,
                                 review_current_page,
                                 review_last_page,
                                 review_location_type,
                                 review_location_breadcrumbs,
                                 review_location_rate,
                                 location_lat,
                                 location_lng,
                                 review_id,
                                 review_date,
                                 review_experience_date,
                                 review_rate,
                                 user_name,
                                 user_link,
                                 user_id,
                                 extra,
                                 parent_url)
            reviews.append(review_data)

        no_reviews = False
        if len(reviews) == 0:
            review_data = Review(review_location_name,
                                 review_current_page,
                                 review_last_page,
                                 review_location_type,
                                 review_location_breadcrumbs,
                                 review_location_rate,
                                 location_lat,
                                 location_lng,
                                 "None",
                                 "None",
                                 "None",
                                 "None",
                                 "None",
                                 "None",
                                 "None",
                                 extra,
                                 parent_url)
            reviews.append(review_data)
            no_reviews = True

        if review_location_name is not None:
            review_location_name = review_location_name.replace("/", "").replace(",", "").replace(" ", "_")

        if review_current_page is not None:
            review_current_page = review_current_page.replace("/", "")

        if review_current_page == '1':
            last_scraped_page_url = file_utils.get_last_scraped_page_url(review_location_name, current_url)
            if last_scraped_page_url is not None:
                next_review_page_url = last_scraped_page_url

        filename = 'scraped_data/data_reviews/%s/reviews-%s-%s.csv' % (
            settings.COUNTRY, review_location_name, review_current_page)
        with open(filename, 'w') as f:
            f.write(Review.get_csv_header_v2())
            for review in reviews:
                f.write(review.get_csv_line())
            f.close()
        Logger.log_it('Saved %s reviews to file %s' % (len(reviews), filename))

        try:
            current_time = time.time()
            average_time = (current_time - start_time) / int(scraped_pages)
            pages_left = int(review_last_page) - int(review_current_page)
            secs = pages_left * average_time
            mins = (pages_left * average_time) / 60
            hours = (pages_left * average_time) / 3600
            Logger.log_it('Reviews: %s/%s | %s seconds left | %s minutes left | %s hours left' % (
                review_current_page, review_last_page, secs, mins, hours))
        except:
            Logger.log_it('Reviews: %s/%s' % (review_current_page, review_last_page))
        if no_reviews:
            Logger.log_it("Location had no reviews. None values with coords were collected.")

    def continue_scraping(self):
        # self.driver.execute_script()
        # https://www.tripadvisor.com/Attraction_Review-g274887-d276817-Reviews-or10760-Hungarian_Parliament_Building-Budapest_Central_Hungary.html
        self.driver.execute_script("document.getElementByClassName('pageNumbers').")

        script = """
            var a_element = document.createElement('a');
            a_element.setAttribute('href', "")
        """

        # js.executeScript("document.getElementById('myDiv').appendChild(document.createTextNode(' New Element'))")

    def refresh_page(self):
        Logger.log_it("Refreshing")
        self.driver.refresh()

    def stop_spider(self):
        Logger.log_it("-------------------------------------------")
        self.driver.close()
        self.timer.stop_timer()
        Logger.log_it(self.timer.print_time())


def get_coordinates(url):
    chrome_options = Options()
    if settings.HEADLESS_MODE:
        chrome_options.add_argument("--headless")
    # chrome_options.binary_location = '/opt/google/chrome/google-chrome'
    # service_log_path = "{}/chromedriver.log".format("/home/nejc/Desktop/scrapers/trip/")
    service_args = ['--verbose']

    driver = webdriver.Chrome(
        chrome_options=chrome_options,
        service_args=service_args,
        # service_log_path=service_log_path
    )
    driver.get(url)
    driver.implicitly_wait(5)

    # Select all languages
    driver.find_element_by_css_selector('div.choices div.ui_radio label.label').click()

    driver.implicitly_wait(3)

    coord_url = driver.find_element_by_css_selector("div.staticMap img").get_attribute("src")
    print(coord_url)
    driver.close()
    return coord_url
