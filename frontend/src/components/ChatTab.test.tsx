import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ChatTab } from './ChatTab';

describe('ChatTab Component', () => {
  const defaultProps = {
    currentChatId: 'dashboard',
    chatSessions: [
      { id: 'dashboard', title: 'Main Terminal' },
      { id: 'chat_123', title: 'chat_123' }
    ],
    messages: [
      { role: 'assistant' as const, content: 'Hello, Sir.' },
      { role: 'user' as const, content: 'What is the weather today?' }
    ],
    inputValue: '',
    setInputValue: vi.fn(),
    isSpeaking: false,
    setIsSpeaking: vi.fn(),
    micState: 'off' as const,
    micEnabled: false,
    setMicEnabled: vi.fn(),
    isTTSEnabled: true,
    setIsTTSEnabled: vi.fn(),
    isGenerating: false,
    playingMsgIndex: null,
    setPlayingMsgIndex: vi.fn(),
    config: { system_prompt: 'System prompt', model: 'gpt-4' },
    isConnected: true,
    isUploading: false,
    attachedFile: null,
    setAttachedFile: vi.fn(),
    handleChatFileAttach: vi.fn(),
    speakText: vi.fn(),
    handleClearChat: vi.fn(),
    handleSendMessage: vi.fn(),
    selectChat: vi.fn(),
    handleCreateNewSession: vi.fn(),
    fetchChatSessions: vi.fn(),
    getSessionLabel: (id: string) => id === 'dashboard' ? 'Main Terminal' : id,
    mainChatEndRef: React.createRef<HTMLDivElement>(),
    subagents: [],
    handleSetSessionAgent: vi.fn(),
    fetchWithAuth: vi.fn()
  };

  it('renders messages correctly', () => {
    render(<ChatTab {...defaultProps} />);
    
    expect(screen.getByText('Hello, Sir.')).toBeInTheDocument();
    expect(screen.getByText('What is the weather today?')).toBeInTheDocument();
    
    expect(screen.getByText('JARVIS')).toBeInTheDocument();
    expect(screen.getByText('CREATOR')).toBeInTheDocument();
  });

  it('triggers setInputValue on text entry', () => {
    render(<ChatTab {...defaultProps} />);
    
    const input = screen.getByPlaceholderText(/Enter command or request for Jarvis/i);
    fireEvent.change(input, { target: { value: 'New message' } });
    
    expect(defaultProps.setInputValue).toHaveBeenCalledWith('New message');
  });

  it('calls handleSendMessage on submit click', () => {
    const props = {
      ...defaultProps,
      inputValue: 'Hello',
      handleSendMessage: vi.fn((e) => e.preventDefault())
    };
    render(<ChatTab {...props} />);
    
    const form = screen.getByRole('button', { name: /send/i }).closest('form');
    if (!form) throw new Error('Form not found');
    fireEvent.submit(form);
    
    expect(props.handleSendMessage).toHaveBeenCalled();
  });

  it('lists active chat sessions in the sidebar', () => {
    render(<ChatTab {...defaultProps} />);
    
    expect(screen.getAllByText('Main Terminal').length).toBeGreaterThan(0);
    expect(screen.getByText('chat_123')).toBeInTheDocument();
  });
});
