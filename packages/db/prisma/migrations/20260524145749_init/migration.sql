-- CreateEnum
CREATE TYPE "UserRole" AS ENUM ('USER', 'ADMIN', 'REVIEWER');

-- CreateEnum
CREATE TYPE "JobStatus" AS ENUM ('PENDING', 'UPLOADED', 'EXTRACTING', 'ANALYZING', 'CHUNKING', 'TRANSLATING', 'POST_EDITING', 'QA', 'RECONSTRUCTING', 'EXPORTING', 'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED');

-- CreateEnum
CREATE TYPE "JobStage" AS ENUM ('CREATED', 'UPLOAD', 'EXTRACT', 'ANALYZE', 'CHUNK', 'TRANSLATE', 'POST_EDIT', 'QA', 'RECONSTRUCT', 'EXPORT', 'DONE');

-- CreateEnum
CREATE TYPE "ChunkStatus" AS ENUM ('PENDING', 'TRANSLATING', 'TRANSLATED', 'POST_EDITING', 'POST_EDITED', 'QA_PENDING', 'QA_PASSED', 'QA_FLAGGED', 'FAILED', 'APPROVED');

-- CreateEnum
CREATE TYPE "DocType" AS ENUM ('TXT', 'DOCX', 'PDF_TEXT', 'PDF_SCANNED', 'PDF_MIXED');

-- CreateEnum
CREATE TYPE "OutputMode" AS ENUM ('REFLOWED', 'LAYOUT_PRESERVED', 'BILINGUAL');

-- CreateEnum
CREATE TYPE "Tone" AS ENUM ('FORMAL', 'INFORMAL', 'EDUCATIONAL', 'CONVERSATIONAL', 'TECHNICAL', 'LITERARY', 'GOVERNMENT', 'ACADEMIC');

-- CreateEnum
CREATE TYPE "AssetType" AS ENUM ('IMAGE', 'GRAPH', 'DIAGRAM', 'TABLE', 'FOOTNOTE', 'CAPTION', 'EQUATION', 'HEADER', 'FOOTER', 'PAGE_NUMBER', 'CHART');

-- CreateEnum
CREATE TYPE "EngineKind" AS ENUM ('MOCK', 'INDICTRANS2', 'AMAZON_TRANSLATE', 'GOOGLE_ADVANCED', 'LLM', 'GLOSSARY_RULE', 'TRANSLATION_MEMORY');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "name" TEXT,
    "role" "UserRole" NOT NULL DEFAULT 'USER',
    "planId" TEXT NOT NULL DEFAULT 'free',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TranslationJob" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "sourceLanguage" TEXT NOT NULL DEFAULT 'en',
    "targetLanguage" TEXT NOT NULL,
    "tone" "Tone" NOT NULL DEFAULT 'FORMAL',
    "mode" TEXT NOT NULL DEFAULT 'DOCUMENT',
    "docType" "DocType",
    "outputMode" "OutputMode" NOT NULL DEFAULT 'REFLOWED',
    "qualityPriority" BOOLEAN NOT NULL DEFAULT true,
    "specialInstructions" TEXT,
    "status" "JobStatus" NOT NULL DEFAULT 'PENDING',
    "currentStage" "JobStage" NOT NULL DEFAULT 'CREATED',
    "progressPercentage" INTEGER NOT NULL DEFAULT 0,
    "totalChunks" INTEGER NOT NULL DEFAULT 0,
    "completedChunks" INTEGER NOT NULL DEFAULT 0,
    "failedChunks" INTEGER NOT NULL DEFAULT 0,
    "originalFileUrl" TEXT,
    "originalFileName" TEXT,
    "extractedTextUrl" TEXT,
    "translatedFileUrl" TEXT,
    "guideJson" JSONB,
    "estimatedCostMicroUsd" INTEGER,
    "actualCostMicroUsd" INTEGER NOT NULL DEFAULT 0,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "completedAt" TIMESTAMP(3),

    CONSTRAINT "TranslationJob_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TranslationChunk" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "chapterIndex" INTEGER NOT NULL DEFAULT 0,
    "sectionTitle" TEXT,
    "chunkIndex" INTEGER NOT NULL,
    "sourceText" TEXT NOT NULL,
    "translatedText" TEXT,
    "rawTranslatedText" TEXT,
    "status" "ChunkStatus" NOT NULL DEFAULT 'PENDING',
    "retryCount" INTEGER NOT NULL DEFAULT 0,
    "engineUsed" "EngineKind",
    "qaScore" INTEGER,
    "qaFlags" JSONB,
    "tokenCount" INTEGER,
    "prevContext" TEXT,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TranslationChunk_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TranslationGlossaryTerm" (
    "id" TEXT NOT NULL,
    "userId" TEXT,
    "jobId" TEXT,
    "targetLanguage" TEXT NOT NULL,
    "sourceTerm" TEXT NOT NULL,
    "targetTerm" TEXT NOT NULL,
    "doNotTranslate" BOOLEAN NOT NULL DEFAULT false,
    "caseSensitive" BOOLEAN NOT NULL DEFAULT false,
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TranslationGlossaryTerm_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TranslationReferenceDocument" (
    "id" TEXT NOT NULL,
    "userId" TEXT,
    "jobId" TEXT,
    "targetLanguage" TEXT NOT NULL,
    "title" TEXT,
    "fileUrl" TEXT NOT NULL,
    "styleGuideJson" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TranslationReferenceDocument_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TranslationMemoryEntry" (
    "id" TEXT NOT NULL,
    "userId" TEXT,
    "targetLanguage" TEXT NOT NULL,
    "domain" TEXT,
    "sourceText" TEXT NOT NULL,
    "targetText" TEXT NOT NULL,
    "sourceHash" TEXT NOT NULL,
    "quality" INTEGER NOT NULL DEFAULT 0,
    "approvedByHuman" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TranslationMemoryEntry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DocumentAsset" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "assetType" "AssetType" NOT NULL,
    "originalPageNumber" INTEGER,
    "originalBoundingBox" JSONB,
    "fileUrl" TEXT,
    "captionSourceText" TEXT,
    "captionTranslatedText" TEXT,
    "referenceId" TEXT,
    "ocrConfidence" DOUBLE PRECISION,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DocumentAsset_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "QAReport" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "overallScore" INTEGER NOT NULL,
    "pass" BOOLEAN NOT NULL,
    "chunksTranslated" INTEGER NOT NULL,
    "chunksFlagged" INTEGER NOT NULL,
    "glossaryViolations" INTEGER NOT NULL DEFAULT 0,
    "numberMismatches" INTEGER NOT NULL DEFAULT 0,
    "untranslatedWarnings" INTEGER NOT NULL DEFAULT 0,
    "layoutWarnings" INTEGER NOT NULL DEFAULT 0,
    "ocrWarnings" INTEGER NOT NULL DEFAULT 0,
    "imageTextWarnings" INTEGER NOT NULL DEFAULT 0,
    "reportJson" JSONB NOT NULL,
    "recommendedReview" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "QAReport_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TranslationEngineRun" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "chunkId" TEXT,
    "engine" "EngineKind" NOT NULL,
    "promptVersion" TEXT,
    "inputText" TEXT,
    "rawOutput" TEXT,
    "postEditedOutput" TEXT,
    "latencyMs" INTEGER,
    "costMicroUsd" INTEGER,
    "qaFlags" JSONB,
    "success" BOOLEAN NOT NULL DEFAULT true,
    "errorMessage" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TranslationEngineRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ExportedFile" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "outputMode" "OutputMode" NOT NULL,
    "format" TEXT NOT NULL,
    "fileUrl" TEXT NOT NULL,
    "sizeBytes" INTEGER,
    "isPartial" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExportedFile_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "JobEventLog" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "stage" "JobStage" NOT NULL,
    "event" TEXT NOT NULL,
    "level" TEXT NOT NULL DEFAULT 'info',
    "message" TEXT,
    "dataJson" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "JobEventLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE INDEX "TranslationJob_userId_status_idx" ON "TranslationJob"("userId", "status");

