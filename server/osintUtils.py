import requests
import bs4
import g4f  # Make sure to have g4f installed
import json

def getInfoFromPage(url):
    """
    Fetches HTML content from the given URL and returns a BeautifulSoup object.
    """
    try:
        page = requests.get(url, timeout=10)
        page.raise_for_status()
        soup = bs4.BeautifulSoup(page.content, "html.parser")
        return soup
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def getAllPages(links):
    """
    Takes a list of URLs and returns a list of BeautifulSoup objects for each successful fetch.
    """
    all_pages = []
    for link in links:
        page = getInfoFromPage(link)
        if page:
            all_pages.append(page)
    return all_pages

def extractTextFromPages(all_pages):
    """
    Given a list of BeautifulSoup objects, extracts and returns concatenated text.
    You can refine this to exclude navigation links, scripts, or specific tags if you wish.
    """
    combined_text = ""
    for soup in all_pages:
        # Example extraction: just get all text
        page_text = soup.get_text(separator="\n", strip=True)
        combined_text += page_text + "\n\n"
    return combined_text

def getPersonInfo(links):
    all_pages = getAllPages(links)
    combined_text = extractTextFromPages(all_pages)

    base_prompt = """
    You are given text from multiple web pages where a certain person's image appeared. 
    Your task is to build a concise JSON profile about this person based on any matching information 
    you find in these pages. Make sure to only include details about the individual. 
    The JSON should follow this structure:

    {
      "name": "...",
      "age": "...",
      "job": "...",
      "location": "...",
      "education": "...",
      "interests": ["...", "..."]
    }

    If any field is unknown or cannot be found, you can omit it or mark it as unknown.
    """

    user_input_text = f"{base_prompt}\n\nHere is the text from the webpages:\n{combined_text}\n"

    # 1. Call the LLM (g4f):
    try:
        response = g4f.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_input_text}
            ],
        )
        # If your version returns a string:
        llm_response = response
        # If it returns a dict with 'choices', do something like:
        # llm_response = response["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error calling the LLM: {e}")
        return None

    # 2. Try to parse the LLM response or re-prompt if invalid:
    person_profile = parse_or_retry_json_response(
        llm_response=llm_response,
        context_text=combined_text,
        max_retries=2,  # you can adjust the number of retries
        model_name="gpt-4o"
    )
    return person_profile


def parse_or_retry_json_response(
    llm_response: str, 
    context_text: str, 
    max_retries: int = 2, 
    model_name: str = "gpt-4o"
):
    """
    Tries to parse the llm_response as JSON. If it fails, 
    it will prompt the LLM again, requesting valid JSON only.
    
    :param llm_response: The string returned by the LLM.
    :param context_text: The original text/context for which the LLM was supposed to generate JSON.
                         Used to provide context to the LLM on retries.
    :param max_retries: Maximum number of times to attempt re-prompting if the LLM's output is invalid JSON.
    :param model_name: The model name for g4f to use (e.g., 'gpt-4o').
    
    :return: A dictionary if valid JSON is obtained, otherwise None or the final raw string.
    """
    for attempt in range(max_retries + 1):
        try:
            # Try to parse the response as JSON
            data = json.loads(llm_response)
            return data  # If successful, return the parsed data
        except json.JSONDecodeError:
            # If we are out of retries, return None or the raw response
            if attempt == max_retries:
                print("Failed to extract valid JSON after multiple attempts.")
                return None

            # Otherwise, we re-prompt the LLM to correct its JSON
            correction_prompt = f"""
            Your previous response did not contain valid JSON. 
            Please correct your output and provide strictly valid JSON based on the following context. 
            Do not include additional commentary, just return valid JSON:
            Context: {context_text}
            Your previous (invalid) JSON response:
            {llm_response}
            """

            try:
                corrected_response = g4f.ChatCompletion.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": correction_prompt}
                    ],
                )
                # If your library returns a string directly:
                llm_response = corrected_response
                # If it returns a dict-like object, you might need something like:
                # llm_response = corrected_response["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"Error calling LLM for JSON correction: {e}")
                return None

    return None

# Example usage:
if __name__ == "__main__":
    links = [
        "https://github.com/engineer1469", 
        "https://www.instagram.com/seppbeld/"
    ]
    person_profile = getPersonInfo(links)
    print("Extracted Profile Summary:")
    print(person_profile)
