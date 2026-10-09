package com.csr.chat.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.List;

public record ChatRequest(
    @NotBlank(message = "消息内容不能为空")
    String message,
    List<ChatHistoryItem> history
) {}