-- CreateIndex
CREATE INDEX "TranslationChunk_jobId_status_idx" ON "TranslationChunk"("jobId", "status");

-- CreateIndex
CREATE UNIQUE INDEX "TranslationChunk_jobId_chunkIndex_key" ON "TranslationChunk"("jobId", "chunkIndex");

-- CreateIndex
CREATE INDEX "TranslationGlossaryTerm_userId_targetLanguage_idx" ON "TranslationGlossaryTerm"("userId", "targetLanguage");

-- CreateIndex
CREATE INDEX "TranslationGlossaryTerm_jobId_idx" ON "TranslationGlossaryTerm"("jobId");

-- CreateIndex
CREATE INDEX "TranslationMemoryEntry_targetLanguage_domain_idx" ON "TranslationMemoryEntry"("targetLanguage", "domain");

-- CreateIndex
CREATE UNIQUE INDEX "TranslationMemoryEntry_sourceHash_targetLanguage_key" ON "TranslationMemoryEntry"("sourceHash", "targetLanguage");

-- CreateIndex
CREATE INDEX "DocumentAsset_jobId_assetType_idx" ON "DocumentAsset"("jobId", "assetType");

-- CreateIndex
CREATE UNIQUE INDEX "QAReport_jobId_key" ON "QAReport"("jobId");

-- CreateIndex
CREATE INDEX "TranslationEngineRun_jobId_engine_idx" ON "TranslationEngineRun"("jobId", "engine");

-- CreateIndex
CREATE INDEX "TranslationEngineRun_chunkId_idx" ON "TranslationEngineRun"("chunkId");

-- CreateIndex
CREATE INDEX "JobEventLog_jobId_createdAt_idx" ON "JobEventLog"("jobId", "createdAt");

-- AddForeignKey
ALTER TABLE "TranslationJob" ADD CONSTRAINT "TranslationJob_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationChunk" ADD CONSTRAINT "TranslationChunk_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationGlossaryTerm" ADD CONSTRAINT "TranslationGlossaryTerm_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationGlossaryTerm" ADD CONSTRAINT "TranslationGlossaryTerm_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationReferenceDocument" ADD CONSTRAINT "TranslationReferenceDocument_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationReferenceDocument" ADD CONSTRAINT "TranslationReferenceDocument_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DocumentAsset" ADD CONSTRAINT "DocumentAsset_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "QAReport" ADD CONSTRAINT "QAReport_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationEngineRun" ADD CONSTRAINT "TranslationEngineRun_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TranslationEngineRun" ADD CONSTRAINT "TranslationEngineRun_chunkId_fkey" FOREIGN KEY ("chunkId") REFERENCES "TranslationChunk"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExportedFile" ADD CONSTRAINT "ExportedFile_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobEventLog" ADD CONSTRAINT "JobEventLog_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "TranslationJob"("id") ON DELETE CASCADE ON UPDATE CASCADE;
