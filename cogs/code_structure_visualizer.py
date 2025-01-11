# cogs/code_structure_visualizer.py
import os
import uuid
import graphviz
import hashlib
from flask import current_app

class CodeStructureVisualizerCog:
    def __init__(self, upload_folder=None):
        """
        Initialize the CodeStructureVisualizerCog.

        :param upload_folder: Path to the folder where uploaded files and generated images are stored.
        """
        self.upload_folder = upload_folder

        # Explicitly add Graphviz path
        os.environ["PATH"] += os.pathsep + '/app/.heroku-buildpack-graphviz/usr/bin'

        # Define directories and file types to exclude
        self.exclude_dirs = {
            'uploads', '.git', '__pycache__', 'node_modules', 'venv',
            'migrations', 'tests', 'docs', 'dist', 'build'
        }
        self.exclude_file_types = {'.pyc', '.pyo', '.log', '.env'}

        # Maximum recursion depth
        self.max_depth = 4

    def generate_codebase_structure_diagram(self, upload_folder=None):
        """
        Generate a visual representation of the codebase structure using Graphviz.

        :return: URL path to the generated image or None if generation fails.
        """
        self.upload_folder = upload_folder
        try:
            # Define the root directory to scan (project root)
            current_file_dir = os.path.dirname(os.path.abspath(__file__))  # Directory where this cog is located
            root_dir = os.path.abspath(os.path.join(current_file_dir, '..'))  # Adjust as needed to point to the project root

            print(f"Scanning root directory: {root_dir}")

            # Create a hash of the directory structure to use for caching
            dir_hash = self.hash_directory_structure(root_dir)
            output_filename = f"codebase_structure_{dir_hash}"
            image_filename = f"{output_filename}.png"
            image_path = os.path.join(self.upload_folder, image_filename)
            image_url = f"/uploads/{image_filename}"

            # Check if the diagram already exists
            if os.path.exists(image_path):
                print(f"Using cached diagram at: {image_path}")
                return image_url

            # Initialize Graphviz Digraph
            dot = graphviz.Digraph(comment='Codebase Structure', format='png')
            dot.attr(dpi='300')  # High resolution for clarity

            def add_nodes_edges(current_path, parent=None, depth=0):
                if depth > self.max_depth:
                    return
                directory = os.path.basename(current_path)
                node_id = self.create_node_id(current_path)

                if parent:
                    dot.node(node_id, directory, shape='folder')
                    dot.edge(parent, node_id)
                else:
                    dot.node(node_id, directory, shape='folder')  # Root node

                try:
                    for entry in sorted(os.listdir(current_path)):
                        path = os.path.join(current_path, entry)
                        if os.path.isdir(path):
                            if entry in self.exclude_dirs:
                                print(f"Excluding directory: {path}")
                                continue
                            add_nodes_edges(path, node_id, depth + 1)
                        else:
                            if self.should_exclude_file(entry):
                                print(f"Excluding file: {path}")
                                continue
                            file_node_id = self.create_node_id(path)
                            dot.node(file_node_id, entry, shape='note')
                            dot.edge(node_id, file_node_id)
                except PermissionError:
                    print(f"Permission denied: {current_path}")
                except Exception as e:
                    print(f"Error scanning directory {current_path}: {e}")

            add_nodes_edges(root_dir)

            # Render the diagram
            dot.render(filename=output_filename, directory=self.upload_folder, cleanup=True)
            print(f"Codebase structure diagram generated at: {image_path}")

            return image_url

        except Exception as e:
            print(f"Error generating codebase structure diagram: {e}")
            return None

    def create_node_id(self, path):
        """
        Create a unique node ID by hashing the file path.

        :param path: File or directory path.
        :return: Unique node ID as a string.
        """
        return hashlib.md5(path.encode()).hexdigest()

    def hash_directory_structure(self, root_dir):
        """
        Create a hash representing the current directory structure.

        :param root_dir: Root directory to hash.
        :return: MD5 hash as a string.
        """
        hash_md5 = hashlib.md5()
        for root, dirs, files in os.walk(root_dir):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file in sorted(files):
                if self.should_exclude_file(file):
                    continue
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'rb') as f:
                        while True:
                            chunk = f.read(4096)
                            if not chunk:
                                break
                            hash_md5.update(chunk)
                except Exception as e:
                    print(f"Error hashing file {filepath}: {e}")
        return hash_md5.hexdigest()

    def should_exclude_file(self, filename):
        """
        Determine if a file should be excluded based on its extension.

        :param filename: Name of the file.
        :return: True if the file should be excluded, False otherwise.
        """
        _, ext = os.path.splitext(filename)
        return ext in self.exclude_file_types
