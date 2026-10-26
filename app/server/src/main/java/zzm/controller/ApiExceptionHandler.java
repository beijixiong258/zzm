package zzm.controller;

import cn.hutool.json.JSONException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import java.util.Map;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<?> status(ResponseStatusException exception) {
        return ResponseEntity.status(exception.getStatusCode()).body(Map.of("detail", exception.getReason() == null ? "Request failed" : exception.getReason()));
    }
    @ExceptionHandler({IllegalArgumentException.class, JSONException.class, MethodArgumentNotValidException.class, HttpMessageNotReadableException.class})
    public ResponseEntity<?> invalid(Exception exception) {
        String message = exception instanceof MethodArgumentNotValidException error
            ? error.getBindingResult().getFieldErrors().stream().map(e -> e.getField() + ": " + e.getDefaultMessage()).findFirst().orElse("Invalid request")
            : "Invalid request data";
        return ResponseEntity.badRequest().body(Map.of("detail", message));
    }
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<?> conflict() {
        return ResponseEntity.status(409).body(Map.of("detail", "The record already exists or has changed. Refresh and retry."));
    }
}
