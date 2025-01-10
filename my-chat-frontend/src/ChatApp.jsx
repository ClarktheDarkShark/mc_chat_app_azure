// src/ChatApp.jsx
import React, { useState, useRef, useEffect, memo } from "react";
import { 
  createTheme, 
  ThemeProvider, 
  IconButton, 
  Container, 
  Typography, 
  Box,
  Slider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  TextField,
  useTheme,
  useMediaQuery,
  Drawer,
  List,
  ListItem,
  ListItemText,
  Divider,
  Button
} from '@mui/material';
import SettingsIcon from '@mui/icons-material/Settings';
import CloseIcon from '@mui/icons-material/Close';
import SendIcon from '@mui/icons-material/Send';
import ClearIcon from '@mui/icons-material/Clear';
import MenuIcon from '@mui/icons-material/Menu';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { io } from 'socket.io-client';
import ReactMarkdown from 'react-markdown';

// ErrorBoundary Component to Catch Rendering Errors
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error: error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Error caught by ErrorBoundary:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Typography color="error">
          Something went wrong while rendering the messages: {this.state.error.toString()}
        </Typography>
      );
    }
    return this.props.children;
  }
}

// MUI Theme Configuration
const theme = createTheme({
  palette: {
    primary: { main: '#AF002A' },
    secondary: { main: '#FFD700' },
    background: {
      default: '#000000',
      paper: '#1a1a1a',
    },
    text: {
      primary: '#ffffff',
      secondary: '#FFD700',
    },
  },
});

// Memoized ChatMessage Component with loadingText prop
const ChatMessage = memo(
  ({ msg, loadingText }) => {
    console.log(`Rendering message ${msg.id}:`, msg.content);

    const isImage =
      msg.role === "assistant" && msg.content.startsWith("![Generated Image](");
    const isAssistant = msg.role === "assistant";
    const isFile = msg.role === "user" && msg.file;

    let contentToRender;

    if (msg.loading) {
      contentToRender = (
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <CircularProgress size={20} color="secondary" />
          <Typography variant="body2" sx={{ ml: 1 }}>
            {msg.content} {/* Directly display the updated content */}
          </Typography>
        </Box>
      );
    } else if (isImage) {
      const match = msg.content.match(/^!\[Generated Image\]\((.+)\)$/);
      const imageUrl = match ? match[1] : null;

      if (imageUrl) {
        contentToRender = (
          <Box sx={{ maxWidth: '70%', borderRadius: '8px', overflow: 'hidden' }}>
            <img
              src={imageUrl}
              alt="Generated"
              style={{ width: '100%', height: 'auto', display: 'block' }}
            />
          </Box>
        );
      } else {
        contentToRender = (
          <Typography variant="body1" color="error">
            Invalid image URL.
          </Typography>
        );
      }
    } else if (isFile) {
      const fileUrl = msg.fileUrl;
      const fileName = msg.fileName;
      const fileType = msg.fileType;

      if (fileType.startsWith("image/")) {
        contentToRender = (
          <Box sx={{ maxWidth: '70%', borderRadius: '8px', overflow: 'hidden' }}>
            <img
              src={fileUrl}
              alt={fileName}
              style={{ width: '100%', height: 'auto', display: 'block' }}
            />
          </Box>
        );
      } else if (fileType === "application/pdf") {
        contentToRender = (
          <Box sx={{ maxWidth: '70%' }}>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#FFD700', textDecoration: 'none' }}
            >
              {fileName} (PDF)
            </a>
          </Box>
        );
      } else {
        contentToRender = (
          <Typography variant="body1" color="secondary">
            {fileName} ({fileType})
          </Typography>
        );
      }
    } else if (isAssistant) {
      contentToRender = (
        <ReactMarkdown>
          {msg.content || "**(No content available)**"}
        </ReactMarkdown>
      );
    } else {
      contentToRender = (
        <Typography variant="body1">
          {msg.content || "No response available."}
        </Typography>
      );
    }

    return (
      <Box
        sx={{
          backgroundColor:
            msg.role === "user"
              ? 'primary.main'
              : msg.loading
              ? 'grey.500'
              : 'grey.700',
          color: 'white',
          borderRadius: 2,
          p: isImage || isFile ? 0 : 1,
          maxWidth: '80%',
          ml: msg.role === "user" ? 'auto' : 0,
          mb: 1,
        }}
      >
        {contentToRender}
      </Box>
    );
  },
  (prevProps, nextProps) => {
    // Custom comparison function
    return (
      prevProps.msg.id === nextProps.msg.id &&
      prevProps.msg.content === nextProps.msg.content &&
      prevProps.loadingText === nextProps.loadingText
    );
  }
);


