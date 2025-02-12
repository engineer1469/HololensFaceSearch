import requests
import time
import bs4
import g4f
import json
import logging
import re
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Configure logging
logging.basicConfig(filename='osintUtils.log', level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s:%(message)s')


def getInfoFromPage(url):
    """
    Fetch HTML content from the given URL and return a BeautifulSoup object.
    """
    try:
        logging.debug(f"Fetching URL: {url}")
        page = requests.get(url, timeout=10)
        page.raise_for_status()
        soup = bs4.BeautifulSoup(page.content, "html.parser")
        logging.debug(f"Successfully fetched and parsed URL: {url}")
        return soup
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return None


def getAllPages(links):
    """
    Takes a list of URLs and returns a list of BeautifulSoup objects for each successful fetch.
    """
    logging.debug("Starting to fetch all pages.")
    all_pages = []
    for link in links:
        page = getInfoFromPage(link)
        if page:
            all_pages.append(page)
    logging.debug("Finished fetching all pages.")
    return all_pages


def extractTextFromPages(all_pages):
    """
    Given a list of BeautifulSoup objects, extracts and returns concatenated text.
    """
    logging.debug("Starting to extract text from all pages.")
    combined_text = ""
    for soup in all_pages:
        page_text = soup.get_text(separator="\n", strip=True)
        combined_text += page_text + "\n\n"
    logging.debug("Finished extracting text from all pages.")
    return combined_text


def extract_json(text):
    """
    Extracts the first JSON object found in a string using a regex.
    """
    json_regex = re.compile(r'\{.*\}', re.DOTALL)
    match = json_regex.search(text)
    if match:
        return match.group(0)
    return None


def parse_or_retry_json_response(llm_response: str, context_text: str, max_retries: int = 2, model_name: str = "deepseek-r1"):
    """
    Tries to parse the llm_response as JSON. If it fails, it re-prompts the LLM,
    requesting strictly valid JSON only.
    """
    for attempt in range(max_retries + 1):
        try:
            logging.debug(f"Attempt {attempt + 1}: Trying to extract and parse JSON from LLM response.")
            json_str = extract_json(llm_response)
            if not json_str:
                raise json.JSONDecodeError("No JSON object found", llm_response, 0)
            data = json.loads(json_str)
            logging.debug("Successfully parsed JSON from LLM response.")
            return data
        except json.JSONDecodeError as e:
            logging.warning(f"Attempt {attempt + 1}: Failed to parse JSON: {e}")
            if attempt == max_retries:
                logging.error("Failed to extract valid JSON after multiple attempts.")
                return None

            correction_prompt = f"""
Your previous response did not contain strictly valid JSON.
Please provide only the JSON object as output with no additional commentary or markdown formatting.
Follow exactly this JSON structure:
{{
  "name": "...",
  "age": "...",
  "job": "...",
  "location": "...",
  "education": "...",
  "interests": ["...", "..."]
}}
Context: {context_text}
Your previous response:
{llm_response}
"""
            try:
                logging.debug("Re-prompting the LLM for JSON correction.")
                corrected_response = g4f.ChatCompletion.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": correction_prompt}
                    ],
                )
                llm_response = corrected_response
                logging.debug("Received corrected response from the LLM.")
            except Exception as ex:
                logging.error(f"Error calling LLM for JSON correction: {ex}")
                return None
    return None


def getPersonInfo(links):
    logging.debug("Starting to get person info.")
    all_pages = getAllPages(links)
    combined_text = extractTextFromPages(all_pages)

    base_prompt = """
You are given text from multiple web pages where a certain person's image appeared.
Your task is to build a concise JSON profile about this person based on any matching information you find in these pages.
Make sure to only include details about the individual.
The JSON should follow this structure and nothing else:

{
  "name": "...",
  "age": "...",
  "job": "...",
  "location": "...",
  "education": "...",
  "interests": ["...", "..."]
}

Provide only the JSON object without any additional commentary or markdown formatting.
If any field is unknown or cannot be found, omit it.
"""

    user_input_text = f"{base_prompt}\n\nHere is the text from the webpages:\n{combined_text}\n"

    try:
        logging.debug("Calling the LLM.")
        response = g4f.ChatCompletion.create(
            model="deepseek-r1",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_input_text}
            ],
        )
        llm_response = response  # Adjust if the response is a dict
        logging.debug(f"Received response from the LLM: {llm_response}")
    except Exception as e:
        logging.error(f"Error calling the LLM: {e}")
        return None

    person_profile = parse_or_retry_json_response(
        llm_response=llm_response,
        context_text=combined_text,
        max_retries=2,
        model_name="gpt-4o"
    )
    logging.debug("Finished getting person info.")
    return person_profile


