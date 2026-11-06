package zzm.integration;

import zzm.config.AppProperties;
import zzm.dto.RetrievalContent;
import zzm.dto.RetrievalContent.*;
import cn.hutool.json.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.regex.Pattern;

/** Java 直接管理 QMD 官方进程和索引；课程权限仍由业务服务逐次确认。 */
@Slf4j
@Component
public class QmdClient {
    private static final Pattern COLLECTION_NAME = Pattern.compile("^([A-Za-z0-9_-]{1,150})_([a-f0-9]{64})$");
    private static final Pattern RESULT_FILE = Pattern.compile("^qmd://([^/]+)/([A-Za-z0-9_-]+)\\.md$");
    private final AppProperties properties;
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    private final Map<String, DocumentIndex> documents = new ConcurrentHashMap<>();
    private final Object metadataLock = new Object();
    private final ReentrantReadWriteLock indexLock = new ReentrantReadWriteLock();
    private final Semaphore searchSlots = new Semaphore(2);
    private volatile boolean documentsLoaded;
    private volatile boolean stopped;
    private volatile Process qmdServer;
    private volatile Process indexProcess;
    private long nextStartAt;

    public QmdClient(AppProperties properties) {
        this.properties = properties;
    }

    public record DocumentIndexStatus(String id, String revision, String indexedRevision, String status) {}

    /** 字段兼容原检索数据卷中的清单，升级后可继续处理未完成的索引任务。 */
    private record DocumentIndex(String id, String revision, String title, List<DocumentPart> parts,
                                 String indexedRevision, boolean deleted, long retryAt) {
        String collectionName() { return id + "_" + revision; }
        @JsonIgnore boolean isReady() { return !deleted && revision.equals(indexedRevision); }
        DocumentIndex markReady() { return new DocumentIndex(id, revision, title, parts, revision, false, 0); }
        DocumentIndex markDeleted() { return new DocumentIndex(id, revision, title, parts, indexedRevision, true, 0); }
        DocumentIndex retryLater() { return new DocumentIndex(id, revision, title, parts, indexedRevision, deleted, System.currentTimeMillis() + 30000); }
    }

    public List<DocumentIndexStatus> listDocumentIndexStatus() {
        loadDocuments();
        return documents.values().stream().sorted(Comparator.comparing(DocumentIndex::id))
            .map(document -> new DocumentIndexStatus(document.id(), document.revision(),
                Objects.toString(document.indexedRevision(), ""), document.deleted() ? "deleted" : document.isReady() ? "ready" : "pending"))
            .toList();
    }

    public void saveDocument(RetrievalDocument document) {
        requireEnabled();
        validateDocument(document);
        loadDocuments();
        synchronized (metadataLock) {
            DocumentIndex previous = documents.get(document.id());
            if (previous != null && !previous.deleted() && previous.revision().equals(document.revision())) return;
            DocumentIndex current = new DocumentIndex(document.id(), document.revision(), document.title(),
                List.copyOf(document.parts()), "", false, 0);
            saveDocumentMetadata(current);
            documents.put(current.id(), current);
        }
    }

    public void deleteDocument(String documentId) {
        requireEnabled();
        validateDocumentId(documentId);
        loadDocuments();
        synchronized (metadataLock) {
            DocumentIndex previous = documents.get(documentId);
            if (previous == null || previous.deleted()) return;
            DocumentIndex deleted = previous.markDeleted();
            saveDocumentMetadata(deleted);
            documents.put(documentId, deleted);
        }
    }

