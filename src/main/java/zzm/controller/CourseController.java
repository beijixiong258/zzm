package zzm.controller;

import zzm.dto.Requests;
import zzm.service.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
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
    @DeleteMapping("/courses/{id}") public void delete(@PathVariable String id, HttpServletRequest request) { courses.deleteCourse(id, accounts.current(request)); }
    @PostMapping("/courses/join") public void join(@RequestParam String code, HttpServletRequest request) { courses.join(code, accounts.current(request)); }
    @GetMapping("/courses/{id}/members") public Object members(@PathVariable String id, HttpServletRequest request) { return courses.members(id, accounts.current(request)); }
    @PostMapping("/courses/{id}/students") public void addStudent(@PathVariable String id, @Valid @RequestBody Requests.CourseStudent input, HttpServletRequest request) {
        courses.addStudent(id, input, accounts.current(request));
    }
    @DeleteMapping("/courses/{id}/students/{studentId}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void removeStudent(@PathVariable String id, @PathVariable String studentId, HttpServletRequest request) {
        courses.removeStudent(id, studentId, accounts.current(request));
    }
}
