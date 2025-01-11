# cogs/file_orchestration.py

import os
import traceback

from flask import jsonify
from models import UploadedFile


# We rely on the "process_uploaded_file" from utils
from utils.file_utils import process_uploaded_file


class FileOrchestrationCog:
    """
    Encapsulates logic to handle orchestration for files:
    - Listing
    - Retrieving
    - Reading contents
    - (Optional) multiple file handling
    """

    def handle_file_orchestration(
        self,
        session_id,
        orchestration,
        upload_folder,
        db_session,
        use_azure=False,
        blob_service_client=None,
        container_name="my-container-name"
    ):
        """
        Orchestration for file(s) specified in 'file_ids',
        or (if none) listing all user-uploaded files.
        """
        supplemental_information = {}
        assistant_reply = ""
        file_ids = orchestration.get("file_ids", [])

        try:
            # Gather all uploaded files for session
            uploaded_files = UploadedFile.query.filter_by(session_id=session_id).all()
            uploaded_dict = {str(f.id): f for f in uploaded_files}

            # If no file_ids => list all
            if not file_ids:
                if not uploaded_files:
                    assistant_reply = "No files have been uploaded yet."
                    return supplemental_information, assistant_reply

                file_list_str = "\n".join(
                    f"- {f.original_filename} (ID: {f.id})" for f in uploaded_files
                )
                assistant_reply = f"Uploaded files:\n{file_list_str}"
                supplemental_information = {
                    "role": "system",
                    "content": f"List of uploaded files:\n***{file_list_str}***"
                }
                return supplemental_information, assistant_reply

            # Otherwise, handle specific file(s)
            valid_ids = [fid for fid in file_ids if fid in uploaded_dict]
            invalid_ids = [fid for fid in file_ids if fid not in uploaded_dict]

            if not valid_ids:
                # None matched
                if invalid_ids:
                    assistant_reply = f"No valid files found for IDs: {', '.join(invalid_ids)}"
                else:
                    assistant_reply = "No valid file IDs found."
                return supplemental_information, assistant_reply

            if len(valid_ids) > 3:
                # If user requests more than 3 files, just list them
                file_list_str = "\n".join(
                    f"- {uploaded_dict[fid].original_filename} (ID: {fid})"
                    for fid in valid_ids
                )
                assistant_reply = (
                    f"Here are the requested file names:\n{file_list_str}\n\n"
                    "Note: File contents not displayed for more than 3 files."
                )
                if invalid_ids:
                    assistant_reply += f"\nInvalid IDs: {', '.join(invalid_ids)}."
                supplemental_information = {
                    "role": "system",
                    "content": f"Requested file names:\n***{file_list_str}***"
                }
                return supplemental_information, assistant_reply

            # If 1-3 files => read contents
            file_contents = []
            errors = []
            for fid in valid_ids:
                upl_file = uploaded_dict[fid]
                file_path = os.path.join(upload_folder, upl_file.filename)
                if not os.path.exists(file_path):
                    errors.append(f"File '{upl_file.original_filename}' not found on server.")
                    continue

                try:
                    content = process_uploaded_file(
                        file=None,
                        upload_folder=upload_folder,
                        session_id=session_id,
                        db_session=db_session,
                        read=True,
                        path=file_path,
                        use_azure=use_azure,
                        blob_service_client=blob_service_client,
                        container_name=container_name
                    )
                    file_contents.append((upl_file.original_filename, content))
                except Exception as e:
                    msg = f"Error reading file '{upl_file.original_filename}': {e}"
                    errors.append(msg)

            # Build the reply
            for fname, content in file_contents:
                assistant_reply += f"**{fname}:**\n{content}\n\n"

            if errors:
                assistant_reply += "\n".join(errors)

            if file_contents:
                joined = "\n\n".join(
                    f"File: {fname}\nContent:\n***{content}***"
                    for fname, content in file_contents
                )
                supplemental_information = {
                    "role": "system",
                    "content": (
                        "You have been supplemented with file contents:\n"
                        f"{joined}"
                    )
                }

            if invalid_ids:
                assistant_reply += f"\nInvalid file IDs: {', '.join(invalid_ids)}."

            return supplemental_information, assistant_reply

        except Exception as e:
            print(f"[FileOrchestrationCog] Error: {e}")
            traceback.print_exc()
            return supplemental_information, assistant_reply
