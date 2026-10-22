package cn.aicademiya.config;

import cn.aicademiya.service.GenerationService;
import cn.aicademiya.service.MaterialService;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class BackgroundJobs {
    private final MaterialService materials;
    private final GenerationService generations;
    private volatile boolean acceptingJobs;

    @EventListener(ApplicationReadyEvent.class)
    public void recover() {
        materials.recoverProcessing();
        generations.recoverProcessing();
        acceptingJobs = true;
    }

    @Scheduled(fixedDelay = 1500)
    public void processMaterials() {
        if (acceptingJobs) materials.processNext();
    }

    @Scheduled(fixedDelay = 2000)
    public void processGenerations() {
        if (acceptingJobs) generations.processNext();
    }
}
