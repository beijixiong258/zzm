package zzm.controller;

import zzm.dto.Requests;
import zzm.entity.TeachingSession;
import zzm.service.*;
import cn.hutool.json.JSONUtil;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class AiController {
    private final AiService ai;
    private final AccountService accounts;
    private final CourseService courses;
    private final MaterialService materials;
    private final ContextBudget budget;
    @GetMapping("/ai/status") public Object status(HttpServletRequest request) {
        accounts.requireStaff(accounts.current(request)); return ai.status();
    }
    @PostMapping("/ai/connection") public Object connection(@RequestParam(defaultValue="false") boolean vision, HttpServletRequest request) {
        accounts.requireStaff(accounts.current(request)); return ai.connection(vision);
    }
    @PostMapping("/courses/{id}/context-budget") public Object context(@PathVariable String id, @Valid @RequestBody Requests.SessionInput input, HttpServletRequest request) {
        var course = courses.requireAccess(id, accounts.current(request), true);
        var selected = materials.selected(id, input.getMaterialIds());
        TeachingSession session = new TeachingSession();
        session.setTitle(input.getTitle()); session.setDescription(input.getDescription()); session.setSessionType(input.getSessionType());
        session.setTopic(input.getTopic()); session.setLearningGoals(input.getLearningGoals()); session.setTeachingLanguage(input.getTeachingLanguage());
        session.setAdditionalInstructions(input.getAdditionalInstructions()); session.setContentJson(JSONUtil.toJsonStr(input.getContent()));
        var generation = ai.generationMessages(session, course, selected, List.of());
        Map<String,Object> result = ai.generationBudget(generation, selected);
        if (!Objects.toString(input.getContent().getHandout(), "").isBlank()) {
            var revision = ai.revisionMessages(session, course, selected, input.getAdditionalInstructions());
            result.put("revisionBudget", ai.generationBudget(revision, selected));
        }
        result.put("pendingMaterials", selected.stream().filter(m -> Set.of("queued", "processing").contains(m.getStatus())).map(m -> m.getId()).toList());
        result.put("incompleteMaterials", selected.stream().filter(m -> !Set.of("queued", "processing").contains(m.getStatus())
            && (Set.of("incomplete", "failed").contains(m.getStatus()) || ai.needsPdfReprocessing(m))).map(m -> m.getId()).toList());
        boolean complete = ((List<?>) result.get("pendingMaterials")).isEmpty() && ((List<?>) result.get("incompleteMaterials")).isEmpty();
        if (!complete) {
            result.put("allowed", false);
            if (result.get("revisionBudget") instanceof Map<?, ?> revision) {
                @SuppressWarnings("unchecked") Map<String, Object> revisionBudget = (Map<String, Object>) revision;
                revisionBudget.put("allowed", false);
            }
        }
        result.put("materials", selected.stream().map(m -> {
            String text = Objects.toString(ai.materialInputs(List.of(m)).get(0).get("text"), "");
            return Map.of("id", m.getId(), "title", m.getTitle(), "textEstimate", budget.estimate(text),
                "textUpperBound", budget.upperBound(text), "imageEstimate", ai.imageTokens(List.of(m)));
        }).toList());
        return result;
    }
}
