package com.csr.chat.service;

import com.csr.activity.entity.Activity;
import com.csr.activity.repository.ActivityRepository;
import com.csr.auth.entity.User;
import com.csr.auth.repository.UserRepository;
import com.csr.chat.dto.ChatHistoryItem;
import com.csr.chat.dto.ChatResponse;
import com.csr.common.BusinessException;
import com.csr.participation.dto.SignupRequest;
import com.csr.participation.entity.ParticipationState;
import com.csr.participation.entity.UserActivity;
import com.csr.participation.repository.UserActivityRepository;
import com.csr.participation.service.ParticipationService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class ChatServiceImpl implements ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatServiceImpl.class);

    private final ActivityRepository activityRepository;
    private final UserRepository userRepository;
    private final UserActivityRepository userActivityRepository;
    private final ParticipationService participationService;
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper;

    @Value("${ai-service.base-url:http://localhost:8000}")
    private String aiServiceBaseUrl;

    @Value("${ai-service.api-token:}")
    private String aiServiceApiToken;

    public ChatServiceImpl(ActivityRepository activityRepository,
                           UserRepository userRepository,
                           UserActivityRepository userActivityRepository,
                           ParticipationService participationService,
                           ObjectMapper objectMapper) {
        this.activityRepository = activityRepository;
        this.userRepository = userRepository;
        this.userActivityRepository = userActivityRepository;
        this.participationService = participationService;
        this.objectMapper = objectMapper;
    }

    @Override
    public ChatResponse processMessage(Long userId, Long activityId, String message, List<ChatHistoryItem> history) {
        Activity activity = activityRepository.findById(activityId)
                .orElseThrow(() -> new BusinessException(404, "活动不存在"));

        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(404, "用户不存在"));

        // 构造发给 AI 服务的请求体
        Map<String, Object> activityInfo = new HashMap<>();
        activityInfo.put("id", activity.getId());
        activityInfo.put("name", activity.getName());
        activityInfo.put("templateType", activity.getTemplateType().name());
        activityInfo.put("allowFamily", activity.isAllowFamily());
        if (activity.getFormSchema() != null) {
            try {
                activityInfo.put("formSchema", objectMapper.readValue(activity.getFormSchema(), new TypeReference<List<Map<String, Object>>>() {}));
            } catch (Exception e) {
                log.warn("formSchema 解析失败，跳过: {}", e.getMessage());
            }
        }

        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("id", user.getId());
        userInfo.put("displayName", user.getDisplayName() != null ? user.getDisplayName() : user.getUsername());
        userInfo.put("email", user.getUsername()); // username 是 email

        Map<String, Object> body = new HashMap<>();
        body.put("message", message);
        body.put("history", history != null ? history : List.of());
        body.put("activity", activityInfo);
        body.put("user", userInfo);

        Map<String, Object> aiResponse = callAiService("/chat/message", body);
        String reply = (String) aiResponse.getOrDefault("reply", "抱歉，AI 服务暂时无法响应。");
        String action = (String) aiResponse.get("action");

        if ("signup".equals(action)) {
            return handleSignup(userId, activity, user, aiResponse);
        }

        if ("withdraw".equals(action)) {
            return handleWithdraw(userId, activity, user);
        }

        return new ChatResponse(reply);
    }

    private ChatResponse handleSignup(Long userId, Activity activity, User user, Map<String, Object> aiResponse) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> formData = (Map<String, Object>) aiResponse.get("form_data");
            String formDataJson = (formData != null && !formData.isEmpty())
                    ? serialize(formData) : null;

            participationService.signup(userId, new SignupRequest(activity.getId(), formDataJson));
            String resultReply = callResultReply("signup_success", activity.getName(), user.getDisplayName());
            return new ChatResponse(resultReply);

        } catch (BusinessException e) {
            // 23505 = 唯一约束，重复报名
            boolean isDuplicate = e.getMessage() != null && e.getMessage().contains("重复") ||
                    e.getMessage() != null && e.getMessage().contains("已报名");
            String scenario = isDuplicate ? "signup_duplicate" : "signup_failure";
            log.warn("报名失败: activityId={} userId={} error={}", activity.getId(), userId, e.getMessage());
            String resultReply = callResultReply(scenario, activity.getName(), user.getDisplayName());
            return new ChatResponse(resultReply);

        } catch (Exception e) {
            log.error("报名异常: activityId={} userId={}", activity.getId(), userId, e);
            String resultReply = callResultReply("signup_failure", activity.getName(), user.getDisplayName());
            return new ChatResponse(resultReply);
        }
    }

    private ChatResponse handleWithdraw(Long userId, Activity activity, User user) {
        Optional<UserActivity> ua = userActivityRepository.findByUserIdAndActivityId(userId, activity.getId());
        if (ua.isEmpty()) {
            return new ChatResponse("未找到你在「" + activity.getName() + "」的报名记录。");
        }
        if (ua.get().getState() != ParticipationState.PENDING) {
            return new ChatResponse("该报名已不在待审核状态，无法取消。如需处理请联系管理员。");
        }
        try {
            participationService.withdraw(ua.get().getId(), userId);
            String resultReply = callResultReply("withdraw_success", activity.getName(), user.getDisplayName());
            return new ChatResponse(resultReply);
        } catch (Exception e) {
            log.error("取消报名异常: participationId={} userId={}", ua.get().getId(), userId, e);
            String resultReply = callResultReply("withdraw_failure", activity.getName(), user.getDisplayName());
            return new ChatResponse(resultReply);
        }
    }

    @Override
    public ChatResponse processGlobalMessage(Long userId, String message, List<ChatHistoryItem> history) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(404, "用户不存在"));

        List<Activity> allActivities = activityRepository.findAll();
        List<UserActivity> myParticipations = userActivityRepository.findByUserId(userId);

        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("id", user.getId());
        userInfo.put("displayName", user.getDisplayName() != null ? user.getDisplayName() : user.getUsername());
        userInfo.put("email", user.getUsername());

        List<Map<String, Object>> activitiesInfo = allActivities.stream().map(a -> {
            Map<String, Object> m = new HashMap<>();
            m.put("id", a.getId());
            m.put("name", a.getName());
            m.put("description", a.getDescription());
            m.put("templateType", a.getTemplateType().name());
            m.put("status", a.getStatus());
            m.put("maxParticipants", a.getMaxParticipants());
            m.put("allowFamily", a.isAllowFamily());
            return m;
        }).toList();

        List<Map<String, Object>> myParticipationsInfo = myParticipations.stream().map(ua -> {
            Map<String, Object> m = new HashMap<>();
            m.put("id", ua.getId());
            m.put("activityId", ua.getActivity().getId());
            m.put("activityName", ua.getActivity().getName());
            m.put("state", ua.getState().name());
            return m;
        }).toList();

        Map<String, Object> body = new HashMap<>();
        body.put("message", message);
        body.put("history", history != null ? history : List.of());
        body.put("activities", activitiesInfo);
        body.put("user", userInfo);
        body.put("my_participations", myParticipationsInfo);

        Map<String, Object> aiResponse = callAiService("/chat/global", body);
        String reply = (String) aiResponse.getOrDefault("reply", "抱歉，AI 服务暂时无法响应。");
        String action = (String) aiResponse.get("action");

        log.info("Global chat AI response: action={} activity_id={} participation_id={}",
                action, aiResponse.get("activity_id"), aiResponse.get("participation_id"));

        if ("signup".equals(action)) {
            Object activityIdObj = aiResponse.get("activity_id");
            if (activityIdObj == null) {
                log.warn("signup action but activity_id is null");
                return new ChatResponse(reply);
            }
            Long activityId = ((Number) activityIdObj).longValue();
            log.info("Processing signup: userId={} activityId={}", userId, activityId);
            Activity activity = activityRepository.findById(activityId).orElse(null);
            if (activity == null) return new ChatResponse("未找到对应的活动，报名失败。");
            return handleSignup(userId, activity, user, aiResponse);
        }

        if ("withdraw".equals(action)) {
            Object participationIdObj = aiResponse.get("participation_id");
            if (participationIdObj == null) return new ChatResponse(reply);
            Long participationId = ((Number) participationIdObj).longValue();
            // 用 JOIN FETCH 避免 LazyInitializationException
            UserActivity ua = userActivityRepository.findByIdWithActivity(participationId).orElse(null);
            if (ua == null) return new ChatResponse("未找到报名记录，取消失败。");
            String activityName = ua.getActivity().getName(); // 在 session 内提前取出
            if (ua.getState() != ParticipationState.PENDING) {
                return new ChatResponse("该报名已不在待审核状态，无法取消。");
            }
            try {
                participationService.withdraw(participationId, userId);
                String resultReply = callResultReply("withdraw_success", activityName, user.getDisplayName());
                return new ChatResponse(resultReply);
            } catch (Exception e) {
                log.error("取消报名异常: participationId={}", participationId, e);
                return new ChatResponse(callResultReply("withdraw_failure", activityName, user.getDisplayName()));
            }
        }

        return new ChatResponse(reply);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> callAiService(String path, Map<String, Object> body) {
        HttpHeaders headers = buildHeaders();
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(body, headers);
        try {
            Map<String, Object> resp = restTemplate.postForObject(
                    aiServiceBaseUrl + path, entity, Map.class);
            if (resp != null && resp.get("data") instanceof Map) {
                return (Map<String, Object>) resp.get("data");
            }
            return Map.of("reply", "AI 服务返回格式异常。");
        } catch (Exception e) {
            log.error("AI 服务调用失败 [{}]: {}", path, e.getMessage());
            return Map.of("reply", "AI 服务暂时不可用，请稍后重试。");
        }
    }

    private String callResultReply(String scenario, String activityName, String userName) {
        Map<String, Object> body = new HashMap<>();
        body.put("scenario", scenario);
        body.put("activityName", activityName);
        body.put("userName", userName);
        Map<String, Object> result = callAiService("/chat/result-reply", body);
        if (result.get("reply") instanceof String r) return r;
        // 兜底文案
        return switch (scenario) {
            case "signup_success" -> "报名成功！";
            case "signup_duplicate" -> "你已报名过该活动，无需重复操作。";
            case "withdraw_success" -> "已成功取消报名。";
            default -> "操作完成。";
        };
    }

    private HttpHeaders buildHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (aiServiceApiToken != null && !aiServiceApiToken.isBlank()) {
            headers.set("X-Api-Key", aiServiceApiToken);
        }
        return headers;
    }

    private String serialize(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            return null;
        }
    }
}
