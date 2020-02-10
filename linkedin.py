import logging
import os, re, time, pickle
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotVisibleException


class LinkedInClient:
    LOGIN_URL = "https://www.linkedin.com/uas/login"
    COOKIE_JAR = os.path.join(os.getcwd(), ".cookies.pkl")

    def __init__(self, email, password, webdriver=None, timeout=5, save_cookie=True):
        if webdriver is None:
            raise ValueError('You must specify a webdriver')

        self.email = email
        self.password = password
        self.webdriver = webdriver
        self.timeout = timeout
        self.save_cookie = save_cookie

    def __enter__(self):
        # dirty hack, for some reason `add_cookie()` doesn't work in phantomjs
        self.__login(True if self.webdriver.capabilities['browserName'] == 'phantomjs' else False)

        return self

    def __exit__(self, type, value, traceback):
        self.webdriver.quit()

    def __login(self, bypass_cookies=False):
        self.webdriver.get(LinkedInClient.LOGIN_URL)

        # let's try to login with a cookie first
        if self.save_cookie and not bypass_cookies:
            try:
                cookies = pickle.load(open(LinkedInClient.COOKIE_JAR, "rb"))
                if cookies:
                    for cookie in cookies:
                        if 'expiry' in cookie:
                            del cookie['expiry']
                            
                        self.webdriver.add_cookie(cookie)

                    logging.info("Attempting to log in with saved cookies from %s ", LinkedInClient.COOKIE_JAR)
                    return
            except FileNotFoundError:
                pass

        self.webdriver.find_element_by_id("username").send_keys(self.email)
        self.webdriver.find_element_by_id("password").send_keys(self.password)
        self.webdriver.find_element_by_css_selector(".login__form_action_container button").submit()

        try:
            wait = WebDriverWait(self.webdriver, self.timeout)
            wait.until_not(lambda driver: driver.current_url == LinkedInClient.LOGIN_URL)

            user_id = self.__get_user_id()
            if user_id is not None:
                logging.info("Successfully logged in to LinkedIn. Identifier: %s", user_id)

                # save cookies for next time - delicious
                if self.save_cookie:
                    pickle.dump(self.webdriver.get_cookies(), open(LinkedInClient.COOKIE_JAR, "wb"))
                    logging.info("Saving cookies to %s", LinkedInClient.COOKIE_JAR)
            else:
                logging.warning("Successfully logged in to LinkedIn but failed to extract your identifier.")
        except TimeoutException:
            logging.error("Login failed. Check your username (%s) and password.", self.email)

    def get_endorsements(self, profile_url):
        skills = list()
        self.webdriver.get(profile_url)
        profile_handle = self.webdriver.current_window_handle

        # dismiss the "view with the app" bullshit (we're using iOS UA)
        try:
            self.__scroll_to_bottom()
            self.webdriver.find_element_by_css_selector("button.pv-gta-overlay__dismiss").click()
        except (NoSuchElementException, ElementNotVisibleException):
            pass

        # check we are logged in
        user_id = self.__get_user_id()
        if user_id is None:
            logging.warning("Cookies have expired, attempting to log in again...")
            self.__login(bypass_cookies=True)

        # check if the profile is valid
        try:
            self.webdriver.find_element_by_css_selector(".profile-unavailable")
            logging.error("{} appears to be an invalid LinkedIn profile.".format(profile_url))
            return
        except NoSuchElementException:
            pass

        time.sleep(1)
        name = self.webdriver.find_element_by_css_selector(".pv-top-card--list > li").text
        dist = "self" if user_id in profile_url else self.webdriver.find_element_by_css_selector(".pv-top-card__distance-badge .dist-value").text.strip()

        if dist is "":
            logging.warning("%s is not in your network. We may not be able to retrieve any endorsements...", name)

        # do we have any endorsements to parse?
        #try:
        #data = self.webdriver.find_element_by_css_selector("#ember121")
        #logging.info("data:%s", data)
        self.webdriver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        self.webdriver.execute_script("arguments[0].scrollIntoView();", self.webdriver.find_element_by_css_selector("#ember89"))
        #sself.webdriver.execute_script("arguments[0].scrollIntoView();", self.webdriver.find_element_by_css_selector("#ember121"))
        time.sleep(3)
        self.webdriver.find_element_by_css_selector("button.pv-skills-section__additional-skills").click()
        self.webdriver.execute_script("arguments[0].scrollIntoView();", self.webdriver.find_element_by_css_selector(".pv-skill-categories-section__top-skills"))
            #self.webdriver.execute_script("window.scrollBy(0, -200);") # backin' up, backin' up
        #except NoSuchElementException:
        #    logging.error("%s doesn't have any endorsements or has hidden them!", name)
        #    return

        skills_elements = self.webdriver.find_elements_by_css_selector("li.pv-skill-category-entity")
        logging.info("Fetching %s skills for %s (%s).", len(skills_elements), name, ("0" if dist == "" else dist) if dist is not None else "self")

        for element in skills_elements:
            skill_name_element = element.find_element_by_class_name("pv-skill-category-entity__name")
            skill_name = skill_name_element.text
            endorsers = list()
            endorsement_count = 0

            try:
                endorsement_count = int(re.sub(r"\D", "", element.find_element_by_class_name("pv-skill-category-entity__endorsement-count").text))
            except NoSuchElementException:
                pass

            if endorsement_count > 0:
                logging.info("Processing %s (%s endorsements).", skill_name, endorsement_count)

                skill_anchor = skill_name_element.find_element_by_tag_name('a')
                ActionChains(self.webdriver).key_down(Keys.SHIFT).click(skill_anchor).key_up(Keys.SHIFT).perform()
                self.webdriver.switch_to_window(self.webdriver.window_handles[-1])

                #waiter = WebDriverWait(self.webdriver, self.timeout)
                #waiter.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".pv-profile-detail__content")))
                #self.__scroll_to_bottom(self.webdriver.find_element_by_css_selector(".pv-profile-detail__content"))
                time.sleep(5)

                for endorser_element in self.webdriver.find_elements_by_css_selector(".pv-endorsement-entity__link"):
                    endorsers.append(endorser_element.find_element_by_css_selector(".pv-endorsement-entity__name--has-hover").text)

                logging.info(endorsers)

                self.webdriver.close()
                self.webdriver.switch_to_window(profile_handle)

            skills.append({"name": skill_name, "endorsements": len(endorsers), "endorsers": endorsers})

        return {"name": name, "skills": skills}

    def __scroll_to_bottom(self, element=None, timeout=0.5):
        def get_height():
            return self.webdriver.execute_script("return document.body.scrollHeight") if element is None else self.webdriver.execute_script("return arguments[0].scrollHeight", element);

        last_height = get_height()

        while True:
            if element is None:
                self.webdriver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            else:
                self.webdriver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", element)

            time.sleep(timeout)

            new_height = get_height()
            if new_height == last_height:
                break

            last_height = new_height

    def __get_user_id(self):
        matches = re.search("{\"request\":\"/voyager/api/me\",\"status\":200,\"body\":\"(.*?)\",\"method\":\"GET\"}", self.webdriver.page_source)

        if matches is not None:
            voyager_me = self.webdriver.find_element_by_id(matches.group(1)).get_attribute("innerHTML")
            user_matcher = re.search("\"publicIdentifier\":\"(.*?)\"", voyager_me)

            if user_matcher is not None:
                return user_matcher.group(1)

        return None
