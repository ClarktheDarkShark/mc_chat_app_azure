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
  ListItemButton,
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

// ErrorBoundary to catch rendering errors
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
          Something went wrong while rendering messages: {this.state.error.toString()}
        </Typography>
      );
    }
    return this.props.children;
  }
}

// MUI theme config
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

// Memoized ChatMessage
const ChatMessage = memo(
  ({ msg, loadingText }) => {
    const isAssistant = msg.role === "assistant";
    const isFile = msg.role === "user" && msg.file;
    const isImage =
      msg.role === "assistant" && msg.content.startsWith("![Generated Image](");

    let contentToRender;
    if (msg.loading) {
      // loading message
      contentToRender = (
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <CircularProgress size={20} color="secondary" />
          <Typography variant="body2" sx={{ ml: 1 }}>
            {msg.content}
          </Typography>
        </Box>
      );
    } else if (isImage) {
      // assistant image
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
      // user uploaded file
      const { fileUrl, fileName, fileType } = msg;
      if (fileType?.startsWith("image/")) {
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
      // assistant text
      contentToRender = (
        <ReactMarkdown>{msg.content || "**(No content available)**"}</ReactMarkdown>
      );
    } else {
      // user text
      contentToRender = (
        <Typography variant="body1">{msg.content || "No response available."}</Typography>
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
          p: isFile || isImage ? 0 : 1,
          maxWidth: '80%',
          ml: msg.role === "user" ? 'auto' : 0,
          mb: 1,
        }}
      >
        {contentToRender}
      </Box>
    );
  },
  (prevProps, nextProps) =>
    prevProps.msg.id === nextProps.msg.id &&
    prevProps.msg.content === nextProps.msg.content &&
    prevProps.loadingText === nextProps.loadingText
);

