import { useEffect, useState, useRef } from 'react';
import './Chat.css';
import { useMsal } from '@azure/msal-react';
import { WebSocketClient } from '@/api/socket';

const Chat = () => {
  const { instance } = useMsal();
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const socketClientRef = useRef(null);

  useEffect(() => {
    // Create WebSocket client instance
    if (!socketClientRef.current) {
      socketClientRef.current = new WebSocketClient('api/chat');
    }
    const socketClient = socketClientRef.current;

    // Connect to WebSocket when component mounts
    socketClient.connect(instance);
    
    // Subscribe to messages and status updates.
    // `subscribe` is the only message-subscription method on the current
    // WebSocketClient. An earlier `subscribeToMessages` alias is no longer
    // expected; if a future client ships without `subscribe`, surface the
    // configuration error rather than silently dropping every message.
    if (typeof socketClient.subscribe !== 'function') {
      console.error('WebSocketClient is missing subscribe method');
      setError('WebSocket client configuration error');
      return;
    }
    
    const unsubscribe = socketClient.subscribe((message) => {
      setMessages(prevMessages => [...prevMessages, message]);
    });
    
    const unsubscribeStatus = socketClient.subscribeToStatus((status) => {
      setConnectionStatus(status);
      if (status === 'error') {
        setError("Failed to connect to chat server");
      } else {
        setError(null);
      }
    });
    
    // Clean up on unmount
    return () => {
      unsubscribe();
      unsubscribeStatus();
      socketClient.disconnect();
    };
  }, [instance]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const sendMessage = () => {
    if (inputMessage.trim() && connectionStatus === 'connected') {
      socketClientRef.current.send(inputMessage);
      setInputMessage('');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  };

  return (
    <div className="chat-container" data-testid="chat-page">
      <h2>Live Chat</h2>
      
      <div className="status-indicator">
        Status: 
        <span className={`status-${connectionStatus}`}>
          {connectionStatus === 'connected' ? 'Connected' : 
           connectionStatus === 'disconnected' ? 'Disconnected' : 'Error'}
        </span>
        {error && <div className="error-message">{error}</div>}
      </div>
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="empty-messages">No messages yet. Start chatting!</div>
        ) : (
          messages.map((msg, index) => (
            <div key={index} className={`message ${msg.type}`}>
              <span className="timestamp">{msg.timestamp}</span>
              {msg.username && <span className="username">{msg.username}</span>}
              <span className="text">{msg.parsedText || msg.text}</span>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <div className="chat-input">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type a message..."
          disabled={connectionStatus !== 'connected'}
        />
        <button 
          onClick={sendMessage}
          disabled={connectionStatus !== 'connected' || !inputMessage.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
};

export default Chat;