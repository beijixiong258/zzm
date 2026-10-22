package cn.aicademiya.controller;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.service.*;
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
    @GetMapping("/sessions/{id}/workspace") public Object workspace(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) { return learning.workspace(id, versionId, accounts.current(request)); }
    @PostMapping("/sessions/{id}/start") public Object start(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) { return learning.view(learning.start(id, versionId, accounts.current(request))); }
    @PutMapping("/records/{id}/answers") public Object answers(@PathVariable String id, @Valid @RequestBody Requests.Answer input, HttpServletRequest request) { return learning.saveAnswers(id, input, accounts.current(request)); }
    @PostMapping("/records/{id}/chat") public Object chat(@PathVariable String id, @Valid @RequestBody Requests.Chat input, HttpServletRequest request) { return learning.chat(id, input, accounts.current(request)); }
    @PostMapping("/records/{id}/submit") public Object submit(@PathVariable String id, @Valid @RequestBody Requests.Revision input, HttpServletRequest request) { return learning.submit(id, input.getRevision(), accounts.current(request)); }
    @GetMapping("/sessions/{id}/students") public Object roster(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) { return learning.roster(id, versionId, accounts.current(request)); }
    @GetMapping("/records/{id}/observe") public Object observe(@PathVariable String id, HttpServletRequest request) { return learning.observe(id, accounts.current(request)); }
    @PostMapping("/records/{id}/review") public Object review(@PathVariable String id, @Valid @RequestBody Requests.Review input, HttpServletRequest request) { return learning.review(id, input, accounts.current(request)); }
    @GetMapping("/history") public Object history(HttpServletRequest request) { return learning.history(accounts.current(request)); }
}