// Main ChatApp Component
function ChatApp() {
  // Utility function to generate UUID
  const generateUUID = () => {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0,
        v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  };
  // State Variables
  // Theme and Media Query for responsive Typography
  const muiTheme = useTheme();
  const isMobile = useMediaQuery(muiTheme.breakpoints.down("md"));
  const [message, setMessage] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [temperature, setTemperature] = useState(0.7);
  const [systemPrompt, setSystemPrompt] = useState("You are a USMC AI agent. Provide relevant responses.");
  const [statusMessage, setStatusMessage] = useState("");
  const [loadingText, setLoadingText] = useState("Assistant is thinking...");
  const [storedSessionId, setStoredSessionId] = useState(() => {
    // Initialize session_id from sessionStorage or generate a new one
    let id = sessionStorage.getItem("session_id");
    if (!id) {
      id = generateUUID();
      sessionStorage.setItem("session_id", id);
    }
    return id;
  });
  // const theme = useTheme();
  // const isMobile = useMediaQuery(useTheme().breakpoints.down("md"));

  const [conversation, setConversation] = useState([
    {
      role: "assistant",
      content: `**Welcome to the USMC AI Agent Demo!**  
I am here to assist you with a variety of tasks. Here are some things you can ask me:

- Summarize the latest news about the Marine Corps.
- Explain how my code handles query orchestration.
- Generate a briefing on amphibious operations.
- Upload files to query, compare, summarize, or improve.
- Create an image of Marines conducting an amphibious assault.

Feel free to type your question below!`,
      id: "welcome",
    },
  ]);

  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [conversationsList, setConversationsList] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);

  // Refs
  const conversationRef = useRef(null);
  const socketRef = useRef(null);



  // Initialize WebSocket and handle session_id
  useEffect(() => {
    if (!socketRef.current) {
      // Initialize Socket.IO with session_id as query parameter
      socketRef.current = io("/", {
        transports: ["websocket"],
        withCredentials: true,
        query: { session_id: storedSessionId },
      });

      // WebSocket event handlers
      socketRef.current.on("connected", (data) => {
        console.log("Connected with session_id:", data.session_id);
      });

      socketRef.current.on("connect_error", (err) => {
        console.error("WebSocket Connection Error:", err.message);
        setError("WebSocket connection failed. Please refresh the page.");
      });

      socketRef.current.on("task_complete", (data) => {
        setStatusMessage(""); // Clear the status message
      });

      socketRef.current.io.on("reconnect_attempt", () => {
        console.log("Attempting to reconnect...");
      });

      socketRef.current.io.on("reconnect_failed", () => {
        console.error("Reconnection failed.");
        setError("Unable to reconnect to the server. Please refresh the page.");
      });
    }

    // Cleanup WebSocket on component unmount
    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
        console.log("Socket disconnected.");
      }
    };
  }, [storedSessionId]); // Dependency ensures the effect re-runs only if storedSessionId changes

  // Auto-scroll to the latest message
  useEffect(() => {
    if (conversationRef.current) {
      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
    }
  }, [conversation]);

  // Fetch conversations list on component mount
  useEffect(() => {
    if (storedSessionId) {
      console.log("Fetching /conversations with session_id:", storedSessionId);
      fetchConversations(storedSessionId);
    } else {
      console.warn("Skipping fetchConversations because session_id is undefined");
    }
  }, [storedSessionId]);

  // Fetch Conversations List
  const fetchConversations = async (sessionId) => {
    try {
      const res = await fetch(`/conversations?session_id=${sessionId}`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
      });

      if (res.ok) {
        const data = await res.json();
        setConversationsList((prev) => {
          const newList = data.conversations || [];
          return JSON.stringify(prev) !== JSON.stringify(newList) ? newList : prev;
        });
      } else {
        console.error("Failed to fetch conversations.");
      }
    } catch (err) {
      console.error("Error fetching conversations:", err);
    }
  };
  

  // Handle Selecting a Conversation
  const selectConversation = async (convo) => {
    try {
      const res = await fetch(`/conversations/${convo.id}`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json"
        },
        credentials: "include"
      });
      if (res.ok) {
        const data = await res.json();
        setConversation(data.conversation_history);
        setDrawerOpen(false);
      } else {
        console.error("Failed to fetch conversation.");
      }
    } catch (err) {
      console.error("Error fetching conversation:", err);
    }
  };

  // Handle Starting a New Conversation
  const startNewConversation = async () => {
    try {
      const res = await fetch("/conversations/new", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ title: "New Conversation" }),
        credentials: "include"
      });
      if (res.ok) {
        const data = await res.json();
        // Reset conversation to include the welcome message
        setConversation([
          {
            role: "assistant",
            content: `**Welcome to the USMC AI Agent Demo!**  
I am here to assist you with a variety of tasks. Here are some things you can ask me:

- *"Summarize the latest news about the Marine Corps."*  
- *"Explain the key features of the new tactical vehicle."*  
- *"Generate a briefing on amphibious operations."*  
- *"Create a Python script that automates data analysis."*  

Feel free to type your question below!`,
            id: "welcome",
          },
        ]);
        setError("");
        // Optionally, fetch conversations list again
        // fetchConversations();
      } else {
        console.error("Failed to create new conversation.");
      }
    } catch (err) {
      console.error("Error creating new conversation:", err);
    }
  };

  // Handle File Selection **ADDED**
  const fileInputRef = useRef(null);
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  // Handle Clicking the Upload Button **ADDED**
  const handleUploadClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  // Send Message Logic
  const sendMessage = async () => {
    setError("");
    if (!message.trim() && !selectedFile) { // **CHANGED**
      setError("Please enter a message or upload a file.");
      return;
    }

    if (socketRef.current) {
      console.log("Sending message...");
      console.log("Socket connected?", socketRef.current.connected);
      
      if (socketRef.current.connected) {
        console.log("Socket connected!");
      } else {
        console.warn("Attempted to send message but socket is not connected.");
      }
    } else {
      console.warn("Socket not initialized.");
    }
    
    // const storedSessionId = sessionStorage.getItem("session_id");
    // console.log('storedSessionId', storedSessionId)

    // // or just store in a local variable if needed
    // let storedSessionId = sessionStorage.getItem("session_id");
    // console.log("session_id:", storedSessionId);

    const userMessage = {
      role: "user",
      content: message.trim(),
      id: Date.now(),
      file: selectedFile ? true : false, // **ADDED**
      fileName: selectedFile ? selectedFile.name : null, // **ADDED**
      fileType: selectedFile ? selectedFile.type : null, // **ADDED**
      fileUrl: null, // **ADDED**
    };

    // Generate a unique id for the assistant placeholder
    const placeholderId = Date.now() + 1;

    // Add the user message and assistant placeholder to the conversation
    setConversation((prev) => {
      // Remove the welcome message if it's still present
      const filtered = prev.filter((msg) => msg.id !== "welcome");
      return [
        ...filtered,
        userMessage,
        {
          role: "assistant",
          content: "Assistant is thinking...", // Initial loading text
          loading: true,
          id: placeholderId,
        },
      ];
    });

    setMessage("");
    setSelectedFile(null); // **ADDED**
    setLoading(true);

    // Prepare payload **CHANGED**
    let payload;
    let fetchOptions;

    if (selectedFile) {
      // Use FormData to send file
      payload = new FormData();
      payload.append("message", message.trim());
      payload.append("model", model);
      payload.append("system_prompt", systemPrompt.trim());
      payload.append("temperature", temperature);
      payload.append("file", selectedFile); // **ADDED**
      payload.append("room", storedSessionId); // **ADDED**

      fetchOptions = {
        method: "POST",
        body: payload,
        credentials: "include",
        // Removed 'X-Session-ID' header
      };
    } else {
      // Send as JSON
      payload = {
        message: userMessage.content,
        model,
        system_prompt: systemPrompt.trim(),
        temperature,
        room: storedSessionId, // **ADDED**
      };

      fetchOptions = {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          // Removed 'X-Session-ID' header
        },
        body: JSON.stringify(payload),
        credentials: "include",
      };
    }

    try {
      const res = await fetch("/chat", fetchOptions); // **CHANGED**

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.error || "Failed to fetch.");
      }

      const data = await res.json();
      console.log("Response from /chat:", data);
      const { assistant_reply, intent = {}, fileUrl, fileName, fileType } = data;  // Destructure here

      if (data.error) {
        setError(data.error);
        // Update the placeholder with error message
        setConversation((prev) =>
          prev.map((msg) =>
            msg.id === placeholderId
              ? { ...msg, content: `Error: ${data.error}`, loading: false }
              : msg
          )
        );
      } else {
        // If a file was uploaded, include its URL in the user message
        if (fileUrl && fileName && fileType) { // **ADDED**
          setConversation((prev) =>
            prev.map((msg) =>
              msg.id === userMessage.id
                ? { ...msg, fileUrl, fileName, fileType }
                : msg
            )
          );
        }

        // Determine the loading text based on intent
        let tempLoadingText = "Assistant is thinking...";  // Default loading text
        if (intent.internet_search) {
          tempLoadingText = "Searching the internet...";
        } else if (intent.image_generation) {
          tempLoadingText = "Creating the image...";
        } else if (intent.code_intent) {
          tempLoadingText = "Processing your code request...";
        } // Add more conditions based on your intent keys

        // Update the loadingText state
        console.log('Updating loadingText with:', tempLoadingText)
        setLoadingText(tempLoadingText); // **ADDED**

        // Update the placeholder with the specific loading text
        setConversation((prev) =>
          prev.map((msg) =>
            msg.id === placeholderId
              ? { ...msg, content: tempLoadingText }
              : msg
          )
        );

        // Simulate delay for realistic typing indicator
        setTimeout(() => {
          // Replace the placeholder with the actual assistant reply
          setConversation((prev) =>
            prev.map((msg) =>
              msg.id === placeholderId
                ? { ...msg, content: assistant_reply, loading: false }
                : msg
            )
          );
        }, 1000); // Adjust delay as needed

        if (storedSessionId) {
          console.log("Fetching /conversations with session_id:", storedSessionId);
          fetchConversations(storedSessionId);
        } else {
          console.warn("Skipping fetchConversations because session_id is undefined");
        }
      }
    } catch (err) {
      console.error(err);
      setError("Something went wrong. Check the console.");
      // Update the placeholder with error message
      setConversation((prev) =>
        prev.map((msg) =>
          msg.id === placeholderId
            ? { ...msg, content: "Error: Something went wrong.", loading: false }
            : msg
        )
      );
    } finally {
      setLoading(false);
    }
  };

  // Handle Enter key in multiline TextField
  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <Box
        sx={{
          backgroundColor: 'background.default',
          minHeight: '100vh',
          p: { xs: 1, sm: 2 },
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-start',
          border: 'none',
          margin: 0,
          padding: 0,
        }}
      >
        {/* Container Setup */}
        <Container
          maxWidth="lg"
          sx={{
            mb: { xs: 2, sm: 4 },
            flexGrow: 1,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-start',
            height: { xs: 'auto', sm: '80%' },
            border: 'none',
            width: '100%',
            padding: '0',
            margin: '0',
          }}
        >
          {/* Drawer for Chat History */}
          <Drawer
            variant="persistent"
            anchor="left"
            open={drawerOpen}
            sx={{
              '& .MuiDrawer-paper': {
                width: 240,
                backgroundColor: '#1a1a1a',
                color: '#ffffff',
              },
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', p: 2, justifyContent: 'space-between' }}>
              <Typography variant="h6">Chat History</Typography>
              <IconButton onClick={() => setDrawerOpen(false)} color="primary">
                <CloseIcon />
              </IconButton>
            </Box>
            <Divider />
            <List>
              {conversationsList.map((convo) => (
                <ListItem button key={convo.id} onClick={() => selectConversation(convo)}>
                  <ListItemText
                    primary={convo.title}
                    secondary={new Date(convo.timestamp).toLocaleString()}
                  />
                </ListItem>
              ))}
            </List>
            <Divider />
            <Box sx={{ p: 2 }}>
              <Button variant="contained" color="secondary" fullWidth onClick={startNewConversation}>
                New Conversation
              </Button>
            </Box>
          </Drawer>

          {/* Main Chat Area */}
          <Box
            sx={{
              flexGrow: 1,
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
              borderRadius: 3,
              backgroundColor: 'background.paper',
              boxShadow: 'none',
              border: 'none',
              p: 2,
              ml: drawerOpen ? '240px' : 0,
              transition: 'margin 0.3s',
            }}
          >
            {/* Header */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <IconButton onClick={() => setDrawerOpen(true)} color="primary">
                <MenuIcon />
              </IconButton>
              <Typography variant={isMobile ? "h6" : "h5"} color="primary">
                USMC AI Agent Demo
              </Typography>
              <IconButton onClick={() => setSettingsOpen(!settingsOpen)} color="primary" size="small">
                {settingsOpen ? <CloseIcon /> : <SettingsIcon />}
              </IconButton>
            </Box>

            {/* Settings Panel */}
            {settingsOpen && (
              <Box sx={{ mb: 3 }}>
                <Box sx={{ mb: 2 }}>
                  <TextField
                    label="System Prompt"
                    multiline
                    rows={2}
                    fullWidth
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    sx={{ my: 1 }}
                    InputLabelProps={{ style: { color: '#ffffff' } }}
                    InputProps={{ style: { color: '#ffffff', backgroundColor: '#333333', borderRadius: '4px' } }}
                  />
                </Box>

                <Box sx={{ mb: 2 }}>
                  <FormControl fullWidth>
                    <InputLabel id="model-select-label" sx={{ color: '#ffffff' }}>Model</InputLabel>
                    <Select
                      labelId="model-select-label"
                      value={model}
                      label="Model"
                      onChange={(e) => setModel(e.target.value)}
                      sx={{ color: '#ffffff', backgroundColor: '#333333', borderRadius: '4px' }}
                    >
                      <MenuItem value="gpt-4o">gpt-4o</MenuItem>
                      <MenuItem value="gpt-4o-mini">gpt-4o-mini</MenuItem>
                      <MenuItem value="o1-mini">o1-mini</MenuItem>
                    </Select>
                  </FormControl>
                </Box>

                <Box sx={{ mb: 2 }}>
                  <Typography gutterBottom color="secondary" variant="body2">
                    Temperature: {temperature}
                  </Typography>
                  <Slider
                    min={0}
                    max={1}
                    step={0.1}
                    value={temperature}
                    onChange={(e, val) => setTemperature(val)}
                    sx={{ color: '#FFD700' }}
                  />
                </Box>
              </Box>
            )}

            {/* Conversation Box */}
            <ErrorBoundary>
              <Box
                ref={conversationRef}
                sx={{
                  flexGrow: 1,
                  overflowY: 'auto',
                  maxHeight: { xs: '70vh', sm: '80vh' },
                  mb: 1,
                  pr: { xs: 0, sm: 1 },
                }}
              >
                {/* Standard Mapping to Render Messages */}
                {conversation.map((msg) => (
                  <ChatMessage key={msg.id} msg={msg} loadingText={loadingText} /> // **UPDATED**
                ))}
              </Box>
            </ErrorBoundary>

            {/* Message Input */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {/* Hidden File Input */}
              <input
                type="file"
                accept=".doc,.docx,.xls,.xlsx,.txt,.py,.jsx,.js,.json,.md,.html,.css,.pdf, image/*"
                style={{ display: 'none' }}
                ref={fileInputRef}
                onChange={handleFileUpload}
              />

              {/* Upload Button */}
              <IconButton
                color="primary"
                onClick={handleUploadClick}
                sx={{ p: 1 }}
                aria-label="upload"
              >
                <UploadFileIcon />
              </IconButton>

              {/* Text Input */}
              <TextField
                label="Your Message"
                variant="outlined"
                fullWidth
                multiline
                maxRows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                InputLabelProps={{ style: { color: '#ffffff' } }}
                InputProps={{
                  style: { color: '#ffffff', backgroundColor: '#333333', borderRadius: '4px' },
                }}
                sx={{ flexGrow: 1 }}
              />
              <IconButton
                color="primary"
                onClick={sendMessage}
                disabled={loading}
                sx={{ p: 1 }}
                aria-label="send"
              >
                <SendIcon />
              </IconButton>
              <IconButton
                color="secondary"
                onClick={() => setConversation([])}
                disabled={loading}
                sx={{ p: 1 }}
                aria-label="clear"
              >
                <ClearIcon />
              </IconButton>
            </Box>

            {/* Display Selected File Name **ADDED** */}
            {selectedFile && (
              <Typography variant="body2" sx={{ mt: 1, color: '#FFD700' }}>
                Selected File: {selectedFile.name}
              </Typography>
            )}

            {/* Display Status Message if Exists */}
            {statusMessage && (
              <Typography variant="body2" sx={{ mt: 1, color: '#FFD700' }}>
                Status: {statusMessage}
              </Typography>
            )}

            {/* Error Display */}
            {error && (
              <Typography color="error" sx={{ mt: 1 }}>
                Error: {error}
              </Typography>
            )}

            {/* Footer */}
            <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 1 }}>
              *This is a commercial non-government application and can produce incorrect responses. It is not authorized for CUI data.*
            </Typography>
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default ChatApp;
