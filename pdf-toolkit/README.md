# PDF Toolkit

برنامج مكتبي بسيط (Python + Tkinter) للتعامل مع ملفات PDF:

- **Merge**: دمج عدة ملفات PDF مع ترتيبها
- **Extract pages**: استخراج صفحات محددة (مثل `1-3,5,8-`)
- **Split**: تقسيم الملف إلى صفحات منفصلة
- **Rotate**: تدوير كل الصفحات 90 / 180 / 270 درجة
- **Extract text**: استخراج النص إلى ملف `.txt`

## التشغيل

```bash
pip install -r requirements.txt
python main.py
```

## الاختبارات

```bash
pip install pytest
pytest
```

## بناء ملف exe لويندوز

محليًا:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name PDFToolkit main.py
```

أو تلقائيًا من GitHub: ادخل تبويب **Actions** ← **Build Windows exe** ← **Run workflow**، وحمّل الملف من Artifacts.

## هيكل المشروع

```
pdf-toolkit/
├── main.py              # نقطة التشغيل
├── pdftool/
│   ├── core.py          # منطق عمليات PDF (بدون واجهة)
│   └── gui.py           # واجهة Tkinter
├── tests/test_core.py
├── requirements.txt
└── .github/workflows/build.yml
```

## الترخيص

MIT
