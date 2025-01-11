# cogs/__init__.py
from .chat import ChatCog
from .uploads import UploadsCog
from .conversations import ConversationsCog
from .orchestration_analysis import OrchestrationAnalysisCog
from .web_search import WebSearchCog
from .code_files import CodeFilesCog



def register_cogs(app, flask_app, socketio):
    chat_cog = ChatCog(app, flask_app, socketio)
    uploads_cog = UploadsCog(chat_cog.upload_folder)
    conversations_cog = ConversationsCog()
    orchestration_analysis_cog = OrchestrationAnalysisCog(chat_cog.client)
    web_search_cog = WebSearchCog(openai_client=chat_cog.client)
    code_files_cog = CodeFilesCog()


    app.register_blueprint(chat_cog.bp)
    app.register_blueprint(uploads_cog.bp)
    app.register_blueprint(conversations_cog.bp)
    print('Cogs loaded', flush=True)
    # Register other cogs as needed
