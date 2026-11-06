package zzm.integration;

import zzm.config.AppProperties;
import zzm.dto.RetrievalContent;
import zzm.dto.RetrievalContent.*;
import cn.hutool.json.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class QmdClientTest {
    @TempDir Path dataRoot;
    private final String revision = "a".repeat(64);
    private final AtomicInteger requests = new AtomicInteger();
    private final AtomicReference<JSONObject> requestBody = new AtomicReference<>();
    private HttpServer server;
    private AppProperties properties;
    private QmdClient client;

    @BeforeEach void setup() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/query", exchange -> {
            requests.incrementAndGet();
            requestBody.set(JSONUtil.parseObj(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)));
            String allowed = "qmd://m-source_" + revision + "/s0.md";
            String forbidden = "qmd://m-another-student_" + revision + "/s0.md";
            byte[] response = RetrievalContent.json(Map.of("results", List.of(
                Map.of("file", allowed, "score", 0.8),
                Map.of("file", forbidden, "score", 1),
                Map.of("file", "qmd://m-source_" + revision + "/s99.md", "score", 0.9)
            ))).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            try (var output = exchange.getResponseBody()) { output.write(response); }
        });
        server.start();
        properties = new AppProperties();
        properties.getRetrieval().setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        properties.getRetrieval().setDataDir(dataRoot.toString());
        properties.setTrashDir(dataRoot.resolve("recycle").toString());
        Files.createDirectories(dataRoot.resolve("manifests"));
        // 沿用旧 Node.js 服务的清单字段，覆盖升级后的读取兼容性。
        Files.writeString(dataRoot.resolve("manifests/m-source.json"), RetrievalContent.json(Map.of(
            "id", "m-source", "revision", revision, "title", "Source", "indexedRevision", revision,
            "parts", List.of(new DocumentPart("s0", "Original source paragraph", 7, "native", true)), "retryAt", 0
        )));
        client = new QmdClient(properties);
    }

    @AfterEach void cleanup() {
        if (client != null) client.stopQmd();
        if (server != null) server.stop(0);
    }

    @Test void callsTheOfficialQueryContractAndRejectsUnexpectedDocumentsAndParts() {
        var matches = client.searchDocuments(List.of(new SearchScope("m-source", revision)), "source", 5);
        assertEquals(1, matches.size());
        assertEquals("m-source", matches.get(0).documentId());
        assertEquals(7, matches.get(0).page());
        assertEquals("Original source paragraph", matches.get(0).snippet());
        assertEquals(1, requestBody.get().getJSONArray("collections").size());
        assertEquals("m-source_" + revision, requestBody.get().getJSONArray("collections").getStr(0));
        var searches = requestBody.get().getJSONArray("searches");
        assertEquals("lex", searches.getJSONObject(0).getStr("type"));
        assertEquals("vec", searches.getJSONObject(1).getStr("type"));
        assertFalse(requestBody.get().containsKey("scopes"));
        assertEquals(5, requestBody.get().getInt("limit"));
        assertFalse(requestBody.get().getBool("rerank"));
    }

    @Test void emptyUnknownAndStaleScopesNeverReachTheOfficialDefaultSearchRange() {
        assertTrue(client.searchDocuments(List.of(), "source", 5).isEmpty());
        assertTrue(client.searchDocuments(List.of(new SearchScope("m-unknown", revision)), "source", 5).isEmpty());
        assertTrue(client.searchDocuments(List.of(new SearchScope("m-source", "b".repeat(64))), "source", 5).isEmpty());
        assertEquals(0, requests.get());
    }

    @Test void updatesAndDeletionImmediatelyRevokeSearchAndSurviveReload() {
        String changed = "b".repeat(64);
        client.saveDocument(new RetrievalDocument("m-source", changed, "Updated source",
            List.of(new DocumentPart("s0", "Updated paragraph", 8, "native", true))));
        assertTrue(client.searchDocuments(List.of(new SearchScope("m-source", revision)), "source", 5).isEmpty());
        assertTrue(client.searchDocuments(List.of(new SearchScope("m-source", changed)), "source", 5).isEmpty());

        var reloaded = new QmdClient(properties);
        assertEquals("pending", reloaded.listDocumentIndexStatus().get(0).status());
        assertEquals(changed, reloaded.listDocumentIndexStatus().get(0).revision());
        reloaded.deleteDocument("m-source");
        var deleted = new QmdClient(properties);
        assertEquals("deleted", deleted.listDocumentIndexStatus().get(0).status());
        assertTrue(deleted.searchDocuments(List.of(new SearchScope("m-source", changed)), "source", 5).isEmpty());
        assertEquals(0, requests.get());
    }
}
