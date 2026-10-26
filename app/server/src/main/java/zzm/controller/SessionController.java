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
public class SessionController {
    private final SessionService sessions;
    private final AccountService accounts;
    private final CourseService courses;
    @PostMapping("/workbench") public Object workbench(HttpServletRequest request) { var user = accounts.current(request); return courses.view(courses.workbench(user), user); }
    @PostMapping("/sessions/{id}/copy") public Object copy(@PathVariable String id, @RequestParam String courseId, HttpServletRequest request) { return sessions.view(sessions.copy(id, courseId, accounts.current(request)), true); }
    @GetMapping("/courses/{id}/sessions") public Object list(@PathVariable String id, HttpServletRequest request) { return sessions.listCourse(id, accounts.current(request)); }
    @PostMapping("/courses/{id}/sessions") public Object create(@PathVariable String id, @Valid @RequestBody Requests.SessionInput input, HttpServletRequest request) {
        return sessions.view(sessions.create(id, input, accounts.current(request)), true);
    }
    @GetMapping("/sessions/{id}") public Object detail(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) {
        var user = accounts.current(request); return "student".equals(user.getRole()) ? sessions.published(id, versionId, user) : sessions.view(sessions.require(id, user, true), true);
    }
    @PutMapping("/sessions/{id}") public Object edit(@PathVariable String id, @Valid @RequestBody Requests.SessionInput input, HttpServletRequest request) { return sessions.view(sessions.edit(id, input, accounts.current(request)), true); }
    @GetMapping("/sessions/{id}/preview") public Object preview(@PathVariable String id, HttpServletRequest request) { return sessions.view(sessions.require(id, accounts.current(request), true), false); }
    @PostMapping("/sessions/{id}/publish") public Object publish(@PathVariable String id, @Valid @RequestBody Requests.Revision input, HttpServletRequest request) {
        var version = sessions.publish(id, input.getRevision(), accounts.current(request)); return java.util.Map.of("versionId", version.getId(), "revision", version.getRevision());
    }
    @GetMapping("/sessions/{id}/versions") public Object versions(@PathVariable String id, HttpServletRequest request) { return sessions.versions(id, accounts.current(request)); }
    @PostMapping("/sessions/{id}/versions/{versionId}/restore") public void restore(@PathVariable String id, @PathVariable String versionId, @Valid @RequestBody Requests.Revision input, HttpServletRequest request) { sessions.restore(id, versionId, input.getRevision(), accounts.current(request)); }
    @PostMapping("/sessions/{id}/archive") public void archive(@PathVariable String id, @RequestParam boolean archived, HttpServletRequest request) { sessions.archive(id, archived, accounts.current(request)); }
}
