import requests
import bs4
import g4f  # Make sure to have g4f installed
import json
import logging
import re

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

def parse_or_retry_json_response(llm_response: str, context_text: str, max_retries: int = 2, model_name: str = "gpt-4o"):
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
        llm_response = response  # Assuming response is a string; adjust if it's a dict.
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

if __name__ == "__main__":
    links = [
        "https://github.com/engineer1469",
        "https://www.instagram.com/seppbeld/"
    ]
    person_profile = getPersonInfo(links)
    logging.info("Extracted Profile Summary:")
    logging.info(person_profile)
