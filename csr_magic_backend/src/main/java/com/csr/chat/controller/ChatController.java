package com.csr.chat.controller;

import com.csr.chat.dto.ChatRequest;
import com.csr.chat.dto.ChatResponse;
import com.csr.chat.service.ChatService;
import com.csr.common.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

@RestController
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @PostMapping("/api/v2/activities/{activityId}/chat")
    public ApiResponse<ChatResponse> chat(
            @PathVariable Long activityId,
            @Valid @RequestBody ChatRequest request
    ) {
        Long userId = getCurrentUserId();
        ChatResponse response = chatService.processMessage(
                userId, activityId, request.message(), request.history());
        return ApiResponse.success(response);
    }

    @PostMapping("/api/v2/chat")
    public ApiResponse<ChatResponse> globalChat(@Valid @RequestBody ChatRequest request) {
        Long userId = getCurrentUserId();
        ChatResponse response = chatService.processGlobalMessage(userId, request.message(), request.history());
        return ApiResponse.success(response);
    }

    private Long getCurrentUserId() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        return Long.parseLong(auth.getName());
    }
}
