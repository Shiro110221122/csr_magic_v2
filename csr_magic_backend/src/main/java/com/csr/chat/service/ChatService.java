package com.csr.chat.service;

import com.csr.chat.dto.ChatHistoryItem;
import com.csr.chat.dto.ChatResponse;
import java.util.List;

public interface ChatService {
    ChatResponse processMessage(Long userId, Long activityId, String message, List<ChatHistoryItem> history);
    ChatResponse processGlobalMessage(Long userId, String message, List<ChatHistoryItem> history);
}
