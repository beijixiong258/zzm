package cn.aicademiya.config;

import cn.aicademiya.service.GenerationService;
import cn.aicademiya.service.MaterialService;
import cn.aicademiya.service.AccountService;
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
    private final AccountService accounts;
    private volatile boolean acceptingJobs;

    @EventListener(ApplicationReadyEvent.class)
    public void recover() {
        accounts.ensureDemoAccounts();
        materials.recoverProcessing();
        generations.recoverProcessing();
        acceptingJobs = true;
    }

    @Scheduled(fixedDelay = 1500)
    public void processMaterials() {
        if (acceptingJobs) materials.processNext();
    }

    @Scheduled(fixedDelay = 1500, initialDelay = 500)
    public void processSecondMaterial() {
        if (acceptingJobs) materials.processNext();
    }

    @Scheduled(fixedDelay = 30000, initialDelay = 5000)
    public void recycleAttachments() {
        if (acceptingJobs) materials.recycleRemovedAttachments();
    }

    @Scheduled(fixedDelay = 86400000, initialDelay = 60000)
    public void inspectStorage() {
        if (acceptingJobs) materials.reportStorageUsage();
    }

    @Scheduled(fixedDelay = 2000)
    public void processGenerations() {
        if (acceptingJobs) generations.processNext();
    }
}
