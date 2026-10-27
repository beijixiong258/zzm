package zzm.service.impl;

import cn.hutool.core.util.IdUtil;
import zzm.config.AppProperties;
import zzm.dto.Requests;
import zzm.entity.*;
import zzm.mapper.*;
import zzm.service.AccountService;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;
import jakarta.servlet.http.*;
import lombok.RequiredArgsConstructor;
import org.bouncycastle.crypto.generators.SCrypt;
import org.springframework.http.*;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static zzm.exception.ApiErrors.error;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;

@Service
@RequiredArgsConstructor
public class AccountServiceImpl extends ServiceImpl<AccountUserMapper, AccountUser> implements AccountService {
    private static final String cookieName = "aicademiyaSession";
    private final AuthSessionMapper sessions;
    private final AppProperties properties;
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    @Override public Map<String, Object> bootstrap() {
        return Map.of("needsSetup", !lambdaQuery().eq(AccountUser::getRole, "admin").eq(AccountUser::getArchived, false).exists(), "defaultLocale", "zh-CN", "demoEnabled", properties.isDemoEnabled(),
            "demoAccounts", properties.isDemoEnabled()
                ? lambdaQuery().eq(AccountUser::getDemo, true).eq(AccountUser::getArchived, false).list().stream().map(this::publicUser).toList()
                : List.of());
    }

    @Override public List<Map<String, Object>> listAccounts(AccountUser operator) {
        requireAdmin(operator);
        return list().stream().map(this::publicUser).toList();
    }

    @Override @Transactional public Map<String, Object> createAccount(Requests.Account input, AccountUser operator) {
        requireAdmin(operator);
        return publicUser(create(input, input.getRole()));
    }


