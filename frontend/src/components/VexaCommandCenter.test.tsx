import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentModel, ChatMessage } from '../types';
import { VexaCommandCenter } from './VexaCommandCenter';

const agents: AgentModel[] = [
  {
    id: 'research',
    name: 'Research Agent',
    system_prompt: '',
    model: 'qwen3',
    status: 'working',
    current_task: 'Проверяет источники',
  },
  {
    id: 'reviewer',
    name: 'Review Agent',
    system_prompt: '',
    model: 'qwen3',
    status: 'idle',
  },
];

const messages: ChatMessage[] = [
  { role: 'user', content: 'Проверь состояние проекта' },
  { role: 'assistant', content: '**Проверка завершена.** Ошибок нет.', id: 2 },
];

describe('VexaCommandCenter', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ enabled: false, available: false, browser_fallback: true }),
    }));
  });

  it('shows live orchestration state and sends typed commands', () => {
    const onCommand = vi.fn().mockReturnValue(true);
    render(
      <VexaCommandCenter
        agents={agents}
        messages={messages}
        isConnected
        isGenerating={false}
        isSpeaking={false}
        micState="off"
        onVoiceToggle={vi.fn()}
        onCommand={onCommand}
        onStop={vi.fn()}
        language="ru"
      />,
    );

    expect(screen.getByText('Готова к команде')).toBeInTheDocument();
    expect(screen.getByText('Проверка завершена. Ошибок нет.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Скажите или напишите задачу для Vexa'), {
      target: { value: 'Запусти тесты' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Передать команду' }));
    expect(onCommand).toHaveBeenCalledWith('Запусти тесты');
  });

  it('starts voice capture and exposes active agents', () => {
    const onVoiceToggle = vi.fn();
    render(
      <VexaCommandCenter
        agents={agents}
        messages={messages}
        isConnected
        isGenerating={false}
        isSpeaking={false}
        micState="off"
        onVoiceToggle={onVoiceToggle}
        onCommand={vi.fn().mockReturnValue(true)}
        onStop={vi.fn()}
        language="ru"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Начать голосовую команду' }));
    expect(onVoiceToggle).toHaveBeenCalledOnce();
    expect(screen.getByText('Research Agent')).toBeInTheDocument();
  });
});
