package cn.aicademiya.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import java.util.List;

@Data
@Component
@ConfigurationProperties(prefix = "app")
public class AppProperties {
    private String configPath;
    private String uploadDir;
    private int documentMaxUnits = 300;
    private int documentMaxCharacters = 300000;
    private int documentImageMaxEdge = 2000;
    private List<String> allowedOrigins;
    private boolean cookieSecure;
    private boolean demoEnabled;
}
