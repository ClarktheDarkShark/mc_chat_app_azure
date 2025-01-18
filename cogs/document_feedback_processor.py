import os
import re
import time
import json
import pandas as pd
import openai

# For PDFs
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

# For Word documents
try:
    import docx
except ImportError:
    docx = None


# ----- PDF Visible Lines Extraction ----- 
def extract_pdf_visible_lines_dict(pdf_path):
    """
    Extracts the visible text lines for each page in the PDF.
    Returns a dictionary mapping each page number (1-indexed) to a list of lines, 
    preserving the visible line breaks.
    """
    if PdfReader is None:
        raise ImportError("PyPDF2 is required. Please install via pip.")
    reader = PdfReader(pdf_path)
    pages_lines = {}
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        # Split the text on newline characters to preserve the layout
        lines = text.splitlines()
        pages_lines[i + 1] = lines
    return pages_lines


# ----- Document Text Extraction (Global Versions) -----   # (C)
def extract_pdf_text_global(pdf_path):
    """
    Extracts text from a PDF and returns a single string that is the concatenation 
    of all pages, each separated by a newline.
    """
    if PdfReader is None:
        raise ImportError("PyPDF2 is required. Please install via pip.")
    reader = PdfReader(pdf_path)
    pages = []
    for i in range(len(reader.pages)):
        page = reader.pages[i]
        text = page.extract_text() or ""
        pages.append(text)
    return "\n".join(pages)

def extract_docx_text_global(docx_path):
    """
    Extracts text from a DOCX file and returns it as a single string.
    """
    if docx is None:
        raise ImportError("python-docx is required. Please install via pip.")
    document = docx.Document(docx_path)
    return "\n".join(para.text for para in document.paragraphs)

def extract_document_text_global(document_path):
    """
    Determines the document type (PDF or DOCX) and returns the entire document text as one string.
    """
    ext = os.path.splitext(document_path)[1].lower()
    if ext == ".pdf":
        return extract_pdf_text_global(document_path)
    elif ext in [".docx"]:
        return extract_docx_text_global(document_path)
    else:
        raise ValueError("Unsupported document type: only PDF and DOCX are supported.")


# ----- Fallback: Extract PDF Text by Page -----   # (C)
def extract_pdf_text_by_page(pdf_path):
    """
    Extracts text from a PDF and returns a dictionary mapping each page number (1-indexed) to its text.
    """
    if PdfReader is None:
        raise ImportError("PyPDF2 is required. Please install via pip.")
    reader = PdfReader(pdf_path)
    pages = {}
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages[i + 1] = text
    return pages


# ----- Snippet Extraction ----- 
def extract_snippet_global(document_text, target_line, context=3):
    """
    Splits the entire document text by newline and returns a snippet consisting of a few lines 
    before and after the target line (global numbering).
    """
    lines = re.split(r'\r?\n', document_text)
    if not lines:
        return ""
    total_lines = len(lines)
    try:
        target_line = int(target_line)
    except Exception:
        target_line = 1
    start = max(0, target_line - context - 1)
    end = min(total_lines, target_line + context)
    return "\n".join(lines[start:end])

def extract_snippet_from_lines(lines, target_line, context=3):
    """
    Given a list of lines (from a single PDF page), returns a snippet with a few lines 
    before and after the target visible line.
    """
    total_lines = len(lines)
    try:
        target_line = int(target_line)
    except Exception:
        target_line = 1
    # Adjust for 0-indexing (visible line numbering is 1-indexed)
    start = max(0, target_line - context - 1)
    end = min(total_lines, target_line + context)
    return "\n".join(lines[start:end])


# ----- CRM Column Mapping -----   # (C)
def map_crm_columns(crm_df):
    """
    Maps CRM columns to standard keys.
    Expected columns (case-insensitive):
      - "Page #" (optional), "Line #", and 
      - "Recommended Change (Please provide language that mitigates issue.  Example: Change 'this' to say 'that')"
        which is mapped to "feedback".
    """
    crm_df.columns = [col.strip() for col in crm_df.columns]
    col_mapping = {}
    for col in crm_df.columns:
        lower = col.lower()
        if lower == "page #":
            col_mapping[col] = "page"
        elif lower == "line #":
            col_mapping[col] = "line"
        elif "recommended change" in lower:
            col_mapping[col] = "feedback"
    crm_df = crm_df.rename(columns=col_mapping)
    return crm_df


