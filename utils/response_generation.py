# utils/response_generation.py
import os
import uuid
import graphviz

def generate_image(prompt, openai_client):
    """Generate an image using OpenAI's DALL-E 3 and return the image URL."""
    try:
        image_response = openai_client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1
        )
        image_url = image_response.data[0].url
        return image_url
    except Exception as e:
        print(f'Error in image generation: {e}')
        return "Error generating image."

def generate_codebase_structure_diagram(upload_folder):
    """Generate a visual representation of the codebase structure."""
    try:
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(current_file_dir, '..'))  # Adjust as needed to point to the project root

        print(f"Scanning root directory: {root_dir}")

        dot = graphviz.Digraph(comment='Codebase Structure', format='png')

        def add_nodes_edges(current_path, parent=None):
            directory = os.path.basename(current_path)
            node_id = current_path.replace(os.sep, '_')  # Unique node ID

            if parent:
                dot.node(node_id, directory, shape='folder')
                dot.edge(parent, node_id)
            else:
                dot.node(node_id, directory, shape='folder')  # Root node

            try:
                for entry in os.listdir(current_path):
                    path = os.path.join(current_path, entry)
                    if os.path.isdir(path):
                        add_nodes_edges(path, node_id)
                    else:
                        file_node_id = path.replace(os.sep, '_')
                        dot.node(file_node_id, entry, shape='note')
                        dot.edge(node_id, file_node_id)
            except PermissionError:
                print(f"Permission denied: {current_path}")
            except Exception as e:
                print(f"Error scanning directory {current_path}: {e}")

        add_nodes_edges(root_dir)

        # Generate the diagram
        output_filename = f"codebase_structure_{uuid.uuid4()}"
        dot.render(filename=output_filename, directory=upload_folder, cleanup=True)
        image_path = os.path.join(upload_folder, f"{output_filename}.png")
        image_url = f"/uploads/{output_filename}.png"

        print(f"Codebase structure diagram generated at: {image_path}")

        return image_url

    except Exception as e:
        print(f"Error generating codebase structure diagram: {e}")
        return None


def generate_chat_response(openai_client, messages, model, temperature):
    """Generate a chat response using OpenAI's ChatCompletion."""
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2000,
            temperature=temperature
        )
        assistant_reply = response.choices[0].message.content
        return assistant_reply
    except Exception as e:
        print(f'Error in chat response generation: {e}')
        return "Error generating response."
