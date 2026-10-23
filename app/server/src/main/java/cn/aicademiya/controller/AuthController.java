package cn.aicademiya.controller;

import cn.aicademiya.dto.Requests;
import cn.aicademiya.service.AccountService;
import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class AuthController {
    private final AccountService accounts;
    @GetMapping("/health") public Object health() { return Map.of("status", "ok"); }
    @GetMapping("/bootstrap") public Object bootstrap() {
        return accounts.bootstrap();
    }
    @PostMapping("/auth/setup") public Object setup(@Valid @RequestBody Requests.Account input) { return accounts.publicUser(accounts.setup(input)); }
    @PostMapping("/auth/login") public Object login(@Valid @RequestBody Requests.Login input, HttpServletResponse response) { return accounts.publicUser(accounts.login(input, response)); }
    @PostMapping("/auth/student-login") public Object studentLogin(@Valid @RequestBody Requests.StudentLogin input, HttpServletResponse response) { return accounts.publicUser(accounts.studentLogin(input, response)); }
    @PostMapping("/auth/demo/{id}") public Object demo(@PathVariable String id, HttpServletResponse response) { return accounts.publicUser(accounts.demo(id, response)); }
    @GetMapping("/auth/me") public Object me(HttpServletRequest request) { return accounts.publicUser(accounts.current(request)); }
    @PostMapping("/auth/logout") public void logout(HttpServletRequest request, HttpServletResponse response) { accounts.logout(request, response); }
    @PostMapping("/auth/password") public void password(@Valid @RequestBody Requests.Password input, HttpServletRequest request, HttpServletResponse response) {
        accounts.changePassword(accounts.current(request), input, response);
    }
    @GetMapping("/accounts") public Object list(HttpServletRequest request) {
        return accounts.listAccounts(accounts.current(request));
    }
    @PostMapping("/accounts") public Object create(@Valid @RequestBody Requests.Account input, HttpServletRequest request) {
        return accounts.createAccount(input, accounts.current(request));
    }
}
