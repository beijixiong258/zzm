package zzm.controller;

import zzm.dto.Requests;
import zzm.service.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class LearningController {
    private final LearningService learning;
    private final AccountService accounts;
    @GetMapping("/records/{id}/export") public org.springframework.http.ResponseEntity<byte[]> export(
        @PathVariable String id, @RequestParam(defaultValue="md") String format, HttpServletRequest request) {
        var user = accounts.current(request);
        if (!"student".equals(user.getRole())) throw zzm.exception.ApiErrors.error(403, "Only students can export their own learning results");
        if (!"md".equals(format)) throw zzm.exception.ApiErrors.error(422, "Unsupported export format");
        String base = org.springframework.web.servlet.support.ServletUriComponentsBuilder.fromCurrentContextPath()
            .path("/api/materials/").build().toUriString();
        byte[] content = learning.exportResult(id, user, base);
        return org.springframework.http.ResponseEntity.ok()
            .contentType(org.springframework.http.MediaType.parseMediaType("text/markdown;charset=UTF-8"))
            .header("Content-Disposition", org.springframework.http.ContentDisposition.attachment()
                .filename("learning-result-" + id + ".md").build().toString())
            .header("Cache-Control", "private, no-store").body(content);
    }
    @GetMapping("/sessions/{id}/workspace") public Object workspace(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) { return learning.workspace(id, versionId, accounts.current(request)); }
    @PostMapping("/sessions/{id}/start") public Object start(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) { return learning.view(learning.start(id, versionId, accounts.current(request))); }
    @PutMapping("/records/{id}/answers") public Object answers(@PathVariable String id, @Valid @RequestBody Requests.Answer input, HttpServletRequest request) { return learning.saveAnswers(id, input, accounts.current(request)); }
    @PostMapping("/records/{id}/conversation/reset") public Object reset(@PathVariable String id, @Valid @RequestBody Requests.Revision input, HttpServletRequest request) { return learning.resetConversation(id,input.getRevision(),accounts.current(request)); }
    @PostMapping("/records/{id}/context-budget") public Object context(@PathVariable String id, @Valid @RequestBody Requests.Chat input, HttpServletRequest request) { return learning.context(id, input, accounts.current(request)); }
    @PostMapping("/records/{id}/chat") public Object chat(@PathVariable String id, @Valid @RequestBody Requests.Chat input, HttpServletRequest request) { return learning.chat(id, input, accounts.current(request)); }
    @PostMapping("/records/{id}/submit") public Object submit(@PathVariable String id, @Valid @RequestBody Requests.Revision input, HttpServletRequest request) { return learning.submit(id, input.getRevision(), accounts.current(request)); }
    @GetMapping("/sessions/{id}/students") public Object roster(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) { return learning.roster(id, versionId, accounts.current(request)); }
    @GetMapping("/records/{id}/observe") public Object observe(@PathVariable String id, HttpServletRequest request) { return learning.observe(id, accounts.current(request)); }
    @PostMapping("/records/{id}/review") public Object review(@PathVariable String id, @Valid @RequestBody Requests.Review input, HttpServletRequest request) { return learning.review(id, input, accounts.current(request)); }
    @GetMapping("/sessions/{id}/preview/workspace") public Object previewWorkspace(@PathVariable String id, HttpServletRequest request) { return learning.previewWorkspace(id, accounts.current(request)); }
    @PostMapping("/sessions/{id}/preview/start") public Object previewStart(@PathVariable String id, HttpServletRequest request) { return learning.view(learning.startPreview(id, accounts.current(request))); }
    @GetMapping("/records/{id}/attachments") public Object attachments(@PathVariable String id, HttpServletRequest request) { return learning.attachments(id, accounts.current(request)); }
    @PostMapping("/records/{id}/attachments") public Object attachment(@PathVariable String id, @RequestParam org.springframework.web.multipart.MultipartFile file, @RequestParam(defaultValue="") String questionId, HttpServletRequest request) { return learning.uploadAttachment(id, questionId, file, accounts.current(request)); }
    @DeleteMapping("/records/{id}/attachments/{attachmentId}") public Object removeAttachment(@PathVariable String id, @PathVariable String attachmentId, @RequestParam long revision, HttpServletRequest request) { return learning.removeAttachment(id, attachmentId, revision, accounts.current(request)); }
    @PostMapping("/records/{id}/feedback/{requestId}/approve") public Object approve(@PathVariable String id, @PathVariable String requestId, @RequestBody java.util.Map<String,String> input, HttpServletRequest request) { return learning.approveFeedback(id, requestId, input.get("text"), accounts.current(request)); }
    @GetMapping("/records/{id}/history") public Object recordHistory(@PathVariable String id, @RequestParam String kind,
        @RequestParam(defaultValue="1") int page, @RequestParam(defaultValue="20") int size,
        @RequestParam(required=false) Long revision, HttpServletRequest request) {
        return learning.recordHistory(id, kind, page, size, revision, accounts.current(request));
    }
    @GetMapping("/records/{id}/history/{historyId}/messages") public Object historyMessages(@PathVariable String id, @PathVariable String historyId,
        @RequestParam(defaultValue="1") int page, @RequestParam(defaultValue="50") int size,
        @RequestParam(required=false) Long revision, HttpServletRequest request) {
        return learning.historyMessages(id, historyId, page, size, revision, accounts.current(request));
    }
    @GetMapping("/history") public Object history(HttpServletRequest request) { return learning.history(accounts.current(request)); }
}
