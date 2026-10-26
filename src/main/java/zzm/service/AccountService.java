package zzm.service;

import com.baomidou.mybatisplus.spring.service.IService;
import zzm.dto.Requests;
import zzm.entity.AccountUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Map;

public interface AccountService extends IService<AccountUser> {
    void ensureDemoAccounts();
    Map<String, Object> bootstrap();
    java.util.List<Map<String, Object>> listAccounts(AccountUser operator);
    Map<String, Object> createAccount(Requests.Account input, AccountUser operator);
    AccountUser current(HttpServletRequest request);
    void requireStaff(AccountUser user);
    void requireAdmin(AccountUser user);
    Map<String, Object> publicUser(AccountUser user);
    AccountUser create(Requests.Account input, String role);
    java.util.List<AccountUser> createMany(java.util.List<Requests.Account> input, String role);
    AccountUser setup(Requests.Account input);
    AccountUser login(Requests.Login input, HttpServletResponse response);
    AccountUser studentLogin(Requests.StudentLogin input, HttpServletResponse response);
    Map<String, Object> createInvitedStudent(Requests.StudentInvitation input);
    Map<String, Object> invitation(String userId, boolean enabled);
    AccountUser demo(String id, HttpServletResponse response);
    void logout(HttpServletRequest request, HttpServletResponse response);
    void changePassword(AccountUser user, Requests.Password input, HttpServletResponse response);
}
