"""Tiny translation layer: English source strings -> Arabic."""
from __future__ import annotations

_lang = "en"

AR = {
    # generic
    "Open": "فتح", "Save": "حفظ", "Save as…": "حفظ باسم…", "Close": "إغلاق", "Cancel": "إلغاء", "OK": "موافق",
    "Copy": "نسخ", "Copied": "تم النسخ", "Page": "صفحة", "Pages": "الصفحات", "Error": "خطأ", "Done": "تم",
    "Yes": "نعم", "No": "لا", "Password": "كلمة المرور", "Delete": "حذف", "Apply": "تطبيق",
    # menus
    "&File": "&ملف", "&Edit": "&تعديل", "&Pages": "&الصفحات", "&View": "&عرض", "&Help": "&مساعدة",
    "Open…": "فتح…", "New blank PDF": "ملف PDF فارغ جديد", "Save a copy…": "حفظ نسخة…",
    "Save optimized…": "حفظ بحجم أصغر…", "Export pages as images…": "تصدير الصفحات كصور…",
    "Extract pages…": "استخراج صفحات…", "Merge files…": "دمج ملفات…", "Insert PDF…": "إدراج ملف PDF…",
    "Document properties…": "خصائص المستند…", "Set password…": "تعيين كلمة مرور…", "Close tab": "إغلاق التبويب",
    "Quit": "خروج", "Undo": "تراجع", "Redo": "إعادة", "Select all text": "تحديد كل النص", "Find": "بحث",
    "Rotate right": "تدوير لليمين", "Rotate left": "تدوير لليسار", "Delete pages": "حذف الصفحات",
    "Duplicate pages": "تكرار الصفحات", "Insert blank page": "إدراج صفحة فارغة", "Extract selected pages…": "استخراج الصفحات المحددة…",
    "Zoom in": "تكبير", "Zoom out": "تصغير", "Fit width": "ملاءمة العرض", "Fit page": "ملاءمة الصفحة",
    "Actual size": "الحجم الفعلي", "Dark reading mode (invert page)": "وضع القراءة الليلي (عكس الألوان)",
    "Sidebar": "الشريط الجانبي", "Dark theme": "الثيم الداكن", "Light theme": "الثيم الفاتح", "Full screen": "ملء الشاشة",
    "Language": "اللغة", "English": "English", "Arabic": "العربية", "About": "حول البرنامج",
    "Next page": "الصفحة التالية", "Previous page": "الصفحة السابقة", "Toggle theme": "تبديل الثيم",
    "Restart the app to apply the language": "أعد تشغيل البرنامج لتطبيق اللغة",
    # tools
    "Select": "تحديد", "Pan": "تحريك", "Highlight": "تظليل", "Underline": "تسطير", "Strikeout": "شطب",
    "Text": "نص", "Draw": "رسم حر", "Rectangle": "مستطيل", "Ellipse": "دائرة", "Line": "خط", "Arrow": "سهم",
    "Comment": "تعليق", "Image": "صورة", "Signature": "توقيع", "Redact": "إخفاء نهائي", "Edit text": "تعديل نص",
    "Drawing": "رسم", "Redaction": "إخفاء", "Width": "السماكة", "Font size": "حجم الخط", "Font": "الخط",
    "Colour": "اللون", "Fill shapes": "تعبئة الأشكال",
    "Select text, then use Highlight / Underline / Strikeout": "حدّد نصًا ثم استخدم التظليل أو التسطير أو الشطب",
    "Click and drag to write text. Ctrl+Enter to finish": "اسحب بالماوس لكتابة نص. Ctrl+Enter للإنهاء",
    "Click a line of text to edit it": "اضغط على سطر نص لتعديله",
    "Black out an area permanently (the text underneath is removed)": "إخفاء منطقة نهائيًا (يُحذف النص تحتها)",
    "Select some text first": "حدّد نصًا أولًا", "Could not read the image": "تعذّرت قراءة الصورة",
    "No text found here": "لا يوجد نص هنا", "Edit comment": "تعديل التعليق", "Comment:": "التعليق:",
    "Add comment": "إضافة تعليق", "Delete annotation": "حذف التعليق/الرسم", "Text:": "النص:",
    "Choose image…": "اختيار صورة…", "Draw signature…": "رسم توقيع…", "Choose a picture": "اختر صورة",
    "Images": "صور", "Sign here": "وقّع هنا", "Clear": "مسح", "Use signature": "استخدام التوقيع",
    # sidebar
    "Thumbnails": "المصغّرات", "Outline": "الفهرس", "Annotations": "الملاحظات",
    # search
    "Find in document": "بحث في المستند", "No results": "لا نتائج", "result": "نتيجة", "of": "من",
    # start page
    "PDF Toolkit": "أداة PDF", "Open, read and edit PDF files": "افتح ملفات PDF واقرأها وعدّل عليها",
    "Open a PDF": "فتح ملف PDF", "Choose a file from your computer": "اختر ملفًا من جهازك",
    "Merge PDFs": "دمج ملفات PDF", "Combine several files into one": "ادمج عدة ملفات في ملف واحد",
    "New blank document": "مستند فارغ", "Start from an empty page": "ابدأ من صفحة فارغة",
    "Recent files": "الملفات الأخيرة", "Drop a PDF here to open it": "أفلت ملف PDF هنا لفتحه",
    "No recent files yet": "لا توجد ملفات حديثة بعد", "Clear list": "مسح القائمة",
    # dialogs / messages
    "PDF files (*.pdf)": "ملفات PDF (*.pdf)", "All files (*)": "كل الملفات (*)",
    "This file is protected": "هذا الملف محمي", "Enter the password to open it:": "أدخل كلمة المرور لفتحه:",
    "Wrong password": "كلمة المرور غير صحيحة", "Could not open the file": "تعذّر فتح الملف",
    "Unsaved changes": "تعديلات غير محفوظة", "Save changes to {name} before closing?": "هل تريد حفظ التعديلات على {name} قبل الإغلاق؟",
    "Discard": "تجاهل", "Saved": "تم الحفظ", "Saved to {path}": "تم الحفظ في {path}", "Saving…": "جارٍ الحفظ…",
    "Pages to extract (e.g. 1-3,5,8-):": "الصفحات المراد استخراجها (مثل 1-3,5,8-):",
    "Invalid page range": "نطاق صفحات غير صالح", "Export": "تصدير", "Resolution (DPI):": "الدقة (DPI):",
    "Pages to export (e.g. 1-3,5 or all):": "الصفحات المراد تصديرها (مثل 1-3,5 أو all):", "Format:": "الصيغة:",
    "Exported {n} images": "تم تصدير {n} صورة", "Extracted {n} pages": "تم استخراج {n} صفحة",
    "Merged {n} files": "تم دمج {n} ملفات", "Choose at least two files": "اختر ملفين على الأقل",
    "Cannot delete all pages": "لا يمكن حذف كل الصفحات", "Delete {n} page(s)?": "حذف {n} صفحة؟",
    "Insert after page:": "إدراج بعد الصفحة:", "Title": "العنوان", "Author": "المؤلف", "Subject": "الموضوع",
    "Keywords": "كلمات مفتاحية", "Pages count": "عدد الصفحات", "File size": "حجم الملف", "Properties": "الخصائص",
    "Leave empty to remove the password:": "اتركها فارغة لإزالة كلمة المرور:",
    "The password will be applied when you save": "ستُطبّق كلمة المرور عند الحفظ",
    "Untitled.pdf": "بدون عنوان.pdf", "Page {n} of {total}": "صفحة {n} من {total}",
    "Move": "نقل", "Remove": "إزالة", "Up": "أعلى", "Down": "أسفل", "Add files…": "إضافة ملفات…",
    "Merge": "دمج", "Order of the files:": "ترتيب الملفات:",
    "PDF Toolkit — a fast, modern PDF reader and editor.": "أداة PDF — قارئ ومحرر PDF سريع وحديث.",
    "Version": "الإصدار", "Shortcuts": "الاختصارات",
    "Fonts that cover Arabic are used automatically": "تُستخدم خطوط تدعم العربية تلقائيًا",
}


def set_language(lang: str):
    global _lang
    _lang = lang if lang in ("en", "ar") else "en"


def language() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    out = AR.get(text, text) if _lang == "ar" else text
    return out.format(**kw) if kw else out