    public List<SearchResult> searchDocuments(List<SearchScope> scopes, String query, int limit) {
        if (scopes.isEmpty() || query == null || query.isBlank()) return List.of();
        requireEnabled();
        loadDocuments();
        if (!searchSlots.tryAcquire()) throw new IllegalStateException("QMD search is busy");
        var readLock = indexLock.readLock();
        if (!readLock.tryLock()) {
            searchSlots.release();
            throw new IllegalStateException("QMD index is updating");
        }
        try {
            Map<String, DocumentIndex> allowed = new LinkedHashMap<>();
            for (SearchScope scope : scopes) {
                DocumentIndex document = documents.get(scope.id());
                if (document != null && document.isReady() && document.revision().equals(scope.revision()))
                    allowed.put(document.collectionName(), document);
            }
            // 官方接口把空集合视为默认范围，因此空权限或未就绪时必须在 Java 侧直接返回。
            if (allowed.isEmpty()) return List.of();
            JSONObject response = queryDocuments(query, List.copyOf(allowed.keySet()), limit);
            JSONArray results = response.getJSONArray("results");
            if (results == null) throw new IllegalStateException("Invalid QMD response");
            List<SearchResult> matches = new ArrayList<>();
            for (Object value : results) {
                JSONObject result = JSONUtil.parseObj(value);
                var location = RESULT_FILE.matcher(result.getStr("file", ""));
                if (!location.matches()) continue;
                DocumentIndex document = allowed.get(location.group(1));
                if (document == null || documents.get(document.id()) != document) continue;
                DocumentPart part = document.parts().stream().filter(item -> item.id().equals(location.group(2))).findFirst().orElse(null);
                if (part == null) continue;
                matches.add(new SearchResult(document.id(), document.revision(), part.id(), part.page(),
                    part.text().substring(0, Math.min(350, part.text().length())), result.getDouble("score", 0d)));
            }
            return matches;
        } finally {
            readLock.unlock();
            searchSlots.release();
        }
    }

