package zzm.integration;

import zzm.config.AppProperties;
import zzm.dto.RetrievalContent.*;
import cn.hutool.json.*;
import org.springframework.stereotype.Component;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;

/** 只调用内部检索服务；业务权限和有效内容由调用方逐次确认。 */
@Component
public class QmdClient {
    private final AppProperties properties;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    public QmdClient(AppProperties properties) { this.properties = properties; }

    public JSONObject request(String method, String path, Object body) {
        if (!properties.getRetrieval().isEnabled()) throw new IllegalStateException("Retrieval is disabled");
        try {
            String base = properties.getRetrieval().getBaseUrl().replaceAll("/+$", "");
            var request = HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(Math.max(1, properties.getRetrieval().getTimeoutSeconds())))
                .header("Content-Type", "application/json")
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                    : HttpRequest.BodyPublishers.ofString(zzm.dto.RetrievalContent.json(body))).build();
            var response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) throw new IllegalStateException("Retrieval HTTP " + response.statusCode());
            return JSONUtil.parseObj(response.body());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt(); throw new IllegalStateException("Retrieval interrupted", exception);
        } catch (java.io.IOException exception) { throw new IllegalStateException("Retrieval unavailable", exception); }
    }
    public List<Hit> search(List<Scope> scopes, String query, int limit) {
        if (scopes.isEmpty() || query == null || query.isBlank()) return List.of();
        JSONObject result = request("POST", "/search", Map.of("scopes", scopes, "query", query,
            "limit", Math.max(1, Math.min(8, limit)), "rerank", properties.getRetrieval().isRerank()));
        return result.getJSONArray("hits").stream().map(JSONUtil::parseObj)
            .map(hit -> new Hit(hit.getStr("corpusId"), hit.getStr("revision"), hit.getStr("partId"),
                hit.getInt("page", 0), hit.getStr("snippet", ""), hit.getDouble("score", 0d))).toList();
    }
    public void put(Corpus corpus) { request("PUT", "/corpora/" + safe(corpus.id()), corpus); }
    public void remove(String id) { request("DELETE", "/corpora/" + safe(id), null); }
    private String safe(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]{1,150}")) throw new IllegalArgumentException("Invalid corpus identifier");
        return id;
    }
}
