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
public class GenerationController {
    private final GenerationService generations;
    private final SessionService sessions;
    private final AccountService accounts;
    @PostMapping("/sessions/{id}/generations") public Object start(@PathVariable String id, @Valid @RequestBody Requests.Generation input, HttpServletRequest request) { return generations.view(generations.start(id, input, accounts.current(request))); }
    @GetMapping("/generations/{id}") public Object status(@PathVariable String id, HttpServletRequest request) { return generations.view(generations.require(id, accounts.current(request))); }
    @GetMapping("/sessions/{id}/generations") public Object jobs(@PathVariable String id, HttpServletRequest request) {
        return generations.listJobs(id, accounts.current(request));
    }
    @PostMapping("/generations/{id}/apply") public Object apply(@PathVariable String id, HttpServletRequest request) { return sessions.view(generations.apply(id, accounts.current(request)), true); }
    @PostMapping("/teacher/assistant") public Object assistant(@Valid @RequestBody Requests.Chat input, HttpServletRequest request) {
        return generations.assistTeacher(input, accounts.current(request));
    }
}