# ----- Generate Quality Summary -----   # (S)
def generate_quality_summary(document_text, model, temperature, openai_client):
    """
    Generates a high quality summary of the given document text.
    
    This summary is intended to provide overall context for subsequent feedback analysis.
    """
    system_prompt = (
        "You are an expert summarizer. Provide a comprehensive yet concise summary of the following document. "
        "Focus on the overall context, main points, and structure of the document. Keep the summary under 300 words."
    )
    user_prompt = f"Document text:\n{document_text}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    response = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=800,
        temperature=temperature
    )
    summary = response.choices[0].message.content.strip()
    # Clean any markdown formatting
    if summary.startswith("```") and summary.endswith("```"):
        summary = summary[3:-3].strip()
    return summary


# ----- Prompt Construction -----   # (S)
def build_system_and_user_prompt(snippet, feedback, quality_summary):
    """
    Constructs system and user messages for the OpenAI API.
    
    The system prompt instructs:
      "You are an expert document editor. You are given the overall document summary along with a snippet from the document 
       and a stakeholder feedback comment. Feedback comments have a level: A (admin), S (substantive), or C (critical). 
       For critical comments (C), if you decide to reject the feedback, ensure you provide robust justification with detailed reasoning. 
       For substantive comments (S), lean toward acceptance unless there is a compelling reason to reject, while 
       carefully considering administrative (A) comments. 
       Now, you are provided with a snippet from the document (using visible line numbers) and the associated stakeholder feedback. 
       Analyze the snippet with context from the overall document summary and decide whether to 'accept' or 'reject' the feedback. 
       If accepting, incorporate any suggested changes into the snippet and provide specifics if appropriate; if rejecting, provide a concise (2–4 sentence) explanation. 
       Return your answer strictly as a valid JSON object with exactly two keys: 'decision' and 'response'."
       
    The user prompt includes the quality summary, the document snippet, and the stakeholder feedback.
    """
    system_message = (
        "You are an expert document editor. Here is the overall summary of the document:\n"
        f"{quality_summary}\n\n"
        "Stakeholder feedback comments include levels: A (admin), S (substantive), and C (critical). "
        "For critical comments (C), if you reject the feedback, ensure you provide robust justification with clear detailed reasoning. "
        "For substantive comments (S), lean toward acceptance unless there is a compelling reason to reject, while "
        "carefully considering administrative (A) comments. "
        "Now, you are provided with a snippet from the document (using visible line numbers) and the associated stakeholder feedback. "
        "Analyze the snippet with context from the overall document summary and decide whether to 'accept' or 'reject' the feedback. "
        "If accepting, incorporate any suggested changes into the snippet and provide specifics if appropriate; if rejecting, provide a concise (2–4 sentence) explanation. "
        "Return your answer strictly as a valid JSON object with exactly two keys: 'decision' and 'response'."
    )
    user_message = (
        "Document snippet (using visible PDF lines when applicable):\n"
        f"{snippet}\n\n"
        "Stakeholder feedback:\n"
        f"{feedback}\n\n"
        "Please analyze and provide your decision and response."
    )
    return system_message, user_message


