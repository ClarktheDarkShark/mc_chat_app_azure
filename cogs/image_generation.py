# cogs/image_generation.py

import traceback
from flask import jsonify
from models import Message
from utils.response_generation import generate_image


class ImageGenerationCog:
    """
    Encapsulates logic for image generation orchestration events.
    """

    def handle_image_generation(
        self,
        socketio,
        orchestration,
        user_message,
        conversation_history,
        conversation_id,
        session_id
    ):
        """
        Generate an image based on 'image_prompt' in the orchestration,
        then send a Socket.IO event with the final result.
        """
        prompt = orchestration.get("image_prompt", "")
        if prompt:
            try:
                image_url = generate_image(prompt)
                assistant_reply = f"![Generated Image]({image_url})"
            except Exception as e:
                print(f"[ImageGenerationCog] Error generating image: {e}")
                traceback.print_exc()
                assistant_reply = "Failed to generate image."
        else:
            assistant_reply = "No image prompt provided."

        conversation_history.append({"role": "assistant", "content": assistant_reply})

        # Save message to DB
        msg = Message(conversation_id=conversation_id, role="assistant", content=assistant_reply)
        msg.save()

        # Emit Socket.IO event
        socketio.emit('task_complete', {'answer': assistant_reply}, room=session_id)

        return jsonify({
            "user_message": user_message,
            "assistant_reply": assistant_reply,
            "conversation_history": conversation_history,
            "orchestration": orchestration
        })
