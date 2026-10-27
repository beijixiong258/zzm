FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml ./
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl fontconfig fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true"
WORKDIR /app
COPY --from=build /build/target/aicademiya-server-0.1.0.jar ./app.jar
RUN useradd --create-home --uid 10001 aicademiya && mkdir -p /data/uploads && chown -R aicademiya:aicademiya /data /app
USER aicademiya
EXPOSE 8001
CMD ["java", "-jar", "app.jar"]