def getLinksFromFace(face_image_path):
    """
    Given a face image, uses facial recognition to find the person's online presence.
    """
    logging.debug(f"Starting to get links from face: {face_image_path}")
    # Placeholder for the actual implementation
    links = [
        "https://github.com/engineer1469",
        "https://www.instagram.com/seppbeld/"
    ]
    return links


def prepBrowser():
    """
    Prepares a browser for use with Selenium.
    It navigates to the login page and:
      - If the login form is found, it enters credentials.
      - If an email verification screen appears, it waits (up to 2 minutes)
        for the user to complete verification.
      - If the login form isn’t found (i.e. already logged in), it skips login.
    Returns the browser instance.
    """
    # Get credentials from file
    try:
        with open("creds.txt", "r") as f:
            creds = f.read().splitlines()
            username = creds[0]
            password = creds[1]
    except Exception as e:
        logging.error(f"Error reading credentials: {e}")
        return None

    # Use a dedicated Chrome profile to store the login session (universal path on Windows)
    chrome_options = Options()
    local_appdata = os.environ.get("LOCALAPPDATA")
    user_data_dir = os.path.join(local_appdata, "Google", "Chrome", "User Data", "Default")
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")

    try:
        logging.debug("Starting to prepare browser.")
        browser = webdriver.Chrome(options=chrome_options)
        browser.get("https://pimeyes.com/en/login")
        logging.debug("Finished preparing browser.")
        time.sleep(2)
    except Exception as e:
        logging.error(f"Error launching browser: {e}")
        return None

    try:
        # Try to locate the login form input
        login_input = WebDriverWait(browser, 5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#login-container > div > div > form > div:nth-child(2) > input")
            )
        )
        logging.debug("Login form found; proceeding with login.")
        login_input.clear()
        login_input.send_keys(username)
        login_input.send_keys(u'\ue004')  # Tab key

        # Locate the password input (assumed to be the next div)
        password_input = browser.find_element(
            By.CSS_SELECTOR, "#login-container > div > div > form > div:nth-child(3) > input"
        )
        password_input.clear()
        password_input.send_keys(password)
        password_input.send_keys(u'\ue007')  # Enter key
        time.sleep(10)

        # Check if an email verification screen appears by locating a unique element.
        try:
            verification_input = WebDriverWait(browser, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#content > div > div.digits > input[type='tel']:nth-child(1)")
                )
            )
            logging.debug("Email verification screen detected. Waiting up to 2 minutes for dashboard to load.")
            print("Please check your email, enter the verification code in the browser, and complete verification. Waiting up to 2 minutes...")
            # Wait until a dashboard element (only present after successful login) is found.
            WebDriverWait(browser, 120).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#sidebar-navigation > div > div > nav > div:nth-child(1) > a > span")
                )
            )
        except TimeoutException:
            logging.debug("No verification screen detected or dashboard did not load within 2 minutes after login.")
    except TimeoutException:
        logging.debug("Login form not found. Assuming already logged in.")
        try:
            # Wait for a known dashboard element to confirm that session is active.
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#sidebar-navigation > div > div > nav > div:nth-child(1) > a > span")
                )
            )
        except TimeoutException:
            logging.error("Dashboard not loaded even though login form was not found.")
    except Exception as e:
        logging.error(f"Error during login procedure: {e}")

    return browser


if __name__ == "__main__":
    browser = prepBrowser()
    if browser:
        logging.debug("Browser prepared successfully.")
    else:
        logging.error("Failed to prepare browser.")
    CurrentPath = os.path.dirname(os.path.realpath(__file__))
    Facepath = os.path.join(CurrentPath, "received_face.jpg")

    # Example usage:
    # links = getLinksFromFace(Facepath)
    # person_profile = getPersonInfo(links)
    # logging.info("Extracted Profile Summary:")
    # logging.info(person_profile)
    
    # Keep the browser open so you can inspect the logged-in state
    input("Press Enter to exit and close the browser...")
    browser.quit()