# ----- Main Function -----   # (S)
def process_stakeholder_feedback(document_path, crm_file_path, model, temperature, openai_client):
    """
    Processes stakeholder feedback for an enterprise document.
    
    For DOCX documents, global line numbering is used.
    
    For PDFs, this function uses the visible line numbers as seen on the left side of the document.
    If the CRM provides a "Page #" column or if the "Line #" value includes a page delimiter (e.g., "2:15" or "2-15"),
    the code extracts the snippet from the specified page and visible line number.
    Otherwise, if no page is provided, the function will attempt to infer the page number based on the global line number.
    If no line is provided, it falls back:
       - For PDFs: it uses page 5 if available; otherwise uses page 1's first 7 lines.
       - For DOCX: it uses the first 7 lines of the global text.
      
    Returns:
      Markdown-formatted results that include the line (or page/line), feedback, decision, and response.
    """
    # Correct file paths (if needed)
    if document_path.startswith("/uploads"):
        document_path = os.path.join("/app/instance/uploads", document_path.lstrip("/uploads"))

    if crm_file_path.startswith("/uploads"):
        crm_file_path = os.path.join("/app/instance/uploads", crm_file_path.lstrip("/uploads"))

    # Extract global document text (used for DOCX and for quality summary)
    try:
        global_text = extract_document_text_global(document_path)
    except Exception as e:
        return [{"error": f"Error extracting document text: {e}"}]
    
    # Generate quality summary for the entire document (to provide overall context)
    try:
        quality_summary = generate_quality_summary(global_text, model, temperature, openai_client)
    except Exception as sum_err:
        quality_summary = "Summary unavailable due to error."
        print(f"Error generating quality summary: {sum_err}")
    
    # Read CRM file
    crm_ext = os.path.splitext(crm_file_path)[1].lower()
    try:
        if crm_ext in [".xlsx", ".xls"]:
            crm_df = pd.read_excel(crm_file_path)
        elif crm_ext == ".csv":
            crm_df = pd.read_csv(crm_file_path)
        else:
            return [{"error": "Unsupported CRM file type. Supported formats: Excel and CSV."}]
    except Exception as e:
        return [{"error": f"Error reading CRM file: {e}"}]
    
    crm_df = map_crm_columns(crm_df)
    # For processing, we need at least the "line" and "feedback" columns.
    required_columns = {"line", "feedback"}
    if not required_columns.issubset(set(crm_df.columns)):
        return [{"error": f"CRM file must include the following columns: {required_columns}"}]
    
    ext = os.path.splitext(document_path)[1].lower()
    visible_lines_pages = None
    if ext == ".pdf":
        try:
            visible_lines_pages = extract_pdf_visible_lines_dict(document_path)
        except Exception as e:
            print(f"Error extracting visible lines from PDF: {e}")
    
    results = []
    markdown_results = "### Feedback Results\n\n"

    # Precompile regex for range detection (handles hyphen, en-dash, em-dash)
    range_pattern = re.compile(r'^(\d+)\s*[-–—]\s*(\d+)$')  # Matches "2-6", "2–6", "2—6"

    for idx, row in crm_df.iterrows():
        try:
            feedback = str(row.get("feedback", "")).strip()
            if not feedback:
                continue  # Skip if no feedback is provided.
                
            line_val = str(row.get("line", "")).strip()
            page_val = str(row.get("page", "")).strip() if "page" in row and row.get("page") is not None else ""
            snippet = ""
            page_num = None
            line_num = None
            line_range = None
            
            if ext == ".pdf" and visible_lines_pages:
                if page_val:
                    # Page and line provided explicitly.
                    try:
                        page_num = int(page_val)
                        line_num = int(line_val) if line_val and line_val.isdigit() else 1
                    except Exception:
                        page_num, line_num = 1, 1
                elif line_val:
                    # No page provided, but we have a line number. Infer the page by treating line_val as a global line index.
                    try:
                        target_line_global = int(line_val)
                    except Exception:
                        target_line_global = 1
                    cumulative = 0
                    for pn in sorted(visible_lines_pages.keys()):
                        page_length = len(visible_lines_pages[pn])
                        if target_line_global <= cumulative + page_length:
                            page_num = pn
                            line_num = target_line_global - cumulative
                            break
                        cumulative += page_length
                    if page_num is None:
                        # If the target line exceeds total lines, fallback to the last page.
                        page_num = max(visible_lines_pages.keys())
                        line_num = 1
                else:
                    # Fallback: use page 5 if available, else page 1.
                    if 5 in visible_lines_pages:
                        page_num, line_num = 5, 1
                    else:
                        page_num, line_num = 1, 1

                # If a range was detected, update line_range.
                range_match = range_pattern.match(line_val)
                if range_match:
                    start_line = int(range_match.group(1))
                    end_line = int(range_match.group(2))
                    line_range = range(start_line, end_line + 1)
                
                # If the selected page is available, extract its snippet using visible lines.
                if page_num in visible_lines_pages:
                    lines = visible_lines_pages[page_num]
                    if line_range:
                        snippets = []
                        for ln in line_range:
                            snippet_part = extract_snippet_from_lines(lines, ln, context=3)
                            snippets.append(snippet_part)
                        snippet = "\n\n---\n\n".join(snippets)
                    elif line_num:
                        snippet = extract_snippet_from_lines(lines, line_num, context=3)
                    else:
                        snippet = "\n".join(lines[:7])
                else:
                    # Fallback to using the first 7 lines of the global text.
                    snippet = "\n".join(global_text.splitlines()[:7])
            else:
                # For DOCX (or any non-PDF), or fallback to global extraction.
                if line_val:
                    if range_match := range_pattern.match(line_val):
                        start_line = int(range_match.group(1))
                        end_line = int(range_match.group(2))
                        lines = re.split(r'\r?\n', global_text)
                        snippets = []
                        for ln in range(start_line, end_line + 1):
                            snippet_part = extract_snippet_global(global_text, ln, context=3)
                            snippets.append(snippet_part)
                        snippet = "\n\n---\n\n".join(snippets)
                    else:
                        try:
                            target_line = int(line_val)
                            snippet = extract_snippet_global(global_text, target_line, context=3)
                        except Exception:
                            snippet = "\n".join(global_text.splitlines()[:7])
                else:
                    snippet = "\n".join(global_text.splitlines()[:7])
            
            # Build prompts incorporating the quality summary.
            system_message, user_message = build_system_and_user_prompt(snippet, feedback, quality_summary)
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ]
            
            # Call the OpenAI API for feedback evaluation.
            response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2000,
                temperature=temperature
            )
            assistant_reply = response.choices[0].message.content.strip()

            if assistant_reply.startswith("```json"):
                assistant_reply = assistant_reply[7:-3].strip()
            elif assistant_reply.startswith("```") and assistant_reply.endswith("```"):
                assistant_reply = assistant_reply[3:-3].strip()
            
            try:
                parsed_reply = json.loads(assistant_reply)
                decision = parsed_reply.get("decision", "unknown")
                response_text = parsed_reply.get("response", "")
            except Exception as parse_err:
                decision = "error"
                response_text = f"Failed to parse reply. Raw output: {assistant_reply}"
            
            # Determine line descriptor.
            if ext == ".pdf" and visible_lines_pages:
                if page_val or re.search(r'[-–—]', line_val) or line_val:
                    if range_match := range_pattern.match(line_val):
                        line_descriptor = f"Page {page_num}, Lines {range_match.group(1)}–{range_match.group(2)}"
                    elif ':' in line_val:
                        parts = line_val.split(':')
                        if len(parts) >= 2:
                            line_descriptor = f"Page {parts[0]}, Line {parts[1]}"
                        else:
                            line_descriptor = f"Page {page_num}, Line {line_num}"
                    else:
                        line_descriptor = f"Page {page_num}, Line {line_num}"
                else:
                    line_descriptor = line_val if line_val else "Fallback (Page 5 or start)"
            else:
                line_descriptor = line_val if line_val else "Fallback (Start)"
            
            results.append({
                "line": line_descriptor,
                "feedback": feedback,
                "decision": decision,
                "response": response_text
            })
            
            markdown_results += (
                f"{idx + 1}. **Line:** {line_descriptor}  \n"
                f"   **Feedback:** {feedback}  \n"
                f"   **Decision:** {decision}  \n"
                f"   **Response:** {response_text}  \n\n"
            )
            
            # Optional delay to avoid rate limits.
            # time.sleep(1)
        except Exception as row_err:
            error_entry = {
                "line": row.get("line", "N/A"),
                "feedback": row.get("feedback", ""),
                "decision": "error",
                "response": f"Error processing row: {row_err}"
            }
            results.append(error_entry)
            markdown_results += (
                f"{idx + 1}. **Line:** {error_entry['line']}\n"
                f"   **Feedback:** {error_entry['feedback']}\n"
                f"   **Decision:** error\n"
                f"   **Response:** {error_entry['response']}\n\n"
            )

    # Return markdown results
    return markdown_results
