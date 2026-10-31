# School Textbooks RAG v2

منصة RAG للكتب المدرسية (ابتدائي / إعدادي / ثانوي) بثلاث لغات (عربي / English / Français)، فيها VLM لقراءة أي نص، وشات منفصل لكل طالب، وأي موديل أو vendor تقدري تبدّليه من `.env`.

## هيكل الكود (Layers)

```
Router  ─►  Controller  ─►  Service  ─►  Repository  ─►  Model (DB)
 HTTP        شكل الـ I/O      business       SQL فقط         جداول
 فقط         + SSE           logic
                               │
                               └──►  Providers (interfaces)  ─►  Anthropic / OpenAI / BGE / Qdrant / Tesseract
```

```
app/
├─ main.py            create_app + lifespan (بيعمل validate للـ providers وقت التشغيل)
├─ cli.py             init-db | create-admin | providers
├─ core/              config, db, security, errors, constants, textutil, container (composition root)
├─ models/            User, Book, BookPage, ChatSession, Message, UsageDaily
├─ schemas/           Pydantic: request/response
├─ repositories/      كل الـ SQL (كل query للشات متفلتر بـ user_id)
├─ services/          auth, student, book, chat, rag, quota, ingestion, extraction, chunking, retrieval, prompts
├─ controllers/       auth, book, student, chat, health
├─ routers/           auth, books, students, chat, health  (+ deps.py: التوصيل بين الطبقات)
├─ providers/         base.py (الـ interfaces) + factory.py (registry) + التنفيذات:
│   ├─ llm/           anthropic_llm, openai_llm
│   ├─ vlm/           anthropic_vlm, openai_vlm
│   ├─ embeddings/    bge_m3 (local, hybrid), openai_embeddings
│   ├─ rerankers/     bge_reranker, noop
│   ├─ vectorstores/  qdrant_store
│   └─ ocr/           tesseract, noop
└─ workers/           celery_app, tasks, queue (JobQueue interface)
```

**القاعدة:** الـ services مبتستوردش أي SDK (anthropic/openai/qdrant/FlagEmbedding)، بتتعامل مع الـ interfaces بس من `app/providers/base.py`.

## تبديل الموديلات (من `.env` من غير ما تلمسي كود)

كل دور (role) له provider + model لوحده:

| الدور | المتغيرات | الاختيارات |
|---|---|---|
| إجابة الطالب | `LLM_PROVIDER` `LLM_MODEL` `LLM_BASE_URL` | `anthropic` / `openai` (+ أي سيرفر OpenAI-compatible زي vLLM / Ollama / OpenRouter / Groq بـ `LLM_BASE_URL`) |
| إعادة صياغة سؤال المتابعة | `CONDENSE_PROVIDER` `CONDENSE_MODEL` | نفس الاختيارات (لو فاضي بيستخدم LLM الأساسي) |
| قراءة صور الصفحات (VLM) | `VLM_PROVIDER` `VLM_MODEL` | `anthropic` / `openai` |
| Embeddings | `EMBED_PROVIDER` `EMBED_MODEL` `EMBED_DIM` | `bge_m3` (local + hybrid) / `openai` (dense فقط) |
| Reranker | `RERANK_PROVIDER` `RERANK_MODEL` | `bge` / `none` |
| Vector DB / OCR | `VECTORSTORE_PROVIDER` `OCR_PROVIDER` | `qdrant` / `tesseract` أو `none` |

```powershell
docker compose exec api python -m app.cli providers     # يعرض الشغال حاليًا + المتاح
```

**مثال:** تحويل كل حاجة لـ OpenAI:
```
LLM_PROVIDER=openai          LLM_MODEL=gpt-4.1
CONDENSE_PROVIDER=openai     CONDENSE_MODEL=gpt-4.1-mini
VLM_PROVIDER=openai          VLM_MODEL=gpt-4.1
```

**تنبيه عند تغيير الـ Embedding model:** بيتعمل collection جديدة في Qdrant (اسمها فيه اسم الموديل والـ dim فمفيش خلط vectors). املاها بـ `POST /admin/books/{id}/reindex` لكل كتاب. ده بيستخدم النص المخزّن في الداتابيز **من غير أي استدعاء VLM** (يعني من غير تكلفة).

**إضافة موديل/vendor جديد (Gemini مثلًا):**
1. اعملي class بيعمل implement لـ `LLMProvider` (أو `VLMProvider` / `EmbeddingProvider`...) من `app/providers/base.py`.
2. سجّليه: `register("llm", "gemini", "my_pkg.gemini:GeminiLLM")` واكتبي `LLM_PROVIDER=gemini`.

أي provider أو API key غلط في `.env` بيوقّف الـ API **وقت التشغيل** برسالة واضحة، مش عند أول سؤال لطالب.

## المعمارية

