package cn.aicademiya.exception;

import org.springframework.http.HttpStatusCode;
import org.springframework.web.server.ResponseStatusException;

public final class ApiErrors {
    private ApiErrors() {}

    public static ResponseStatusException error(int status, String message) {
        return new ResponseStatusException(HttpStatusCode.valueOf(status), message);
    }
}
