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
public class CourseController {
    private final CourseService courses;
    private final AccountService accounts;
    @GetMapping("/courses") public Object mine(HttpServletRequest request) { return courses.mine(accounts.current(request)); }
    @PostMapping("/courses") public Object create(@Valid @RequestBody Requests.CourseInput input, HttpServletRequest request) {
        var user = accounts.current(request); return courses.view(courses.create(input, user), user);
    }
    @PutMapping("/courses/{id}") public Object edit(@PathVariable String id, @Valid @RequestBody Requests.CourseInput input, HttpServletRequest request) {
        var user = accounts.current(request); return courses.view(courses.edit(id, input, user), user);
    }
    @PostMapping("/courses/{id}/archive") public void archive(@PathVariable String id, @RequestParam boolean archived, HttpServletRequest request) { courses.archive(id, archived, accounts.current(request)); }
    @PostMapping("/courses/join") public void join(@RequestParam String code, HttpServletRequest request) { courses.join(code, accounts.current(request)); }
    @GetMapping("/courses/{id}/members") public Object members(@PathVariable String id, HttpServletRequest request) { return courses.members(id, accounts.current(request)); }
    @PostMapping("/courses/{id}/members") public void add(@PathVariable String id, @Valid @RequestBody Requests.Account input, HttpServletRequest request) { courses.addMember(id, input, accounts.current(request)); }
    @PostMapping("/courses/{id}/members/batch") public void addBatch(@PathVariable String id, @Valid @RequestBody Requests.AccountBatch input, HttpServletRequest request) { courses.addMembers(id, input.getMembers(), accounts.current(request)); }
    @PostMapping("/courses/{id}/members/{userId}/archive") public void archiveMember(@PathVariable String id, @PathVariable String userId, @RequestParam boolean archived, HttpServletRequest request) {
        courses.archiveMember(id, userId, archived, accounts.current(request));
    }
}
