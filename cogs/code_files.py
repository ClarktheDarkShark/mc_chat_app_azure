# cogs/code_files.py
import os

class CodeFilesCog:
    def __init__(self, base_dir=''):
        """
        Initialize the CodeFilesCog.

        :param base_dir: Base directory to search for code files. Defaults to current working directory.
        """
        self.base_dir = base_dir or os.getcwd()

    def get_all_code_files_content(self, allowed_dirs=None):
        """
        Retrieve content from Python files in the base directory and specified subdirectories.
        
        :param allowed_dirs: List of allowed subdirectories to include (e.g., ['cogs', 'utils'])
        :return: Concatenated string of code content.
        """
        if allowed_dirs is None:
            allowed_dirs = ['cogs', 'utils']  # Default to cogs and utils directories
        
        code_content = ""
        
        
        # Include Python files from the base directory
        for file in os.listdir(self.base_dir):
            if file.endswith('.py') and os.path.isfile(os.path.join(self.base_dir, file)):
                file_path = os.path.join(self.base_dir, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        code_content += f.read() + "\n\n"
                    print(f"Included base file: {file_path}")
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
        
        # Include Python files from allowed subdirectories
        for allowed_dir in allowed_dirs:
            dir_path = os.path.join(self.base_dir, allowed_dir)
            if os.path.isdir(dir_path):
                for file in os.listdir(dir_path):
                    if file.endswith('.py'):
                        file_path = os.path.join(dir_path, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                code_content += f.read() + "\n\n"
                            print(f"Included file: {file_path}")
                        except Exception as e:
                            print(f"Error reading {file_path}: {e}")

        file_path = os.path.join(self.base_dir, "my-chat-frontend/src/ChatApp.jsx")
        with open(file_path, 'r', encoding='utf-8') as f:
            code_content += f.read() + "\n\n"
        
        if not code_content:
            print("No Python files found in the specified directories.")
        
        return code_content

