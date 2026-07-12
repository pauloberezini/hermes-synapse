import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ChatTab } from './ChatTab';

describe('ChatTab Component', () => {
  const defaultProps = {
    currentChatId: 'dashboard',
    chatSessions: ['dashboard', 'chat_123'],
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
    onVoiceToggle: vi.fn(),
    isTTSEnabled: true,
    setIsTTSEnabled: vi.fn(),
    isGenerating: false,
    playingMsgIndex: null,
    setPlayingMsgIndex: vi.fn(),
    config: { system_prompt: 'System prompt', model: 'gpt-4' },
    isConnected: true,
    isUploading: false,
    speakText: vi.fn(),
    handleClearChat: vi.fn(),
    handleSendMessage: vi.fn(),
    handleFileUpload: vi.fn(),
    selectChat: vi.fn(),
    handleCreateNewSession: vi.fn(),
    fetchChatSessions: vi.fn(),
    getSessionLabel: (id: string) => id === 'dashboard' ? 'Main Terminal' : id,
    mainChatEndRef: React.createRef<HTMLDivElement>()
  };

  it('renders messages correctly', () => {
    render(<ChatTab {...defaultProps} />);
    
    expect(screen.getByText('Hello, Sir.')).toBeInTheDocument();
    expect(screen.getByText('What is the weather today?')).toBeInTheDocument();
    
    expect(screen.getByText('VEXA')).toBeInTheDocument();
    expect(screen.getByText('CREATOR')).toBeInTheDocument();
  });

  it('triggers setInputValue on text entry', () => {
    render(<ChatTab {...defaultProps} />);
    
    const input = screen.getByPlaceholderText(/Enter command or request for Vexa/i);
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

  it('disables send while generating', () => {
    render(<ChatTab {...defaultProps} inputValue="hi" isGenerating={true} />);
    const send = screen.getByRole('button', { name: /send/i });
    expect(send).toBeDisabled();
  });

  it('shows a Stop button while generating and calls onStopGeneration', () => {
    const onStopGeneration = vi.fn();
    render(<ChatTab {...defaultProps} isGenerating={true} onStopGeneration={onStopGeneration} />);
    const stop = screen.getByRole('button', { name: /stop/i });
    fireEvent.click(stop);
    expect(onStopGeneration).toHaveBeenCalled();
  });

  it('renders an empty state when there are no messages', () => {
    render(<ChatTab {...defaultProps} messages={[]} />);
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
  });

  it('shows an offline banner when disconnected', () => {
    render(<ChatTab {...defaultProps} isConnected={false} />);
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
  });

  it('shows Retry action for an empty response and calls onRetryLast', () => {
    const onRetryLast = vi.fn();
    render(
      <ChatTab
        {...defaultProps}
        hasLastUserMessage={true}
        onRetryLast={onRetryLast}
        messages={[{ role: 'assistant' as const, content: '', meta: { status: 'empty' } }]}
      />
    );
    const retry = screen.getByRole('button', { name: /retry/i });
    fireEvent.click(retry);
    expect(onRetryLast).toHaveBeenCalled();
  });

  it('filters sessions by search query', () => {
    render(<ChatTab {...defaultProps} />);
    const search = screen.getByPlaceholderText(/search sessions/i);
    fireEvent.change(search, { target: { value: 'zzz-no-match' } });
    // dashboard is always kept; the other session is filtered out.
    expect(screen.queryByText('chat_123')).not.toBeInTheDocument();
  });
});
