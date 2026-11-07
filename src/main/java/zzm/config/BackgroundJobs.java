package zzm.config;

import zzm.service.GenerationService;
import zzm.service.MaterialService;
import zzm.service.AccountService;
import zzm.service.SessionService;
import zzm.service.LearningAssessmentService;
import zzm.integration.QmdClient;
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
    private final SessionService sessions;
    private final LearningAssessmentService assessments;
    private final QmdClient qmd;
    private volatile boolean acceptingJobs;

    @EventListener(ApplicationReadyEvent.class)
    public void recover() {
        accounts.ensureDemoAccounts();
        materials.recoverProcessing();
        generations.recoverProcessing();
        assessments.recoverProcessing();
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

    @Scheduled(fixedDelay = 1500, initialDelay = 3000)
    public void prepareRetrieval() { if (acceptingJobs) materials.processRetrieval(); }

    @Scheduled(fixedDelay = 30000, initialDelay = 5000)
    public void syncRetrieval() { if (acceptingJobs) materials.syncRetrieval(); }

    @Scheduled(fixedDelay = 1000, initialDelay = 5000)
    public void processRetrievalIndex() { if (acceptingJobs) qmd.processNextIndexTask(); }

    @Scheduled(fixedDelay = 30000, initialDelay = 5000)
    public void recycleAttachments() {
        if (acceptingJobs) materials.recycleRemovedAttachments();
    }

    @Scheduled(fixedDelay = 30000)
    public void expireTasks() {
        if (acceptingJobs) sessions.expireTasks();
    }

    @Scheduled(fixedDelay = 86400000, initialDelay = 60000)
    public void inspectStorage() {
        if (acceptingJobs) materials.reportStorageUsage();
    }

    @Scheduled(fixedDelay = 2000)
    public void processGenerations() {
        if (acceptingJobs) generations.processNext();
    }

    @Scheduled(fixedDelay = 2000, initialDelay = 1000)
    public void processAssessments() {
        if (acceptingJobs) assessments.processNext();
    }
}