    private JSONObject queryDocuments(String query, List<String> collections, int limit) {
        try {
            String baseUrl = properties.getRetrieval().getBaseUrl().replaceAll("/+$", "");
            Map<String, Object> body = Map.of("searches", List.of(Map.of("type", "lex", "query", query),
                Map.of("type", "vec", "query", query)), "collections", collections,
                "limit", Math.max(1, Math.min(8, limit)), "candidateLimit", 12, "rerank", properties.getRetrieval().isRerank());
            var request = HttpRequest.newBuilder(URI.create(baseUrl + "/query"))
                .timeout(Duration.ofSeconds(Math.max(1, properties.getRetrieval().getTimeoutSeconds())))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(RetrievalContent.json(body))).build();
            var response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) throw new IllegalStateException("QMD HTTP " + response.statusCode());
            return JSONUtil.parseObj(response.body());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("QMD search interrupted", exception);
        } catch (IOException exception) {
            throw new IllegalStateException("QMD search unavailable", exception);
        }
    }

    /** 索引与检索互斥；后台任务失败时延期重试，不阻塞教师生成流程。 */
    public void processNextIndexTask() {
        if (stopped || !properties.getRetrieval().isEnabled()) return;
        var writeLock = indexLock.writeLock();
        if (!writeLock.tryLock()) return;
        try {
            loadDocuments();
            DocumentIndex document = documents.values().stream()
                .filter(item -> !item.isReady() && item.retryAt() <= System.currentTimeMillis())
                .sorted(Comparator.comparing(DocumentIndex::id)).findFirst().orElse(null);
            if (document == null) {
                startQmdServer();
                return;
            }
            stopProcess(qmdServer);
            qmdServer = null;
            nextStartAt = 0;
            try {
                if (!document.deleted()) writeDocumentParts(document);
                writeQmdConfiguration();
                if (!document.deleted()) {
                    updateIndex();
                    buildEmbeddings(document.collectionName());
                }
                removeObsoleteCollections(document);
                synchronized (metadataLock) {
                    if (documents.get(document.id()) != document) return;
                    if (document.deleted()) {
                        recycleIndexPath(manifestPath(document.id()));
                        documents.remove(document.id());
                    } else {
                        DocumentIndex ready = document.markReady();
                        saveDocumentMetadata(ready);
                        documents.put(ready.id(), ready);
                    }
                }
            } catch (IOException | RuntimeException exception) {
                synchronized (metadataLock) {
                    if (documents.get(document.id()) == document) {
                        DocumentIndex retry = document.retryLater();
                        saveDocumentMetadata(retry);
                        documents.put(retry.id(), retry);
                    }
                }
                log.warn("QMD 索引任务失败，稍后重试：document={}, cause={}", document.id(), exception.getClass().getSimpleName());
            } finally {
                startQmdServer();
            }
        } catch (IOException | RuntimeException exception) {
            nextStartAt = System.currentTimeMillis() + 30000;
            log.debug("QMD 后台处理延期：{}", exception.getClass().getSimpleName());
        } finally {
            writeLock.unlock();
        }
    }

    private void updateIndex() throws IOException {
        runQmdCommand("update");
    }

    private void buildEmbeddings(String collectionName) throws IOException {
        runQmdCommand("embed", "-c", collectionName, "--max-docs-per-batch", "16", "--max-batch-mb", "16");
    }

    private void startQmdServer() throws IOException {
        if (stopped || qmdServer != null && qmdServer.isAlive() || System.currentTimeMillis() < nextStartAt) return;
        URI address = URI.create(properties.getRetrieval().getBaseUrl());
        if (!Set.of("127.0.0.1", "localhost", "::1", "[::1]").contains(address.getHost()))
            throw new IllegalStateException("QMD must use a loopback address");
        writeQmdConfiguration();
        int port = address.getPort() < 0 ? 8181 : address.getPort();
        qmdServer = createQmdProcess("mcp", "--http", "--host", address.getHost(), "--port", Integer.toString(port)).start();
        qmdServer.getOutputStream().close();
        if (stopped) stopProcess(qmdServer);
        nextStartAt = System.currentTimeMillis() + 30000;
    }

    private void runQmdCommand(String... arguments) throws IOException {
        if (stopped) throw new IllegalStateException("QMD is stopping");
        Process process = createQmdProcess(arguments).start();
        indexProcess = process;
        try {
            process.getOutputStream().close();
            if (stopped) throw new IllegalStateException("QMD is stopping");
            if (!process.waitFor(Math.max(1, properties.getRetrieval().getIndexTimeoutSeconds()), TimeUnit.SECONDS))
                throw new IllegalStateException("QMD index command timed out");
            if (process.exitValue() != 0) throw new IllegalStateException("QMD index command failed: " + process.exitValue());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("QMD index command interrupted", exception);
        } finally {
            stopProcess(process);
            indexProcess = null;
        }
    }

    private ProcessBuilder createQmdProcess(String... arguments) {
        List<String> command = new ArrayList<>();
        command.add(properties.getRetrieval().getCommand());
        command.addAll(List.of(arguments));
        ProcessBuilder builder = new ProcessBuilder(command).directory(dataRoot().toFile())
            .redirectOutput(ProcessBuilder.Redirect.INHERIT).redirectError(ProcessBuilder.Redirect.INHERIT);
        Map<String, String> environment = builder.environment();
        environment.put("INDEX_PATH", dataRoot().resolve("index.sqlite").toString());
        environment.put("QMD_CONFIG_DIR", dataRoot().resolve("config").toString());
        environment.put("XDG_CACHE_HOME", dataRoot().resolve("cache").toString());
        environment.put("PWD", dataRoot().toString());
        return builder;
    }

    private void loadDocuments() {
        if (documentsLoaded) return;
        synchronized (metadataLock) {
            if (documentsLoaded) return;
            try {
                Files.createDirectories(dataRoot().resolve("manifests"));
                Files.createDirectories(dataRoot().resolve("documents"));
                Files.createDirectories(dataRoot().resolve("config"));
                try (var files = Files.list(dataRoot().resolve("manifests"))) {
                    for (Path file : files.filter(path -> path.getFileName().toString().endsWith(".json")).toList()) {
                        DocumentIndex document = json.readValue(file.toFile(), DocumentIndex.class);
                        validateDocument(new RetrievalDocument(document.id(), document.revision(), document.title(), document.parts()));
                        if (!file.getFileName().toString().equals(document.id() + ".json")) throw new IOException("Invalid QMD manifest name");
                        documents.put(document.id(), document);
                    }
                }
                documentsLoaded = true;
            } catch (IOException exception) {
                documents.clear();
                throw new IllegalStateException("QMD document metadata unavailable", exception);
            }
        }
    }

    private void writeDocumentParts(DocumentIndex document) throws IOException {
        Path directory = dataRoot().resolve("documents").resolve(document.collectionName());
        Files.createDirectories(directory);
        for (DocumentPart part : document.parts()) Files.writeString(directory.resolve(part.id() + ".md"), part.text());
    }

    private void writeQmdConfiguration() throws IOException {
        Map<String, Object> collections = new TreeMap<>();
        try (var directories = Files.list(dataRoot().resolve("documents"))) {
            for (Path directory : directories.filter(path -> Files.isDirectory(path) && !Files.isSymbolicLink(path)).toList()) {
                String name = directory.getFileName().toString();
                if (COLLECTION_NAME.matcher(name).matches())
                    collections.put(name, Map.of("path", directory.toString(), "pattern", "*.md"));
            }
        }
        // JSON 是 YAML 的子集，直接生成 QMD 官方配置，不另建配置协议。
        writeJsonAtomically(dataRoot().resolve("config/index.yml"), Map.of("collections", collections));
    }

    private void removeObsoleteCollections(DocumentIndex document) throws IOException {
        try (var directories = Files.list(dataRoot().resolve("documents"))) {
            for (Path directory : directories.filter(Files::isDirectory).toList()) {
                var name = COLLECTION_NAME.matcher(directory.getFileName().toString());
                if (!name.matches() || !name.group(1).equals(document.id())) continue;
                if (!document.deleted() && directory.getFileName().toString().equals(document.collectionName())) continue;
                runQmdCommand("collection", "remove", directory.getFileName().toString());
                recycleIndexPath(directory);
            }
        }
    }

    private void saveDocumentMetadata(DocumentIndex document) {
        try {
            writeJsonAtomically(manifestPath(document.id()), document);
        } catch (IOException exception) {
            throw new IllegalStateException("QMD document metadata could not be saved", exception);
        }
    }

    private void writeJsonAtomically(Path target, Object value) throws IOException {
        Path temporary = target.resolveSibling(target.getFileName() + "." + UUID.randomUUID() + ".tmp");
        Files.writeString(temporary, RetrievalContent.json(value));
        try {
            Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    /** 只移动检索自身生成的片段和清单；跨数据卷时逐文件移动，原始上传材料不经过此处。 */
    private void recycleIndexPath(Path source) throws IOException {
        if (!Files.exists(source)) return;
        Path destination = properties.recycleRoot().resolve("retrieval").resolve(UUID.randomUUID() + "-" + source.getFileName());
        Files.createDirectories(destination.getParent());
        if (!Files.isDirectory(source)) {
            Files.move(source, destination);
            return;
        }
        try (var paths = Files.walk(source)) {
            for (Path path : paths.toList()) {
                Path target = destination.resolve(source.relativize(path));
                if (Files.isDirectory(path)) Files.createDirectories(target);
                else Files.move(path, target);
            }
        }
        try (var paths = Files.walk(source)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);
        }
    }

    private Path dataRoot() {
        return Path.of(properties.getRetrieval().getDataDir()).toAbsolutePath().normalize();
    }

    private Path manifestPath(String id) {
        return dataRoot().resolve("manifests").resolve(id + ".json");
    }

    private void requireEnabled() {
        if (!properties.getRetrieval().isEnabled()) throw new IllegalStateException("QMD is disabled");
    }

    private void validateDocumentId(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]{1,150}")) throw new IllegalArgumentException("Invalid document identifier");
    }

    private void validateDocument(RetrievalDocument document) {
        validateDocumentId(document.id());
        if (document.revision() == null || !document.revision().matches("[a-f0-9]{64}") || document.title() == null
            || document.title().length() > 1000 || document.parts() == null || document.parts().size() > 3000)
            throw new IllegalArgumentException("Invalid document");
        Set<String> ids = new HashSet<>();
        for (DocumentPart part : document.parts()) {
            validateDocumentId(part.id());
            if (!ids.add(part.id()) || part.text() == null || part.text().length() > 12000 || part.page() < 0 || part.page() > 10000)
                throw new IllegalArgumentException("Invalid document part");
        }
    }

    private void stopProcess(Process process) {
        if (process == null) return;
        List<ProcessHandle> children = process.descendants().toList();
        children.forEach(ProcessHandle::destroy);
        process.destroy();
        try {
            if (!process.waitFor(5, TimeUnit.SECONDS)) process.destroyForcibly();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
        }
        children.stream().filter(ProcessHandle::isAlive).forEach(ProcessHandle::destroyForcibly);
    }

    @PreDestroy
    public void stopQmd() {
        stopped = true;
        stopProcess(indexProcess);
        stopProcess(qmdServer);
    }
}
