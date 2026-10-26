package zzm.controller;

import zzm.dto.Requests;
import zzm.service.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Map;
import static zzm.exception.ApiErrors.error;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class MaterialController {
    private final MaterialService materials;
    private final AccountService accounts;
    @GetMapping("/courses/{courseId}/materials") public Object list(@PathVariable String courseId, HttpServletRequest request) { return materials.library(courseId, accounts.current(request)); }
    @PostMapping("/courses/{courseId}/materials") public Object upload(@PathVariable String courseId, @RequestParam MultipartFile file,
        @RequestParam(defaultValue = "") String relativePath, @RequestParam(defaultValue = "student") String visibility, HttpServletRequest request) {
        return materials.view(materials.upload(courseId, file, relativePath, visibility, accounts.current(request)));
    }
    @GetMapping("/materials/{id}/text") public Object text(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) {
        return Map.of("text", materials.requireFile(id, versionId, accounts.current(request)).getTextContent());
    }
    @GetMapping("/materials/{id}/file") public ResponseEntity<Resource> file(@PathVariable String id, @RequestParam(required = false) String versionId, HttpServletRequest request) {
        var material = materials.requireFile(id, versionId, accounts.current(request)); Path path = Path.of(material.getStoragePath());
        if (!Files.isRegularFile(path)) throw error(404, "Original file is unavailable");
        boolean inline = material.getMimeType().startsWith("image/") || "application/pdf".equals(material.getMimeType());
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(material.getMimeType()))
            .header(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.builder(inline ? "inline" : "attachment").filename(material.getFileName(), StandardCharsets.UTF_8).build().toString())
            .header("X-Content-Type-Options", "nosniff").body(new FileSystemResource(path));
    }
    @PutMapping("/materials/{id}") public void edit(@PathVariable String id, @Valid @RequestBody Requests.MaterialInput input, HttpServletRequest request) { materials.edit(id, input, accounts.current(request)); }
    @PostMapping("/materials/{id}/archive") public void archive(@PathVariable String id, @RequestParam boolean archived, HttpServletRequest request) { materials.archive(id, archived, accounts.current(request)); }
    @DeleteMapping("/materials/{id}") public void remove(@PathVariable String id, HttpServletRequest request) { materials.removeMaterial(id, accounts.current(request)); }
    @PostMapping("/materials/{id}/retry") public void retry(@PathVariable String id, HttpServletRequest request) { materials.retry(id, accounts.current(request)); }
}