    @Override public AccountUser current(HttpServletRequest request) {
        String token = token(request);
        AuthSession session = token.isEmpty() ? null : sessions.selectById(digest(token));
        if (session == null || !session.getExpiresAt().isAfter(LocalDateTime.now(ZoneOffset.UTC))) throw error(401, "Sign in required");
        AccountUser user = getById(session.getUserId());
        if (user == null || Boolean.TRUE.equals(user.getArchived())) throw error(401, "Sign in required");
        return user;
    }
    @Override public void requireStaff(AccountUser user) {
        if (!Set.of("teacher", "admin").contains(user.getRole())) throw error(403, "Teacher access required");
        if (Boolean.TRUE.equals(user.getMustChangePassword())) throw error(403, "Password change required");
    }
    @Override public void requireAdmin(AccountUser user) {
        requireStaff(user);
        if (!"admin".equals(user.getRole())) throw error(403, "Administrator access required");
    }
    @Override public Map<String, Object> publicUser(AccountUser user) {
        return Map.of("id", user.getId(), "name", user.getName(), "email", Objects.toString(user.getEmail(), ""), "username", Objects.toString(user.getUsername(), ""), "invitationEnabled", Boolean.TRUE.equals(user.getInvitationEnabled()), "demo", Boolean.TRUE.equals(user.getDemo()), "role", user.getRole(),
            "mustChangePassword", Boolean.TRUE.equals(user.getMustChangePassword()), "archived", Boolean.TRUE.equals(user.getArchived()));
    }
    @Override @Transactional public AccountUser create(Requests.Account input, String role) {
        return createMany(List.of(input), role).get(0);
    }
    @Override @Transactional public List<AccountUser> createMany(List<Requests.Account> input, String role) {
        List<AccountUser> users = input.stream().map(value -> newAccount(value, role)).toList();
        saveBatch(users); return users;
    }
    private AccountUser newAccount(Requests.Account input, String role) {
        if (input.getPassword() == null || input.getPassword().length() < 8) throw error(422, "Password must contain at least 8 characters");
        AccountUser user = new AccountUser();
        user.setName(input.getName().trim()); user.setEmail(input.getEmail().trim().toLowerCase(Locale.ROOT));
        user.setPasswordHash(encoder.encode(input.getPassword())); user.setRole(role);
        user.setArchived(false); user.setDemo(false); user.setMustChangePassword(false);
        return user;
    }
    @Override @Transactional public AccountUser setup(Requests.Account input) {
        if (lambdaQuery().eq(AccountUser::getRole, "admin").eq(AccountUser::getArchived, false).exists()) throw error(409, "Initial setup is already complete");
        if (input.getPassword() == null || input.getPassword().length() < 8) throw error(422, "Password must contain at least 8 characters");
        AccountUser user = new AccountUser();
        user.setId("initialAdmin"); user.setName(input.getName().trim());
        user.setEmail(input.getEmail().trim().toLowerCase(Locale.ROOT)); user.setRole("admin");
        user.setPasswordHash(encoder.encode(input.getPassword())); user.setArchived(false);
        user.setDemo(false); user.setMustChangePassword(false); save(user); return user;
    }
    @Override public AccountUser login(Requests.Login input, HttpServletResponse response) {
        AccountUser user = lambdaQuery().eq(AccountUser::getEmail, input.getEmail().trim().toLowerCase(Locale.ROOT)).one();
        if (user == null || Boolean.TRUE.equals(user.getArchived()) || !matches(input.getPassword(), user.getPasswordHash())) throw error(401, "Email or password is incorrect");
        if (input.getRole() != null && !input.getRole().equals(user.getRole())) throw error(403, "This account does not match the selected role.");
        issue(user, response); return user;
    }
    @Override public AccountUser studentLogin(Requests.StudentLogin input, HttpServletResponse response) {
        AccountUser user = lambdaQuery().eq(AccountUser::getUsername, input.getUsername().trim().toLowerCase(Locale.ROOT)).one();
        if (user == null || !"student".equals(user.getRole()) || Boolean.TRUE.equals(user.getArchived())
            || !Boolean.TRUE.equals(user.getInvitationEnabled()) || !matches(input.getInvitationCode().trim(), user.getInvitationHash()))
            throw error(401, "Username or invitation code is incorrect");
        issue(user, response); return user;
    }
    @Override @Transactional public Map<String, Object> createInvitedStudent(Requests.StudentInvitation input) {
        String username = input.getUsername().trim().toLowerCase(Locale.ROOT);
        if (lambdaQuery().eq(AccountUser::getUsername, username).exists()) throw error(409, "This username is already in use");
        AccountUser user = new AccountUser(); user.setName(input.getName().trim()); user.setUsername(username);
        user.setRole("student"); user.setArchived(false); user.setDemo(false); user.setMustChangePassword(false);
        user.setInvitationEnabled(false); save(user); return invitation(user.getId(), true);
    }
    @Override public Map<String, Object> invitation(String userId, boolean enabled) {
        AccountUser user = getById(userId);
        if (user == null || !"student".equals(user.getRole()) || user.getUsername() == null) throw error(422, "This student does not have a username-based account");
        byte[] bytes = new byte[15]; new java.security.SecureRandom().nextBytes(bytes);
        String code = enabled ? Base64.getUrlEncoder().withoutPadding().encodeToString(bytes) : "";
        lambdaUpdate().eq(AccountUser::getId, userId).set(AccountUser::getInvitationEnabled, enabled)
            .set(AccountUser::getInvitationHash, enabled ? encoder.encode(code) : null).update();
        sessions.delete(Wrappers.<AuthSession>lambdaQuery().eq(AuthSession::getUserId, userId));
        user.setInvitationEnabled(enabled);
        Map<String, Object> result = new LinkedHashMap<>(publicUser(user)); result.put("invitationCode", code); return result;
    }
    @Override @Transactional public void ensureDemoAccounts() {
        if (!properties.isDemoEnabled()) return;
        for (String role : List.of("teacher", "student")) {
            String id = "teacher".equals(role) ? "demoTeacher" : "demoStudent";
            if (getById(id) != null) continue;
            AccountUser user = new AccountUser(); user.setId(id); user.setRole(role);
            user.setName("teacher".equals(role) ? "演示教师" : "演示学生");
            user.setDemo(true); user.setArchived(false); user.setMustChangePassword(false); user.setInvitationEnabled(false);
            save(user);
        }
    }
    @Override public AccountUser demo(String id, HttpServletResponse response) {
        if (!properties.isDemoEnabled()) throw error(404, "Demo sign-in is disabled");
        AccountUser user = getById(id);
        if (user == null || !Boolean.TRUE.equals(user.getDemo()) || Boolean.TRUE.equals(user.getArchived())) throw error(404, "Demo account unavailable");
        issue(user, response); return user;
    }
    @Override public void logout(HttpServletRequest request, HttpServletResponse response) {
        sessions.deleteById(digest(token(request))); cookie(response, "", 0);
    }
    @Override @Transactional public void changePassword(AccountUser user, Requests.Password input, HttpServletResponse response) {
        if (!matches(input.getCurrentPassword(), user.getPasswordHash())) throw error(422, "Current password is incorrect");
        lambdaUpdate().eq(AccountUser::getId, user.getId()).set(AccountUser::getPasswordHash, encoder.encode(input.getNewPassword()))
            .set(AccountUser::getMustChangePassword, false).update();
        sessions.delete(Wrappers.<AuthSession>lambdaQuery().eq(AuthSession::getUserId, user.getId()));
        issue(user, response);
    }
    private boolean matches(String password, String encoded) {
        if (encoded == null || encoded.isBlank()) return false;
        if (!encoded.startsWith("scrypt$")) return encoder.matches(password, encoded);
        try {
            String[] parts = encoded.split("\\$");
            byte[] actual = SCrypt.generate(password.getBytes(StandardCharsets.UTF_8), HexFormat.of().parseHex(parts[1]), 16384, 8, 1, 64);
            return MessageDigest.isEqual(actual, HexFormat.of().parseHex(parts[2]));
        } catch (IllegalArgumentException | IndexOutOfBoundsException exception) { return false; }
    }
    private void issue(AccountUser user, HttpServletResponse response) {
        String token = IdUtil.fastSimpleUUID() + IdUtil.fastSimpleUUID();
        AuthSession session = new AuthSession(); session.setId(digest(token)); session.setUserId(user.getId());
        session.setExpiresAt(LocalDateTime.now(ZoneOffset.UTC).plusDays(7)); sessions.insert(session); cookie(response, token, 604800);
    }
    private void cookie(HttpServletResponse response, String token, long seconds) {
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(cookieName, token).httpOnly(true).secure(properties.isCookieSecure())
            .sameSite("Lax").path("/api").maxAge(seconds).build().toString());
    }
    private String token(HttpServletRequest request) {
        if (request.getCookies() == null) return "";
        return Arrays.stream(request.getCookies()).filter(c -> cookieName.equals(c.getName())).map(Cookie::getValue).findFirst().orElse("");
    }
    private String digest(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }
}
