# """
# ui_automation_hybrid.py
# -----------------------

# A hybrid module for UI automation that first attempts to find a UI element using OCR
# and heuristic keyword matching. If a clear match is not found (or if forced), it falls
# back to using an LLM (e.g., OpenAI’s ChatCompletion API) to determine the click coordinates.

# Functions provided:
#   - capture_screen(): Capture a screenshot.
#   - get_ui_elements(): Returns OCR-detected UI elements (text plus bounding boxes).
#   - find_element_by_keyword_heuristic(keyword): Search for an element by keyword (heuristic).
#   - ask_llm_for_coordinates(action, ocr_data, extra_info=""): Asks the LLM for coordinates, given OCR data.
#   - find_element_by_keyword(keyword, force_llm_fallback=False): Hybrid function that uses the heuristic first.
#   - click_at(coordinates, delay=0.5): Moves to the given coordinates and clicks.
#   - type_text(text, delay=0.1): Types the provided text.
#   - create_new_conversation(), change_model(new_model), change_default_prompt(new_prompt): Examples of UI actions.

# Usage:
#   Import this module into your chat.py file and call the functions as needed.
# """

# import time
# import json
# import cv2
# import numpy as np
# import pyautogui
# import pytesseract
# from PIL import Image
# import logging
# import openai

# # Configure logging as needed
# logging.basicConfig(level=logging.DEBUG)

# # Ensure your OpenAI API key is set as environment variable, or set it here:
# openai.api_key =  os.getenv("OPENAI_KEY")

# class UIAutomationHybrid:
#     @staticmethod
#     def capture_screen(region=None):
#         """
#         Capture a screenshot (full screen or specified region).
#         :param region: Tuple (left, top, width, height) or None.
#         :return: PIL.Image object.
#         """
#         screenshot = pyautogui.screenshot(region=region)
#         return screenshot

#     @staticmethod
#     def get_ui_elements():
#         """
#         Uses pytesseract to perform OCR on the screenshot and extract text elements with bounding boxes.
#         :return: A list of elements, where each element is a dictionary containing: 
#                  'text', 'x', 'y', 'w', and 'h'.
#         """
#         image = UIAutomationHybrid.capture_screen()
#         ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
#         elements = []
#         n_boxes = len(ocr_data['level'])
#         for i in range(n_boxes):
#             text = ocr_data['text'][i].strip()
#             if text != "":
#                 element = {
#                     "text": text,
#                     "x": int(ocr_data['left'][i]),
#                     "y": int(ocr_data['top'][i]),
#                     "w": int(ocr_data['width'][i]),
#                     "h": int(ocr_data['height'][i])
#                 }
#                 elements.append(element)
#         logging.debug(f"OCR detected {len(elements)} elements.")
#         return elements

#     @staticmethod
#     def find_element_by_keyword_heuristic(keyword):
#         """
#         Searches OCR-detected elements for the first element whose text contains the keyword.
#         :param keyword: The search keyword (case-insensitive).
#         :return: Tuple (x, y) indicating the center of the matched element, or None if not found.
#         """
#         elements = UIAutomationHybrid.get_ui_elements()
#         keyword_lower = keyword.lower()
#         candidates = []
#         for element in elements:
#             if keyword_lower in element['text'].lower():
#                 center_x = element['x'] + element['w'] // 2
#                 center_y = element['y'] + element['h'] // 2
#                 candidates.append((center_x, center_y))
#         if len(candidates) == 1:
#             logging.debug(f"Heuristic found one candidate for '{keyword}': {candidates[0]}")
#             return candidates[0]
#         elif len(candidates) > 1:
#             logging.debug(f"Heuristic found multiple candidates for '{keyword}', using the first one: {candidates[0]}")
#             # You might add additional logic here to disambiguate.
#             return candidates[0]
#         else:
#             logging.debug(f"Heuristic found no candidates for '{keyword}'.")
#             return None

#     @staticmethod
#     def ask_llm_for_coordinates(action, ocr_elements, extra_info=""):
#         """
#         Asks the LLM for coordinates to click based on the provided OCR data and action description.
#         :param action: A string describing the action (e.g., "click the new conversation button").
#         :param ocr_elements: List of OCR elements (from get_ui_elements()).
#         :param extra_info: Optional extra context.
#         :return: Dictionary with keys "x" and "y", or an "error" key.
#         """
#         prompt = (
#             "You are a UI automation assistant. I have a list of UI elements extracted from a screenshot. "
#             "Each UI element is represented as a JSON object with the keys: text, x, y, w, h. \n\n"
#             "Here are the elements:\n"
#             f"{json.dumps(ocr_elements, indent=2)}\n\n"
#             f"Based on these elements, and the following requested action: '{action}'. {extra_info}\n\n"
#             "Determine the screen coordinates (x, y) to click to perform this action. "
#             "Return the answer as a valid JSON object with keys 'x' and 'y'. If you are unable to decide, include an 'error' key with an explanation."
#         )
#         try:
#             model = "gpt-4o-mini"
#             response = openai.chat.completions.create(
#                 model=model,
#                 messages=[
#                     {"role": "system", "content": "You are a helpful UI automation assistant."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 max_tokens=2000,
#                 temperature=0
#             )
#             reply = response.choices[0].message.content

