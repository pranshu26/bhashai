import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  // Seed a few demo glossary terms (user-agnostic). Real users are created via /auth/signup.
  const terms = [
    { targetLanguage: 'hi', sourceTerm: 'Right to Information', targetTerm: 'सूचना का अधिकार' },
    { targetLanguage: 'hi', sourceTerm: 'Gram Panchayat', targetTerm: 'ग्राम पंचायत' },
    { targetLanguage: 'mr', sourceTerm: 'Gram Panchayat', targetTerm: 'ग्रामपंचायत' },
    { targetLanguage: 'bn', sourceTerm: 'Right to Information', targetTerm: 'তথ্যের অধিকার' },
  ];
  for (const t of terms) {
    const exists = await prisma.translationGlossaryTerm.findFirst({
      where: { userId: null, jobId: null, targetLanguage: t.targetLanguage, sourceTerm: t.sourceTerm },
    });
    if (!exists) await prisma.translationGlossaryTerm.create({ data: t });
  }
  const count = await prisma.translationGlossaryTerm.count();
  console.log(`Seed complete. Glossary terms in DB: ${count}`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
