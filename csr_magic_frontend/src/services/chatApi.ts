import apiClient from './apiClient';
import type { ApiResponse } from '../types/common';

export interface ChatHistoryItem {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatMessageRequest {
  message: string;
  history: ChatHistoryItem[];
}

export interface ChatMessageResponse {
  reply: string;
}

export const chatApi = {
  sendMessage: (activityId: number, data: ChatMessageRequest) =>
    apiClient.post<ApiResponse<ChatMessageResponse>>(
      `/api/v2/activities/${activityId}/chat`,
      data
    ),
  sendGlobalMessage: (data: ChatMessageRequest) =>
    apiClient.post<ApiResponse<ChatMessageResponse>>('/api/v2/chat', data),
};