function ChatApp() {
  // Utility to generate a random GUID
  const generateUUID = () =>
    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0,
        v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });

  // Basic state
  const muiTheme = useTheme();
  const isMobile = useMediaQuery(muiTheme.breakpoints.down("md"));
  const [message, setMessage] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [temperature, setTemperature] = useState(0.7);
  const [systemPrompt, setSystemPrompt] = useState("You are a USMC AI agent. Provide relevant responses.");
  const [statusMessage, setStatusMessage] = useState("");
  const [loadingText, setLoadingText] = useState("Assistant is thinking...");

  // Utility: Generate a welcome message
  const welcomeMessage = {
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
  };

  // session_id stored in localStorage
  const [storedSessionId, setStoredSessionId] = useState(() => {
    let id = localStorage.getItem("session_id");
    if (!id) {
      id = generateUUID();
      localStorage.setItem("session_id", id);

      // Immediately archive the new thread
      const newThreadArchive = {
        id: Date.now(), // Unique archive id
        timestamp: new Date().toISOString(),
        session_id: id,
        messages: [welcomeMessage],
      };
      const existingArchives = localStorage.getItem("savedConversations");
      const updatedArchives = existingArchives
        ? [...JSON.parse(existingArchives), newThreadArchive]
        : [newThreadArchive];
      localStorage.setItem("savedConversations", JSON.stringify(updatedArchives));
    }
    return id;
  });

  // Active conversation in the UI
  const [conversation, setConversation] = useState([welcomeMessage]);

  // Local "archive" of prior conversations, each with its own session_id, messages, etc.
  const [savedConversations, setSavedConversations] = useState(() => {
    const stored = localStorage.getItem("savedConversations");
    return stored ? JSON.parse(stored) : [];
  });

  // We still keep the server-based "conversationsList" just in case, but we won't rely on it
  const [conversationsList, setConversationsList] = useState([]);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);

  // Refs
  const conversationRef = useRef(null);
  const fileInputRef = useRef(null);
  const socketRef = useRef(null);

  // Initialize WebSocket
  useEffect(() => {
    if (!socketRef.current) {
      socketRef.current = io("/", {
        transports: ["websocket"],
        withCredentials: true,
        query: { session_id: storedSessionId },
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
      });

      socketRef.current.on("connected", (data) => {
        console.log("Connected with session_id:", data.session_id);
      });

      socketRef.current.on("connect_error", (err) => {
        console.error("WebSocket Connection Error:", err.message);
        setError("WebSocket connection failed. Please refresh the page.");
      });

      socketRef.current.on("task_complete", () => {
        setStatusMessage("");
      });

      socketRef.current.io.on("reconnect_attempt", () => {
        console.log("Attempting to reconnect...");
      });

      socketRef.current.io.on("reconnect_failed", () => {
        console.error("Reconnection failed.");
        setError("Unable to reconnect to the server.");
      });
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
        console.log("Socket disconnected.");
      }
    };
  }, [storedSessionId]);

  // Auto-scroll to the latest message
  useEffect(() => {
    if (conversationRef.current) {
      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
    }
  }, [conversation]);

  // Minimal server-based conversation fetch
  useEffect(() => {
    if (storedSessionId) {
      fetchConversations(storedSessionId);
    }
  }, [storedSessionId]);

  useEffect(() => {
    let inactivityTimer;

    const resetTimer = () => {
      if (inactivityTimer) clearTimeout(inactivityTimer);
      inactivityTimer = setTimeout(() => {
        fetch("/ping", { method: "GET", credentials: "include" })
          .then((res) => console.log("Pinged server to keep DB alive:", res.status))
          .catch((err) => console.error("Ping error:", err));
      }, 2 * 60 * 1000); // 2 minutes
    };

    // Add event listeners for user interactions
    window.addEventListener("mousemove", resetTimer);
    window.addEventListener("keydown", resetTimer);

    // Call resetTimer initially
    resetTimer();

    // Cleanup event listeners on component unmount
    return () => {
      window.removeEventListener("mousemove", resetTimer);
      window.removeEventListener("keydown", resetTimer);
      if (inactivityTimer) clearTimeout(inactivityTimer);
    };
  }, []);

  const fetchConversations = async (sessionId) => {
    try {
      const res = await fetch(`/conversations?session_id=${sessionId}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        const newList = data.conversations || [];
        setConversationsList((prev) =>
          JSON.stringify(prev) !== JSON.stringify(newList) ? newList : prev
        );
      } else {
        console.error("Failed to fetch conversations from server.");
      }
    } catch (err) {
      console.error("Error fetching from /conversations:", err);
    }
  };

  // (B) Manage local "archived" conversations
  const archiveCurrentConversation = () => {
    if (!conversation || conversation.length === 0) return;
    // Archive the entire thread, including the current session_id
    const newArchive = {
      id: Date.now(),
      timestamp: new Date().toISOString(),
      session_id: storedSessionId,  // store the session_id used by this thread
      messages: [...conversation],
    };
    const updated = [...savedConversations, newArchive];
    setSavedConversations(updated);
    localStorage.setItem("savedConversations", JSON.stringify(updated));
  };

  const loadArchivedConversation = async (archiveId) => {
    const found = savedConversations.find((c) => c.id === archiveId);
    if (found) {
      // Set the current session_id to that of the archived conversation.
      setStoredSessionId(found.session_id);
      localStorage.setItem("session_id", found.session_id);
  
      try {
        const res = await fetch(`/conversations?session_id=${found.session_id}`, {
          method: "GET",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          // Expect the server to return conversation history now
          if (data.conversation && data.conversation.conversation_history && data.conversation.conversation_history.length > 0) {
            setConversation(data.conversation.conversation_history);
          } else {
            // Fall back to local archive if server returns empty history
            setConversation(found.messages);
          }
        } else {
          console.error("Failed to fetch archived conversation from server, using local data.");
          setConversation(found.messages);
        }
      } catch (err) {
        console.error("Error fetching archived conversation from server:", err);
        setConversation(found.messages);
      }
      setDrawerOpen(false);
    }
  };
  
  

  const deleteArchivedConversation = (archiveId) => {
    const updated = savedConversations.filter((c) => c.id !== archiveId);
    setSavedConversations(updated);
    localStorage.setItem("savedConversations", JSON.stringify(updated));
  };
  

  // (C) "New Conversation" => get fresh session_id from server, reset UI
  const startNewConversation = async () => {
    // Archive whatever is currently on screen
    archiveCurrentConversation();

    // Create a new conversation (and new session_id) from the server
    try {
      const res = await fetch("/conversations/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Conversation" }),
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        // Store the new session_id in state & localStorage
        setStoredSessionId(data.session_id);
        localStorage.setItem("session_id", data.session_id);

        // Clear the UI with a fresh welcome message
        const welcomeMessage = {
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
        };
  
        // Reset the UI with only the welcome message.
        setConversation([welcomeMessage]);
  
        // Immediately archive the new thread, so that its button appears.
        const newThreadArchive = {
          id: Date.now(), // Unique archive id
          timestamp: new Date().toISOString(),
          session_id: data.session_id,
          messages: [welcomeMessage],
        };
        const updated = [...savedConversations, newThreadArchive];
        setSavedConversations(updated);
        localStorage.setItem("savedConversations", JSON.stringify(updated));

        setError("");
        fetchConversations(data.session_id);
      } else {
        console.error("Failed to create new conversation.");
      }
    } catch (err) {
      console.error("Error creating conversation:", err);
    }
  };

  // (D) File handling
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) setSelectedFile(file);
  };
  const handleUploadClick = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  // (E) Sending a message
  const sendMessage = async () => {
    setError("");
    if (!message.trim() && !selectedFile) {
      setError("Please enter a message or upload a file.");
      return;
    }

    if (!socketRef.current || !socketRef.current.connected) {
      console.warn("Socket not connected, but proceeding...");
    }

    const userMessage = {
      role: "user",
      content: message.trim(),
      id: Date.now(),
      file: !!selectedFile,
      fileName: selectedFile?.name || null,
      fileType: selectedFile?.type || null,
      fileUrl: null,
    };
    const placeholderId = userMessage.id + 1;

    // Insert user message and a placeholder for the assistant
    setConversation((prev) => {
      const filtered = prev.filter((m) => m.id !== "welcome");
      return [
        ...filtered,
        userMessage,
        {
          role: "assistant",
          content: "Assistant is thinking...",
          loading: true,
          id: placeholderId,
        },
      ];
    });
    setMessage("");
    setSelectedFile(null);
    setLoading(true);

    // Prepare fetch
    let payload;
    let fetchOptions;
    if (selectedFile) {
      payload = new FormData();
      payload.append("message", userMessage.content);
      payload.append("model", model);
      payload.append("system_prompt", systemPrompt.trim());
      payload.append("temperature", temperature);
      payload.append("file", selectedFile);
      payload.append("room", storedSessionId);

      fetchOptions = { method: "POST", body: payload, credentials: "include" };
    } else {
      payload = {
        message: userMessage.content,
        model,
        system_prompt: systemPrompt.trim(),
        temperature,
        room: storedSessionId,
      };
      fetchOptions = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        credentials: "include",
      };
    }

    try {
      const res = await fetch("/chat", fetchOptions);
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Failed to fetch.");
      }
      const data = await res.json();
      const { assistant_reply, intent = {}, fileUrl, fileName, fileType } = data;

      if (data.error) {
        setError(data.error);
        setConversation((prev) =>
          prev.map((m) =>
            m.id === placeholderId
              ? { ...m, content: `Error: ${data.error}`, loading: false }
              : m
          )
        );
      } else {
        // If file was uploaded, add its info to the user message
        if (fileUrl && fileName && fileType) {
          setConversation((prev) =>
            prev.map((m) =>
              m.id === userMessage.id
                ? { ...m, fileUrl, fileName, fileType }
                : m
            )
          );
        }

        // Adjust the loading text
        let tempLoadingText = "Assistant is thinking...";
        if (intent.internet_search) tempLoadingText = "Searching the internet...";
        else if (intent.image_generation) tempLoadingText = "Creating the image...";
        else if (intent.code_intent) tempLoadingText = "Processing your code request...";

        setLoadingText(tempLoadingText);
        setConversation((prev) =>
          prev.map((m) => (m.id === placeholderId ? { ...m, content: tempLoadingText } : m))
        );

        // Simulate a short delay, then set the final assistant reply
        setTimeout(() => {
          setConversation((prev) =>
            prev.map((m) =>
              m.id === placeholderId
                ? { ...m, content: assistant_reply, loading: false }
                : m
            )
          );
        }, 1000);

        // Optionally re-fetch server conversation
        if (storedSessionId) fetchConversations(storedSessionId);
      }
    } catch (err) {
      console.error(err);
      setError("Something went wrong. Check the console.");
      setConversation((prev) =>
        prev.map((m) =>
          m.id === placeholderId
            ? { ...m, content: "Error: Something went wrong.", loading: false }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  };

  // Clear current chat from UI (not archived)
  const clearChat = () => {
    setConversation([]);
  };

  // Render
  return (
    <ThemeProvider theme={theme}>
      <Box
        sx={{
          backgroundColor: "background.default",
          minHeight: "90vh",
          p: { xs: 1, sm: 2 },
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          margin: 0,
          padding: 0,
        }}
      >
        <Container
          maxWidth="lg"
          sx={{
            mb: { xs: 2, sm: 4 },
            flexGrow: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            height: { xs: "auto", sm: "80%" },
            border: "none",
            width: "100%",
            padding: 0,
            margin: 0,
            // Center the conversation
            mx: "auto",
          }}
        >
          {/* Drawer for Chat History */}
          <Drawer
            variant="persistent"
            anchor="left"
            open={drawerOpen}
            sx={{
              "& .MuiDrawer-paper": {
                width: 240,
                backgroundColor: "#1a1a1a",
                color: "#ffffff",
              },
            }}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                p: 2,
                justifyContent: "space-between",
              }}
            >
              <Typography variant="h6">Chat History</Typography>
              <IconButton onClick={() => setDrawerOpen(false)} color="primary">
                <CloseIcon />
              </IconButton>
            </Box>
            <Divider />

            {/* List of archived conversations */}
            <List>
              {savedConversations.map((c) => (
                <ListItem
                  key={c.id}
                  secondaryAction={
                    <IconButton edge="end" aria-label="delete" onClick={() => deleteArchivedConversation(c.id)}>
                      <CloseIcon />
                    </IconButton>
                  }
                >
                   <ListItemButton
                      onClick={() => loadArchivedConversation(c.id)}
                      selected={c.session_id === storedSessionId}  // Highlight if current
                    >
                    <ListItemText
                      primary={`Conversation #${c.id}`}
                      secondary={new Date(c.timestamp).toLocaleString()}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>

            <Divider />
            <Box sx={{ p: 2 }}>
              <Button
                variant="contained"
                color="secondary"
                fullWidth
                onClick={startNewConversation}
              >
                New Conversation
              </Button>
            </Box>
          </Drawer>

          {/* Main Chat Area */}
          <Box
            sx={{
              flexGrow: 1,
              display: "flex",
              flexDirection: "column",
              height: "95%",
              borderRadius: 3,
              backgroundColor: "background.paper",
              border: "none",
              p: 2,
              ml: drawerOpen ? "240px" : 0,
              transition: "margin 0.3s",
              // Center the conversation
              mx: "auto",
              width: "100%",
            }}
          >
          {/* Header */}
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              mb: 2,
              background: "linear-gradient(to right,rgb(0, 0, 0),rgb(0, 0, 0))", // Modern gradient
              p: 1,
              borderRadius: 2, // Slightly rounded corners
              boxShadow: "0px 4px 10px rgba(0, 0, 0, 0.3)", // Subtle shadow for depth
            }}
          >
            <IconButton
              onClick={() => setDrawerOpen(true)}
              sx={{
                color: "primary.main", 
                "&:hover": {
                  backgroundColor: "rgba(255, 255, 255, 0.2)", // Hover effect
                },
              }}
            >
              <MenuIcon />
            </IconButton>

            <Typography
              variant={isMobile ? "h6" : "h5"}
              sx={{
                color: "primary.main",
                fontWeight: "bold", // Bolder typography
                textShadow: "1px 1px 4px rgba(0, 0, 0, 0.5)", // Add subtle text shadow
              }}
            >
              USMC AI Agent Demo
            </Typography>

            <IconButton
              onClick={() => setSettingsOpen(!settingsOpen)}
              sx={{
                color: "primary.main", 
                "&:hover": {
                  backgroundColor: "rgba(255, 255, 255, 0.2)", // Hover effect
                },
              }}
              size="medium" // Slightly larger size for better visibility
            >
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
                    InputLabelProps={{ style: { color: "#ffffff" } }}
                    InputProps={{
                      style: {
                        color: "#ffffff",
                        backgroundColor: "#333333",
                        borderRadius: "4px",
                      },
                    }}
                  />
                </Box>

                <Box sx={{ mb: 2 }}>
                  <FormControl fullWidth>
                    <InputLabel id="model-select-label" sx={{ color: "#ffffff" }}>
                      Model
                    </InputLabel>
                    <Select
                      labelId="model-select-label"
                      value={model}
                      label="Model"
                      onChange={(e) => setModel(e.target.value)}
                      sx={{
                        color: "#ffffff",
                        backgroundColor: "#333333",
                        borderRadius: "4px",
                      }}
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
                    sx={{ color: "#FFD700" }}
                  />
                </Box>
              </Box>
            )}

            {/* Conversation Box */}
            <ErrorBoundary>
              <Box
                ref={conversationRef}
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "flex-end",
                  flexGrow: 1,
                  overflowY: "auto",
                  maxHeight: { xs: "70vh", sm: "80vh" },
                  mb: 1,
                  pr: { xs: 0, sm: 1 },
                }}
              >
                {conversation.map((msg) => (
                  <ChatMessage key={msg.id} msg={msg} loadingText={loadingText} />
                ))}
              </Box>
            </ErrorBoundary>

            {/* Message Input */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <input
                type="file"
                accept=".doc,.docx,.xls,.xlsx,.txt,.py,.jsx,.js,.json,.md,.html,.css,.pdf, image/*"
                style={{ display: "none" }}
                ref={fileInputRef}
                onChange={handleFileUpload}
              />

              <IconButton color="primary" onClick={handleUploadClick} sx={{ p: 1 }}>
                <UploadFileIcon />
              </IconButton>

              <TextField
                label="Your Message"
                variant="outlined"
                fullWidth
                multiline
                maxRows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                InputLabelProps={{ style: { color: "#ffffff" } }}
                InputProps={{
                  style: {
                    color: "#ffffff",
                    backgroundColor: "#333333",
                    borderRadius: "4px",
                  },
                }}
              />
              <IconButton
                color="primary"
                onClick={sendMessage}
                disabled={loading}
                sx={{ p: 1 }}
              >
                <SendIcon />
              </IconButton>
              <IconButton
                color="secondary"
                onClick={clearChat}
                disabled={loading}
                sx={{ p: 1 }}
              >
                <ClearIcon />
              </IconButton>
            </Box>

            {/* Optional status, errors, file name */}
            {selectedFile && (
              <Typography variant="body2" sx={{ mt: 1, color: "#FFD700" }}>
                Selected File: {selectedFile.name}
              </Typography>
            )}

            {statusMessage && (
              <Typography variant="body2" sx={{ mt: 1, color: "#FFD700" }}>
                Status: {statusMessage}
              </Typography>
            )}

            {error && (
              <Typography color="error" sx={{ mt: 1 }}>
                Error: {error}
              </Typography>
            )}

            <Typography
              variant="body2"
              color="text.secondary"
              align="center"
              sx={{ mt: 1 }}
            >
              *This is a commercial non-government application and can produce
              incorrect responses. It is not authorized for CUI data.*
            </Typography>
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default ChatApp;