```
PDF upload (admin) ─► Postgres (books, book_pages) ─► Celery worker
   per page: native text layer ─or─ VLM ─► fallback: native → OCR
   page text saved in DB (resumable, no repeated VLM cost) ─► structure-aware chunking
   ─► Embedding provider ─► Vector store (hybrid لو الـ embedder بيدعم sparse، فلتر grade/subject/book)

Student question ─► JWT ─► quota + rate limit ─► condense follow-up ─► search (filter grade)
   ─► reranker ─► LLM (SSE stream) مع [n] citations (book, pages) ─► saved in the student's own chat
```

- **Grades:** `primary-1..6`, `prep-1..3`, `secondary-1..3`. الطالب بيسأل في كتب صفه بس (الفلتر على السيرفر).
- **Chat isolation:** كل query بيتفلتر بـ `user_id` من الـ JWT.

## تشغيل (Windows / PowerShell)

```powershell
copy .env.example .env      # عدّلي JWT_SECRET و ANTHROPIC_API_KEY
docker compose up -d --build
docker compose exec api python -m app.cli init-db
docker compose exec api python -m app.cli create-admin --email admin@school.com --password "ChangeMe-12345" --name Admin
```

Swagger: http://localhost:8000/docs  (أول تشغيل بينزّل موديلات BGE-M3 فبياخد وقت).

## الاستخدام

1. `POST /auth/login` ← token (Authorize في Swagger).
2. أدمن: `POST /admin/books` (file, title, subject, grade, language, term) ← 202، تابعي `GET /admin/books/{id}`.
3. أدمن: `POST /admin/students` (grade + limits اختيارية).
4. طالب: `POST /chat/sessions` ← `POST /chat/sessions/{id}/ask` `{question, subject?, book_id?, stream}`.
   الـ stream بيرجع SSE events: `meta, token, citations, done, error`.
5. أدمن: `POST /admin/books/{id}/retry` (الصفحات الفاشلة بس) و`/reindex` (من غير VLM).

## السيناريوهات اللي متغطية

| السيناريو | التعامل |
|---|---|
| PDF سكان / نص عربي مكسور / معادلات / جداول / رسومات | VLM بيحوّلهم لـ Markdown + LaTeX + وصف الرسم بلغة الصفحة |
| VLM فشل (rate limit/overload) | retries ثم native text ثم OCR ثم صفحة failed |
| صفحة فاشلة | الكتاب يبقى `partial` والباقي شغال، و`/retry` بيعيد الناقص بس |
| الـ worker وقع في النص | `acks_late` + الصفحات المخزنة = بيكمل من حيث وقف |
| نفس الملف اترفع مرتين / مش PDF / متشفّر / تالف / كبير | SHA-256 → 409، وباقيهم 422 |
| تغيير موديل الـ embedding / إعدادات الـ chunking | collection جديدة + `/reindex` من النص المخزن |
| سؤال متابعة ("وإيه بعدها؟") | condense باستخدام تاريخ الشات |
| سؤال بلغة والكتاب بلغة تانية | embeddings متعددة اللغات، والرد بلغة السؤال |
| الإجابة مش في الكتب | رد جاهز "مش لاقي" من غير LLM (ماتهلوسش) |
| prompt injection جوه الكتاب أو السؤال | النصوص معزولة كـ untrusted في الـ system prompt |
| طالب يبعت سؤالين مع بعض في نفس الشات | Redis lock ← 409 |
| الاتصال قطع في نص الإجابة | الرد الجزئي بيتحفظ واستهلاكه بيتحسب |
| حدود الاستهلاك | burst/دقيقة (Redis) + يومي requests/tokens لكل طالب (Postgres، توقيت القاهرة) |
| Vector DB / Redis / LLM واقعين | 503/502 برسالة واضحة، و`/health/ready` بيوضح مين واقع والـ providers الشغالة |
| طالب اتعطّل حسابه | التوكن القديم بيبطل فورًا |

## حدود معروفة (صراحةً)

- اتفحص بـ: compile + import + **26 test** (منهم 14 على fake providers بيثبتوا إن الـ RAG flow شغال على الـ interfaces وإن التبديل بيتم بـ `.env`/`register`) + smoke test للـ startup والـ 401 وتبديل الـ providers. **لسه ماتجرّبش end-to-end** مع Postgres/Qdrant/Claude/OpenAI حقيقيين، فأول تشغيل جرّبيه بكتاب صغير (5-10 صفحات).
- تنفيذات الـ OpenAI providers مكتوبة على الـ SDK لكن ماتجرّبتش مع API حقيقي.
- الجداول بتتعمل بـ `create_all` (`init-db`)، مفيش Alembic migrations لسه.
- حدّ التوكن اليومي بيتشيك قبل السؤال ويتسجل بعده، فممكن يتعدّى بسؤال واحد بالكتير.
- مفيش frontend، Swagger بس.

## تشغيل الاختبارات

```powershell
pip install -r requirements-dev.txt
pytest -q
```