#             logging.debug(f"LLM reply: {reply}")
#             result = json.loads(reply)
#             return result
#         except Exception as e:
#             logging.error("Error calling LLM:", exc_info=e)
#             return {"error": "Failed to get valid coordinates from LLM."}

#     @staticmethod
#     def find_element_by_keyword(keyword, force_llm_fallback=False, extra_info=""):
#         """
#         Hybrid method to find the UI element based on keyword. It will first try heuristic keyword matching.
#         If no candidate is found (or if forced), it will fallback to calling the LLM.
#         :param keyword: Search keyword.
#         :param force_llm_fallback: If True, always use the LLM even if the heuristic finds a candidate.
#         :param extra_info: Extra context to pass to the LLM.
#         :return: Tuple (x, y) of the coordinate to click, or None.
#         """
#         coord = None
#         if not force_llm_fallback:
#             coord = UIAutomationHybrid.find_element_by_keyword_heuristic(keyword)
#         if coord is None or force_llm_fallback:
#             # Fallback to LLM
#             ocr_elements = UIAutomationHybrid.get_ui_elements()
#             llm_result = UIAutomationHybrid.ask_llm_for_coordinates(f"click the UI element that contains '{keyword}'", ocr_elements, extra_info)
#             if "x" in llm_result and "y" in llm_result:
#                 coord = (int(llm_result["x"]), int(llm_result["y"]))
#             else:
#                 logging.error(f"LLM could not provide coordinates for keyword '{keyword}': {llm_result.get('error', 'No error message')}")
#                 coord = None
#         return coord

#     @staticmethod
#     def click_at(coordinates, delay=0.5):
#         """
#         Clicks at the given (x, y) coordinates.
#         :param coordinates: Tuple (x, y) for screen coordinates.
#         :param delay: Seconds to wait after clicking.
#         """
#         if coordinates:
#             logging.info(f"Clicking at {coordinates}")
#             pyautogui.moveTo(coordinates[0], coordinates[1])
#             pyautogui.click()
#             time.sleep(delay)
#         else:
#             logging.warning("No coordinates provided to click_at()")

#     @staticmethod
#     def type_text(text, delay=0.1):
#         """
#         Types text into the active UI element.
#         :param text: Text string to type.
#         :param delay: Delay between keystrokes.
#         """
#         logging.info(f"Typing text: {text}")
#         pyautogui.write(text, interval=delay)
#         time.sleep(0.5)

#     # --- High-Level UI Actions ---

#     @staticmethod
#     def create_new_conversation(force_llm_fallback=False):
#         """
#         Emulates clicking the "new conversation" button.
#         It looks for a UI element by keyword.
#         :param force_llm_fallback: If True, forces LLM fallback.
#         :return: Status message.
#         """
#         coord = UIAutomationHybrid.find_element_by_keyword("new conversation", force_llm_fallback)
#         if coord:
#             UIAutomationHybrid.click_at(coord)
#             return "New conversation created via UI."
#         return "Failed to locate the 'new conversation' element."

#     @staticmethod
#     def change_model(new_model, force_llm_fallback=False):
#         """
#         Emulates changing the model in settings. First, clicks the settings icon,
#         then searches for an element related to "model" to update its value.
#         :param new_model: The new model name.
#         :param force_llm_fallback: If True, forces LLM fallback on each step.
#         :return: Status message.
#         """
#         # Step 1: Click the settings icon.
#         settings_coord = UIAutomationHybrid.find_element_by_keyword("settings", force_llm_fallback)
#         if not settings_coord:
#             return "Failed to locate the settings icon."
#         UIAutomationHybrid.click_at(settings_coord)
#         time.sleep(1)  # Wait for settings to be visible

#         # Step 2: Find the model field.
#         model_coord = UIAutomationHybrid.find_element_by_keyword("model", force_llm_fallback)
#         if not model_coord:
#             return "Failed to locate the model field."
#         UIAutomationHybrid.click_at(model_coord)
#         UIAutomationHybrid.type_text(new_model)
#         return f"Model changed to '{new_model}'."

#     @staticmethod
#     def change_default_prompt(new_prompt, force_llm_fallback=False):
#         """
#         Emulates changing the default prompt via UI actions. First, clicks the settings icon,
#         then finds the prompt field to update.
#         :param new_prompt: The new default prompt text.
#         :param force_llm_fallback: If True, forces LLM fallback for element detection.
#         :return: Status message.
#         """
#         # Step 1: Click the settings icon.
#         settings_coord = UIAutomationHybrid.find_element_by_keyword("settings", force_llm_fallback)
#         if not settings_coord:
#             return "Failed to locate the settings icon."
#         UIAutomationHybrid.click_at(settings_coord)
#         time.sleep(1)

#         # Step 2: Find the prompt field.
#         prompt_coord = UIAutomationHybrid.find_element_by_keyword("prompt", force_llm_fallback)
#         if not prompt_coord:
#             return "Failed to locate the prompt field."
#         UIAutomationHybrid.click_at(prompt_coord)
#         UIAutomationHybrid.type_text(new_prompt)
#         return f"Default prompt updated to: '{new_prompt}'."
